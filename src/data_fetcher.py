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
        self.api_key = api_key or self._load_api_key()
        self.use_fmp = use_fmp
        
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
    
    def _load_api_key(self) -> str:
        """EODHDのAPIキーを読み込む"""
        load_dotenv()
        api_key = os.getenv('EODHD_API_KEY')
        if not api_key:
            raise ValueError(".envファイルにEODHD_API_KEYが設定されていません")
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

    def get_mid_small_symbols(self, use_market_cap_filter: bool = False, 
                             min_market_cap: float = 1e9, max_market_cap: float = 50e9) -> List[str]:
        """S&P 400とS&P 600の銘柄リストを取得（FMPまたはEODHD）"""
        symbols = []
        
        if self.use_fmp and self.fmp_fetcher:
            try:
                if use_market_cap_filter:
                    # 時価総額ベースのフィルタリングを使用
                    logging.info(f"時価総額ベースで中小型株を取得 (${min_market_cap/1e9:.1f}B - ${max_market_cap/1e9:.1f}B)")
                    symbols = self.fmp_fetcher.get_mid_small_cap_symbols(min_market_cap, max_market_cap)
                    
                    if symbols:
                        logging.info(f"FMP時価総額ベースで取得した中小型株銘柄数: {len(symbols)}")
                        return symbols
                    else:
                        logging.warning("FMP時価総額ベースフィルタリングでデータが取得できませんでした")
                else:
                    # 従来のS&P 400/600を試行
                    sp400_symbols = self.fmp_fetcher.get_sp400_constituents()
                    sp600_symbols = self.fmp_fetcher.get_sp600_constituents()
                    
                    symbols.extend(sp400_symbols)
                    symbols.extend(sp600_symbols)
                    
                    if symbols:
                        logging.info(f"FMPから取得したS&P 400/600銘柄数: {len(symbols)}")
                        return symbols
                    else:
                        logging.warning("FMPではS&P 400/600データが利用できません。EODHDにフォールバック")
            except Exception as e:
                logging.warning(f"FMP中型・小型株データ取得失敗: {e}")
        
        # EODHD or fallback
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

    def get_earnings_data(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """決算データを取得（FMPまたはEODHD）"""
        data_source = "FMP" if self.use_fmp else "EODHD"
        print(f"\n1. 決算データの取得を開始 ({data_source}: {start_date} から {end_date})")
        
        if self.use_fmp and self.fmp_fetcher:
            return self._get_earnings_data_fmp(start_date, end_date)
        else:
            return self._get_earnings_data_eodhd(start_date, end_date)
    
    def _get_earnings_data_fmp(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """FMPから決算データを取得"""
        try:
            # FMP Bulk APIで一括取得（アメリカ市場のみ）
            fmp_data = self.fmp_fetcher.get_earnings_calendar(start_date, end_date, us_only=True)
            
            if not fmp_data:
                print("FMP決算データの取得に失敗しました")
                return {'earnings': []}
            
            # FMPデータを標準形式に変換
            processed_df = self.fmp_fetcher.process_earnings_data(fmp_data)
            
            if processed_df.empty:
                print("FMP決算データの処理結果が空です")
                return {'earnings': []}
            
            # DataFrameを辞書リストに変換
            earnings_list = processed_df.to_dict('records')
            
            print(f"FMP決算データ取得完了: {len(earnings_list)}件")
            return {'earnings': earnings_list}
            
        except Exception as e:
            print(f"FMP決算データの取得中にエラーが発生: {str(e)}")
            print("EODHDにフォールバックします...")
            return self._get_earnings_data_eodhd(start_date, end_date)
    
    def _get_earnings_data_eodhd(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """EODHDから決算データを取得。長期間のデータは5年ごとに分割して取得"""
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
                
                # APIレート制限を考慮して少し待機
                time.sleep(0.1)
            
            # 全期間のデータを結合
            combined_data = {'earnings': all_earnings}
            print(f"EODHD決算データ取得完了: {len(all_earnings)}件")
            return combined_data
            
        except Exception as e:
            print(f"EODHD決算データの取得中にエラーが発生: {str(e)}")
            raise

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
        
        # EODHD fallback
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
                
                # APIレート制限を考慮して少し待機
                time.sleep(0.1)
            
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
        
        # EODHD fallback
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