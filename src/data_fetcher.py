import requests
import pandas as pd
import logging
import time
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

from .fmp_data_fetcher import FMPDataFetcher


class DataFetcher:
    """データ取得クラス"""
    
    def __init__(self, api_key: Optional[str] = None, use_fmp: bool = False):
        """DataFetcherの初期化"""
        self.use_fmp = use_fmp
        self.fmp_fetcher = None  # 初期化
        self.api_key = api_key or self._load_api_key()
        
        # FMP Data Fetcherの初期化
        if self.use_fmp:
            try:
                self.fmp_fetcher = FMPDataFetcher()
                logging.info("FMP Data Fetcher initialized as primary data source")
            except Exception as e:
                logging.warning(f"FMP initialization failed, falling back to EODHD: {e}")
                self.use_fmp = False
                self.fmp_fetcher = None
        else:
            self.fmp_fetcher = None

        # Alpaca intraday fetcher (optional)
        try:
            from .alpaca_data_fetcher import AlpacaDataFetcher
            self.alpaca_fetcher = AlpacaDataFetcher(account_type=os.getenv('ALPACA_ACCOUNT_TYPE', 'live'))
            logging.info("AlpacaDataFetcher initialised for intraday data")
        except Exception as e:
            self.alpaca_fetcher = None
            logging.info(f"AlpacaDataFetcher not available: {e}")
    
    def _load_api_key(self) -> str:
        """EODHDのAPIキーを読み込む"""
        load_dotenv()
        api_key = os.getenv('EODHD_API_KEY')
        if not api_key:
            if self.use_fmp:
                # FMPを使用する場合はEODHDキーは必須ではない
                logging.info("EODHD_API_KEY not found, but FMP is available as primary data source")
                return ""  # 空文字列を返してエラーを回避
            else:
                # FMPAPIキーがあるかも確認
                fmp_key = os.getenv('FMP_API_KEY')
                if fmp_key:
                    logging.info("EODHD_API_KEY not found, but FMP_API_KEY is available")
                    return ""  # 空文字列を返してエラーを回避
                else:
                    raise ValueError(".envファイルにEODHD_API_KEYまたはFMP_API_KEYが設定されていません")
        return api_key
    
    def get_sp500_symbols(self) -> List[str]:
        """S&P500銘柄リストを取得（FMPまたはWikipedia）"""
        if self.use_fmp and self.fmp_fetcher:
            try:
                symbols = self.fmp_fetcher.get_sp500_constituents()
                if symbols:
                    logging.info(f"FMPから取得したS&P500銘柄数: {len(symbols)}")
                    return symbols
            except Exception as e:
                logging.warning(f"FMP S&P500データ取得失敗: {e}")
        
        # Fallback to Wikipedia
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', {'class': 'wikitable'})
            
            symbols = []
            for row in table.find_all('tr')[1:]:  # ヘッダーをスキップ
                symbol = row.find_all('td')[0].text.strip()
                symbols.append(symbol)
            
            logging.info(f"Wikipediaから取得したS&P500銘柄数: {len(symbols)}")
            return symbols
            
        except Exception as e:
            logging.error(f"S&P500銘柄リストの取得に失敗: {str(e)}")
            return []

    def get_mid_small_symbols(self, min_market_cap: float = 1e9, max_market_cap: float = 50e9) -> List[str]:
        """時価総額レンジで中型・小型株を取得（優先: FMP company-screener）"""
        symbols: List[str] = []

        # 1) FMP から取得
        if self.use_fmp and self.fmp_fetcher:
            try:
                logging.info(
                    f"FMP stock screener: {min_market_cap/1e9:.1f}B – {max_market_cap/1e9 if max_market_cap<1e12 else '∞'}B")
                symbols = self.fmp_fetcher.get_mid_small_cap_symbols(min_market_cap, max_market_cap)
                if symbols:
                    logging.info(f"Retrieved {len(symbols)} mid/small-cap symbols via FMP screener")
                    return symbols
            except Exception as e:
                logging.warning(f"FMP mid/small-cap fetch failed: {e}")

        # 2) EODHD fallback（APIキーがある場合のみ）
        if self.api_key:  # EODHDキーが利用可能な場合のみ実行
            try:
                # S&P 400 (MID)の取得
                mid_url = f"https://eodhd.com/api/fundamentals/MID.INDX?api_token={self.api_key}&fmt=json"
                mid_response = requests.get(mid_url)
                mid_response.raise_for_status()
                mid_data = mid_response.json()
                
                # S&P 600 (SML)の取得
                sml_url = f"https://eodhd.com/api/fundamentals/SML.INDX?api_token={self.api_key}&fmt=json"
                sml_response = requests.get(sml_url)
                sml_response.raise_for_status()
                sml_data = sml_response.json()
                
                # 構成銘柄の抽出と結合
                symbols = []
                
                # MIDの構成銘柄を追加
                if 'Components' in mid_data:
                    for component in mid_data['Components'].values():
                        symbols.append(component['Code'])
                        
                # SMLの構成銘柄を追加
                if 'Components' in sml_data:
                    for component in sml_data['Components'].values():
                        symbols.append(component['Code'])
                
                if not symbols:
                    raise ValueError("中型・小型株の銘柄リストを取得できませんでした")
                    
                logging.info(f"EODHDから取得した中型・小型株銘柄数: {len(symbols)}")
                return symbols
                
            except Exception as e:
                logging.error(f"中型・小型株銘柄リストの取得に失敗: {str(e)}")
                return []
        else:
            logging.info("EODHD APIキーが設定されていないため中小型株リストをスキップ")
            return []

    def get_earnings_data(self, start_date: str, end_date: str, target_symbols: Optional[list] = None) -> Dict[str, Any]:
        """決算データを取得（FMP または EODHD）
        target_symbols を指定すると該当銘柄のみに絞って取得。
        """
        data_source = "FMP" if self.use_fmp else "EODHD"
        print(f"\n1. 決算データの取得を開始 ({data_source}: {start_date} から {end_date})")
        
        if self.use_fmp and self.fmp_fetcher:
            return self._get_earnings_data_fmp(start_date, end_date, target_symbols)
        else:
            return self._get_earnings_data_eodhd(start_date, end_date)
    
    def _get_earnings_data_fmp(self, start_date: str, end_date: str, target_symbols: Optional[list]) -> Dict[str, Any]:
        """FMPから決算データを取得"""
        try:
            # --- 決算時刻（BMO/AMC）UTCズレ対策 ---------------------------
            # 1日分バッファを付けて取得し、取得後に元期間でフィルタ
            buffer_start = (pd.to_datetime(start_date) - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
            buffer_end   = (pd.to_datetime(end_date)   + pd.Timedelta(days=1)).strftime('%Y-%m-%d')

            # FMP Bulk APIで一括取得（アメリカ市場のみ）
            fmp_data = self.fmp_fetcher.get_earnings_calendar(buffer_start, buffer_end, target_symbols=target_symbols, us_only=True)

            if not fmp_data:
                print("FMP決算データの取得に失敗しました")
                return {'earnings': []}

            # FMPデータを標準形式に変換
            processed_df = self.fmp_fetcher.process_earnings_data(fmp_data)

            # 取得後にオリジナル期間で日付フィルタを適用
            if not processed_df.empty:
                processed_df['report_date'] = pd.to_datetime(processed_df['report_date'])
                start_dt = pd.to_datetime(start_date)
                end_dt   = pd.to_datetime(end_date)
                processed_df = processed_df[(processed_df['report_date'] >= start_dt) & (processed_df['report_date'] <= end_dt)]
                # DataFilter が文字列形式を想定しているため再度 str へ変換
                processed_df['report_date'] = processed_df['report_date'].dt.strftime('%Y-%m-%d')
            
            if processed_df.empty:
                print("FMP決算データの処理結果が空です")
                return {'earnings': []}
            
            # DataFrameを辞書リストに変換
            earnings_list = processed_df.to_dict('records')
            
            print(f"FMP決算データ取得完了: {len(earnings_list)}件")
            return {'earnings': earnings_list}
            
        except ValueError as e:
            # FMP日付制限エラーの場合は詳細なエラーメッセージを表示
            if "2020-08-01" in str(e):
                print(f"\n{str(e)}")
                print("\nEODHDデータソースに自動的に切り替えます...")
                print("注意: EODHDは決算日精度が低い（44%）ですが、長期間の分析が可能です\n")
                return self._get_earnings_data_eodhd(start_date, end_date)
            else:
                print(f"FMP決算データの取得中にエラーが発生: {str(e)}")
                print("EODHDにフォールバックします...")
                return self._get_earnings_data_eodhd(start_date, end_date)
        except Exception as e:
            print(f"FMP決算データの取得中にエラーが発生: {str(e)}")
            print("EODHDにフォールバックします...")
            return self._get_earnings_data_eodhd(start_date, end_date)
    
    def _get_earnings_data_eodhd(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """EODHDから決算データを取得。長期間のデータは5年ごとに分割して取得"""
        if not self.api_key:
            print("EODHD APIキーが設定されていません。FMP_API_KEYを設定してください。")
            return {'earnings': []}
        
        try:
            # 開始日と終了日をdatetime型に変換
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            
            # 5年（1825日）ごとに期間を分割
            period_length = pd.Timedelta(days=1825)
            all_earnings = []
            
            current_start = start
            while current_start < end:
                current_end = min(current_start + period_length, end)
                print(f"期間 {current_start.date()} から {current_end.date()} のデータを取得中...")
                
                url = "https://eodhd.com/api/calendar/earnings"
                params = {
                    'api_token': self.api_key,
                    'from': current_start.strftime('%Y-%m-%d'),
                    'to': current_end.strftime('%Y-%m-%d'),
                    'fmt': 'json'
                }
                
                response = requests.get(url, params=params)
                if response.status_code != 200:
                    raise Exception(f"APIエラー: {response.status_code}")
                    
                data = response.json()
                if 'earnings' in data:
                    all_earnings.extend(data['earnings'])
                
                # 次の期間の開始日を設定
                current_start = current_end + pd.Timedelta(days=1)
                
                # EODHDレート制限対策（最小限に）
                time.sleep(0.05)
            
            # 全期間のデータを結合
            combined_data = {'earnings': all_earnings}
            print(f"EODHD決算データ取得完了: {len(all_earnings)}件")
            return combined_data
            
        except Exception as e:
            print(f"EODHD決算データの取得中にエラーが発生: {str(e)}")
            raise

    def get_preopen_price(self, symbol: str, trade_date: str) -> Optional[float]:
        """Return pre-open price using Alpaca first then FMP fallback."""
        # Prefer Alpaca intraday (pre/post market対応)
        if getattr(self, 'alpaca_fetcher', None):
            price = self.alpaca_fetcher.get_preopen_price(symbol, trade_date)
            if price is not None:
                return price
        # Fallback to FMP if Alpaca unavailable or returns None
        if self.fmp_fetcher:
            return self.fmp_fetcher.get_preopen_price(symbol, trade_date)
        return None

    def get_historical_data(self, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        株価データを取得（FMPまたはEODHD）
        長期間のデータは5年ごとに分割してリクエストし、結果を統合
        """
        if self.use_fmp and self.fmp_fetcher:
            try:
                # FMPから株価データ取得
                fmp_data = self.fmp_fetcher.get_historical_price_data(symbol, start_date, end_date)
                
                if fmp_data and isinstance(fmp_data, list):
                    # FMPデータをDataFrameに変換
                    df = pd.DataFrame(fmp_data)
                    
                    if not df.empty:
                        # FMPのカラム名をEODHD形式に統一
                        column_mapping = {
                            'date': 'date',
                            'open': 'open', 
                            'high': 'high',
                            'low': 'low',
                            'close': 'close',
                            'adjClose': 'adjusted_close',
                            'volume': 'volume'
                        }
                        
                        # 利用可能なカラムのみマッピング
                        available_mapping = {k: v for k, v in column_mapping.items() if k in df.columns}
                        df = df.rename(columns=available_mapping)
                        
                        # 日付処理
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.sort_values('date')
                        
                        # 数値型に変換
                        numeric_columns = ['open', 'high', 'low', 'close', 'adjusted_close', 'volume']
                        for col in numeric_columns:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                        
                        logging.info(f"FMPから{symbol}の株価データを取得: {len(df)}件")
                        return df
                
                logging.warning(f"FMPでの{symbol}株価データ取得に失敗、EODHDにフォールバック")
            except Exception as e:
                logging.warning(f"FMP株価データ取得エラー ({symbol}): {e}")
        
        # EODHD fallback (only if API key is available)
        if not self.api_key:
            logging.warning(f"EODHD APIキーが設定されていないため、{symbol}の株価データを取得できません")
            return None
            
        try:
            api_symbol = symbol.replace('.', '-')
            
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            
            # 5年（1825日）ごとに期間を分割
            period_length = pd.Timedelta(days=1825)
            all_data = []
            
            current_start = start
            while current_start < end:
                current_end = min(current_start + period_length, end)
                logging.info(f"Fetching data for {api_symbol} from {current_start.date()} to {current_end.date()}")
                
                url = f"https://eodhd.com/api/eod/{api_symbol}"
                params = {
                    'api_token': self.api_key,
                    'from': current_start.strftime('%Y-%m-%d'),
                    'to': current_end.strftime('%Y-%m-%d'),
                    'fmt': 'json'
                }
                
                response = requests.get(url, params=params)
                if response.status_code != 200:
                    logging.error(f"APIエラー ({api_symbol}): {response.status_code}")
                    return None
                    
                data = response.json()
                if data:
                    all_data.extend(data)
                
                # 次の期間の開始日を設定
                current_start = current_end + pd.Timedelta(days=1)
                
                # EODHDレート制限対策（最小限に）
                time.sleep(0.05)
            
            if not all_data:
                logging.warning(f"データが見つかりません: {symbol}")
                return None
                
            # DataFrameに変換
            df = pd.DataFrame(all_data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            # 数値型に変換
            numeric_columns = ['open', 'high', 'low', 'close', 'adjusted_close', 'volume']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
            
        except Exception as e:
            logging.error(f"株価データの取得に失敗 ({symbol}): {str(e)}")
            return None

    def get_fundamentals_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        指定された銘柄のファンダメンタルデータを取得（FMPまたはEODHD）
        """
        if self.use_fmp and self.fmp_fetcher:
            try:
                # FMPから企業プロファイル取得
                profile_data = self.fmp_fetcher.get_company_profile(symbol)
                if profile_data:
                    logging.info(f"FMPから{symbol}の企業データを取得")
                    return profile_data
                
                logging.warning(f"FMPでの{symbol}企業データ取得に失敗、EODHDにフォールバック")
            except Exception as e:
                logging.warning(f"FMP企業データ取得エラー ({symbol}): {e}")
        
        # EODHD fallback (only if API key is available)
        if not self.api_key:
            logging.warning(f"EODHD APIキーが設定されていないため、{symbol}のファンダメンタルデータを取得できません")
            return None
            
        try:
            api_symbol = symbol.replace('.', '-')
            url = f"https://eodhd.com/api/fundamentals/{api_symbol}"
            params = {
                'api_token': self.api_key,
                'fmt': 'json'
            }
            
            response = requests.get(url, params=params)
            if response.status_code != 200:
                logging.error(f"ファンダメンタルデータAPIエラー ({api_symbol}): {response.status_code}")
                return None
                
            data = response.json()
            return data
            
        except Exception as e:
            logging.error(f"ファンダメンタルデータの取得に失敗 ({symbol}): {str(e)}")
            return None