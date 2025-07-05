import argparse
from datetime import datetime, timedelta
import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import os
from collections import defaultdict
import time
from typing import Optional, List
import logging
from tqdm import tqdm
import plotly.graph_objs as go
from plotly.offline import plot
import webbrowser
from bs4 import BeautifulSoup

# 環境変数の読み込み
load_dotenv()
EODHD_API_KEY = os.getenv('EODHD_API_KEY')


class EarningsBacktest:
    # ダークモードの色設定
    DARK_THEME = {
        'bg_color': '#1e293b',
        'plot_bg_color': '#1e293b',
        'grid_color': '#334155',
        'text_color': '#e2e8f0',
        'line_color': '#60a5fa',
        'profit_color': '#22c55e',
        'loss_color': '#ef4444'
    }

    def __init__(self, start_date, end_date, stop_loss=6, trail_stop_ma=21,
                 max_holding_days=90, initial_capital=10000, position_size=6,
                 slippage=0.3, risk_limit=6, partial_profit=True, sp500_only=False,
                 mid_small_only=False, language='en', pre_earnings_change=-10):
        """バックテストの初期化"""
        # 日付の妥当性チェック
        current_date = datetime.now()
        end_date_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        if end_date_dt > current_date:
            print(f"警告: 終了日({end_date})が未来の日付です。現在の日付を使用します。")
            self.end_date = current_date.strftime('%Y-%m-%d')
        else:
            self.end_date = end_date
        
        self.start_date = start_date
        self.stop_loss = stop_loss
        self.trail_stop_ma = trail_stop_ma
        self.max_holding_days = max_holding_days
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.slippage = slippage
        self.risk_limit = risk_limit
        self.partial_profit = partial_profit
        self.sp500_only = sp500_only
        self.mid_small_only = mid_small_only
        self.api_key = self._load_api_key()
        self.sp500_symbols = self.get_sp500_symbols() if sp500_only else None
        self.mid_small_symbols = self.get_mid_small_symbols() if mid_small_only else None
        self.language = language
        self.pre_earnings_change = pre_earnings_change
        
        # トレード記録用
        self.trades = []
        self.positions = []
        self.equity_curve = []
        
        # シンボルリストの取得と和集合の作成
        self.target_symbols = None
        if sp500_only or mid_small_only:
            symbols = set()
            if sp500_only and self.sp500_symbols:
                symbols.update(self.sp500_symbols)
            if mid_small_only and self.mid_small_symbols:
                symbols.update(self.mid_small_symbols)
            self.target_symbols = symbols if symbols else None

    def _load_api_key(self):
        """EODHDのAPIキーを読み込む"""
        load_dotenv()
        api_key = os.getenv('EODHD_API_KEY')
        if not api_key:
            raise ValueError(".envファイルにEODHD_API_KEYが設定されていません")
        return api_key

    def get_sp500_symbols(self) -> List[str]:
        """WikipediaからS&P500銘柄リストを取得"""
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
            
            logging.info(f"取得したS&P500銘柄数: {len(symbols)}")
            return symbols
            
        except Exception as e:
            logging.error(f"S&P500銘柄リストの取得に失敗: {str(e)}")
            raise

    def get_mid_small_symbols(self) -> List[str]:
        """EODHDのAPIを使用してS&P 400とS&P 600の銘柄リストを取得"""
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
                
            logging.info(f"取得した中型・小型株銘柄数: {len(symbols)}")
            return symbols
            
        except Exception as e:
            logging.error(f"中型・小型株銘柄リストの取得に失敗: {str(e)}")
            raise

    def get_earnings_data(self):
        """EODHDから決算データを取得。長期間のデータは5年ごとに分割して取得"""
        print(f"\n1. 決算データの取得を開始 ({self.start_date} から {self.end_date})")
        
        try:
            # 開始日と終了日をdatetime型に変換
            start = pd.to_datetime(self.start_date)
            end = pd.to_datetime(self.end_date)
            
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
                # time.sleep(0.1)
            
            # 全期間のデータを結合
            combined_data = {'earnings': all_earnings}
            print(f"決算データ取得完了: {len(all_earnings)}件")
            return combined_data
            
        except Exception as e:
            print(f"決算データの取得中にエラーが発生: {str(e)}")
            raise

    def get_historical_data(self, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        EODHDのAPIを使用して指定された銘柄の株価データを取得
        長期間のデータは5年ごとに分割してリクエストし、結果を統合
        """
        try:
            api_symbol = symbol.replace('.', '-')
            print(f"株価データ取得開始: {symbol}")  # デバッグログ追加
            print(f"期間: {start_date} から {end_date}")  # デバッグログ追加
            
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
                # time.sleep(0.1)
            
            if not all_data:
                logging.warning(f"データなし: {api_symbol}")
                return None
                
            # 全期間のデータを統合してDataFrameに変換
            df = pd.DataFrame(all_data)
            print(f"取得データ件数: {len(df)}")  # デバッグログ追加
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()
            
            # 重複データの削除
            df = df[~df.index.duplicated(keep='first')]
            
            # 調整済み株価を使用するように変更
            df.rename(columns={
                'adjusted_close': 'Close',  # adjusted_closeをCloseとして使用
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'volume': 'Volume'
            }, inplace=True)
            
            # 調整済みの始値、高値、安値を計算
            adj_ratio = df['Close'] / df['close']  # 調整比率を計算
            df['Open'] = df['Open'] * adj_ratio
            df['High'] = df['High'] * adj_ratio
            df['Low'] = df['Low'] * adj_ratio
            
            # 不要なカラムを削除
            df = df.drop(['close'], axis=1)
            
            # 21日移動平均を追加（調整済み株価を使用）
            df['MA21'] = df['Close'].rolling(window=21).mean()
            
            logging.info(f"成功: {api_symbol}")
            return df
            
        except requests.exceptions.RequestException as e:
            logging.error(f"リクエストエラー {api_symbol}: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"予期せぬエラー {api_symbol}: {str(e)}")
            return None

    def determine_trade_date(self, report_date, market_timing):
        """トレード日を決定"""
        report_date = datetime.strptime(report_date, "%Y-%m-%d")
        if market_timing == "BeforeMarket":
            return report_date.strftime("%Y-%m-%d")
        else:
            # BeforeMarket以外はすべてAfterMarketと同じ扱い
            next_date = report_date + timedelta(days=1)
            return next_date.strftime("%Y-%m-%d")

    def filter_earnings_data(self, data):
        """決算データのフィルタリング処理"""
        if 'earnings' not in data:
            raise KeyError("JSONデータに'earnings'キーが存在しません")
        
        total_records = len(data['earnings'])
        print(f"\nフィルタリング処理を開始 (全{total_records}件)")
        
        # 第1段階のフィルタリング
        print("\n=== 第1段階フィルタリング ===")
        print("条件:")
        print("1. .US銘柄のみ")
        print("2. サプライズ率5%以上")
        print("3. 実績値がプラス")
        if self.mid_small_only:
            print("4. 中小型銘柄のみ")
        
        first_filtered = []
        skipped_count = 0
        
        # tqdmを使用してプログレスバーを表示
        for earning in tqdm(data['earnings'], desc="第1段階フィルタリング", total=total_records):
            try:
                # 1. .US銘柄のチェック
                if not earning['code'].endswith('.US'):
                    skipped_count += 1
                    continue
                
                # ターゲットシンボルのフィルタリング
                if self.target_symbols is not None:
                    symbol = earning['code'][:-3]  # .USを除去
                    if symbol not in self.target_symbols:
                        skipped_count += 1
                        continue
                
                # 2&3. サプライズ率と実績値のチェック
                try:
                    percent = float(earning.get('percent', 0))
                    actual = float(earning.get('actual', 0))
                except (ValueError, TypeError):
                    skipped_count += 1
                    continue
                
                if percent < 5 or actual <= 0:
                    skipped_count += 1
                    continue
                
                first_filtered.append(earning)
                
            except Exception as e:
                tqdm.write(f"\n銘柄の処理中にエラー ({earning.get('code', 'Unknown')}): {str(e)}")
                skipped_count += 1
                continue
        
        print(f"\n第1段階フィルタリング結果:")
        print(f"- 処理件数: {total_records}")
        print(f"- 条件適合: {len(first_filtered)}")
        print(f"- スキップ: {skipped_count}")
        
        # 第2段階のフィルタリング
        print("\n=== 第2段階フィルタリング ===")
        print("条件:")
        print("4. ギャップ率0%以上")
        print("5. 株価10ドル以上")
        print("6. 20日平均出来高20万株以上")
        print(f"7. 過去20日間の価格変化率{self.pre_earnings_change}%以上")
        
        date_stocks = defaultdict(list)
        processed_count = 0
        skipped_count = 0
        total_second_stage = len(first_filtered)
        
        # tqdmを使用してプログレスバーを表示
        for earning in tqdm(first_filtered, desc="第2段階フィルタリング", total=total_second_stage):
            try:
                market_timing = earning.get('before_after_market')
                trade_date = self.determine_trade_date(
                    earning['report_date'], 
                    market_timing
                )
                
                # 銘柄コードから.USを除去
                symbol = earning['code'][:-3]
                
                tqdm.write(f"\n処理中: {symbol}")
                tqdm.write(f"- サプライズ率: {float(earning['percent']):.1f}%")
                
                # 株価データの取得期間を延長（過去20日分のデータを取得するため）
                stock_data = self.get_historical_data(
                    symbol,
                    (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=60)).strftime("%Y-%m-%d"),
                    (datetime.strptime(trade_date, "%Y-%m-%d") + 
                     timedelta(days=self.max_holding_days + 30)).strftime("%Y-%m-%d")
                )
                
                if stock_data is None or stock_data.empty:
                    tqdm.write("- スキップ: 株価データなし")
                    skipped_count += 1
                    continue

                # 過去20日間の価格変化率を計算
                try:
                    current_close = stock_data.loc[:trade_date].iloc[-1]['Close']
                    price_20d_ago = stock_data.loc[:trade_date].iloc[-20]['Close']
                    price_change = ((current_close - price_20d_ago) / price_20d_ago) * 100
                    tqdm.write(f"- 過去20日間の価格変化率: {price_change:.1f}%")
                except (KeyError, IndexError):
                    tqdm.write("- スキップ: 20日分の価格データなし")
                    skipped_count += 1
                    continue

                # 価格変化率のフィルタリング
                if price_change < self.pre_earnings_change:
                    tqdm.write(f"- スキップ: 価格変化率が{self.pre_earnings_change}%未満")
                    skipped_count += 1
                    continue

                # トレード日のデータを取得
                try:
                    trade_date_data = stock_data.loc[trade_date]
                    prev_day_data = stock_data.loc[:trade_date].iloc[-2]
                except (KeyError, IndexError):
                    tqdm.write("- スキップ: トレード日のデータなし")
                    skipped_count += 1
                    continue
                
                # ギャップ率を計算
                gap = ((trade_date_data['Open'] - prev_day_data['Close']) / prev_day_data['Close']) * 100
                
                # 平均出来高を計算
                avg_volume = stock_data['Volume'].tail(20).mean()
                
                tqdm.write(f"- ギャップ率: {gap:.1f}%")
                tqdm.write(f"- 株価: ${trade_date_data['Open']:.2f}")
                tqdm.write(f"- 平均出来高: {avg_volume:,.0f}")
                
                # フィルタリング条件のチェック
                if gap < 0:
                    tqdm.write("- スキップ: ギャップ率が負")
                    skipped_count += 1
                    continue
                if trade_date_data['Open'] < 10:
                    tqdm.write("- スキップ: 株価が10ドル未満")
                    skipped_count += 1
                    continue
                if avg_volume < 200000:
                    tqdm.write("- スキップ: 出来高不足")
                    skipped_count += 1
                    continue
                
                # データを保存
                stock_data = {
                    'code': symbol,
                    'report_date': earning['report_date'],
                    'trade_date': trade_date,
                    'price': trade_date_data['Open'],  # 'entry_price'から'price'に戻す
                    'entry_price': trade_date_data['Open'],
                    'prev_close': prev_day_data['Close'],  # prev_closeも追加
                    'gap': gap,
                    'volume': trade_date_data['Volume'],
                    'avg_volume': avg_volume,
                    'percent': float(earning['percent'])
                }
                
                date_stocks[trade_date].append(stock_data)
                processed_count += 1
                tqdm.write("→ 条件適合")
                
            except Exception as e:
                tqdm.write(f"\n銘柄の処理中にエラー ({earning.get('code', 'Unknown')}): {str(e)}")
                skipped_count += 1
                continue
        
        # 各trade_dateで上位6銘柄を選択
        selected_stocks = []
        print("\n日付ごとの選択（上位5銘柄）:")
        for trade_date in sorted(date_stocks.keys()):
            # percentで降順ソート
            date_stocks[trade_date].sort(key=lambda x: float(x['percent']), reverse=True)
            # 上位5銘柄を選択
            selected = date_stocks[trade_date][:5]
            selected_stocks.extend(selected)
            
            print(f"\n{trade_date}: {len(selected)}銘柄")
            for stock in selected:
                print(f"- {stock['code']}: サプライズ{stock['percent']:.1f}%, "
                      f"ギャップ{stock['gap']:.1f}%")
        
        print(f"\n第2段階フィルタリング結果:")
        print(f"- 処理件数: {total_second_stage}")
        print(f"- 条件適合: {processed_count}")
        print(f"- スキップ: {skipped_count}")
        print(f"- 最終選択銘柄数: {len(selected_stocks)}")
        
        return selected_stocks

    def execute_backtest(self):
        """バックテストの実行"""
        print("\nバックテストを開始します...")
        print(f"期間: {self.start_date} から {self.end_date}")
        print(f"初期資金: ${self.initial_capital:,.2f}")
        print(f"ポジションサイズ: {self.position_size}%")
        print(f"ストップロス: {self.stop_loss}%")
        print(f"トレーリングストップMA: {self.trail_stop_ma}日")
        print(f"最大保有期間: {self.max_holding_days}日")
        print(f"スリッページ: {self.slippage}%")
        
        # 決算データを取得
        print("\n2. 決算データの取得中...")
        earnings_data = self.get_earnings_data()
        
        # フィルタリング処理
        print("\n3. 銘柄のフィルタリング中...")
        trade_candidates = self.filter_earnings_data(earnings_data)
        print(f"フィルタリング後の銘柄数: {len(trade_candidates)}")
        
        # 現在の資産額
        current_capital = self.initial_capital
        
        # トレード記録用
        self.trades = []
        
        print("\n4. バックテストの実行中...")
        total_candidates = len(trade_candidates)
        
        # tqdmを使用してプログレスバーを表示
        for candidate in tqdm(trade_candidates, desc="バックテスト実行", total=total_candidates):
            try:
                symbol = candidate['code']
                entry_date = candidate['trade_date']
                
                # リスク管理チェック
                if not self.check_risk_management(entry_date, current_capital):
                    tqdm.write(f"\n{entry_date}: {symbol} - リスク管理によりトレードをスキップ")
                    continue
                
                tqdm.write(f"\n処理中: {symbol} - {entry_date}")
                
                # 株価データの取得期間を延長（最大保有期間分のデータを取得）
                stock_data = self.get_historical_data(
                    symbol,
                    entry_date,
                    (datetime.strptime(entry_date, "%Y-%m-%d") + 
                     timedelta(days=self.max_holding_days + 30)).strftime("%Y-%m-%d")
                )
                
                if stock_data is None or stock_data.empty:
                    tqdm.write(f"- スキップ: 株価データなし")
                    continue
                
                # エントリー価格にスリッページを適用
                entry_price = candidate['price'] * (1 + self.slippage/100)  # 買い注文なので価格を上乗せ
                
                # ポジションサイズの計算
                position_value = current_capital * (self.position_size / 100)
                shares = int(position_value / entry_price)
                if shares == 0:
                    tqdm.write(f"- スキップ: 購入可能株数が0")
                    continue
                
                tqdm.write(f"- エントリー: ${entry_price:.2f} x {shares}株")
                
                # ストップロス価格
                stop_loss_price = entry_price * (1 - self.stop_loss/100)
                
                # トレード開始日以降のデータを抽出
                trade_data = stock_data.loc[entry_date:]
                entry_idx = trade_data.index.get_loc(entry_date)

                # エントリー当日の安値がストップロス価格を下回っているかチェック
                entry_day_low = trade_data.iloc[entry_idx]['Low']
                if entry_day_low <= stop_loss_price:
                    # ストップロス価格で決済（スリッページを適用）
                    exit_price = stop_loss_price * (1 - self.slippage/100)
                    exit_date = entry_date
                    exit_reason = "stop_loss_intraday"
                    trade_pnl = (exit_price - entry_price) * shares
                    trade_pnl_rate = ((exit_price - entry_price) / entry_price) * 100

                    # 資産の更新
                    current_capital += trade_pnl

                    # トレード記録
                    trade_record = {
                        'entry_date': entry_date,
                        'exit_date': exit_date,
                        'ticker': symbol,
                        'shares': shares,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'pnl': trade_pnl,
                        'pnl_rate': trade_pnl_rate,
                        'holding_period': 0,
                        'exit_reason': exit_reason,
                        'gap': candidate['gap']
                    }

                    self.trades.append(trade_record)

                    tqdm.write(f"- 当日ストップロス: ${exit_price:.2f}")
                    tqdm.write(f"- 損益: ${trade_pnl:.2f} ({trade_pnl_rate:.2f}%)")
                    continue

                # 初日の終値で部分利確をチェック
                if self.partial_profit:
                    entry_day_close = trade_data.iloc[entry_idx]['Close']
                    entry_day_profit_rate = ((entry_day_close - entry_price) / entry_price) * 100
                    
                    if entry_day_profit_rate >= 6:
                        # 半分のポジションを利確（スリッページを適用）
                        half_shares = shares // 2
                        if half_shares > 0:
                            exit_price_partial = entry_day_close * (1 - self.slippage/100)  # 売り注文なので価格を下げる
                            trade_pnl_partial = (exit_price_partial - entry_price) * half_shares
                            trade_pnl_rate_partial = ((exit_price_partial - entry_price) / entry_price) * 100
                            
                            # 資産の更新
                            current_capital += trade_pnl_partial
                            
                            # 部分利確のトレード記録
                            trade_record_partial = {
                                'entry_date': entry_date,
                                'exit_date': entry_date,
                                'ticker': symbol,
                                'holding_period': 0,
                                'entry_price': round(entry_price, 2),
                                'exit_price': round(exit_price_partial, 2),
                                'shares': half_shares,
                                'pnl_rate': round(trade_pnl_rate_partial, 2),
                                'pnl': round(trade_pnl_partial, 2),
                                'exit_reason': 'partial_profit'
                            }
                            
                            self.trades.append(trade_record_partial)
                            tqdm.write(f"- 部分利確: ${exit_price_partial:.2f} x {half_shares}株")
                            tqdm.write(f"- 部分利確損益: ${trade_pnl_partial:.2f} ({trade_pnl_rate_partial:.2f}%)")
                            
                            # 残りのポジションサイズを更新
                            shares = shares - half_shares
                
                # 売却条件のチェック
                exit_price = None
                exit_date = None
                exit_reason = None
                
                for i in range(entry_idx + 1, len(trade_data)):
                    current_date = trade_data.index[i]
                    current_row = trade_data.iloc[i]
                    days_held = (current_date - datetime.strptime(entry_date, "%Y-%m-%d")).days
                    
                    # 1. 最大保有期間のチェック
                    if days_held >= self.max_holding_days:
                        exit_price = current_row['Close'] * (1 - self.slippage/100)
                        exit_date = current_date.strftime("%Y-%m-%d")
                        exit_reason = "max_holding_days"
                        break
                    
                    # 2. ストップロスのチェック
                    if current_row['Low'] <= stop_loss_price:
                        exit_price = stop_loss_price * (1 - self.slippage/100)
                        exit_date = current_date.strftime("%Y-%m-%d")
                        exit_reason = "stop_loss"
                        break
                    
                    # 3. トレーリングストップのチェック
                    if current_row['Close'] < current_row['MA21']:
                        exit_price = current_row['MA21'] * (1 - self.slippage/100)
                        exit_date = current_date.strftime("%Y-%m-%d")
                        exit_reason = "trailing_stop"
                        break
                
                # 売却が発生しなかった場合は最終日で売却
                if exit_price is None:
                    last_row = trade_data.iloc[-1]
                    exit_price = last_row['Close'] * (1 - self.slippage/100)
                    exit_date = last_row.name.strftime("%Y-%m-%d")
                    exit_reason = "end_of_data"
                
                # 損益計算
                trade_pnl = (exit_price - entry_price) * shares
                trade_pnl_rate = ((exit_price - entry_price) / entry_price) * 100
                
                # 資産の更新
                current_capital += trade_pnl
                
                # トレード記録
                trade_record = {
                    'entry_date': entry_date,
                    'exit_date': exit_date,
                    'ticker': symbol,
                    'shares': shares,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl': trade_pnl,
                    'pnl_rate': trade_pnl_rate,
                    'holding_period': (datetime.strptime(exit_date, "%Y-%m-%d") - 
                                     datetime.strptime(entry_date, "%Y-%m-%d")).days,
                    'exit_reason': exit_reason,
                    'gap': candidate['gap']  # stockをcandidateに変更
                }
                
                self.trades.append(trade_record)
                
                tqdm.write(f"- 決済: ${exit_price:.2f} ({exit_reason})")
                tqdm.write(f"- 損益: ${trade_pnl:.2f} ({trade_pnl_rate:.2f}%)")
                
            except Exception as e:
                tqdm.write(f"エラー ({symbol}): {str(e)}")
                continue
        
        print("\n5. バックテスト完了")
        print(f"実行したトレード数: {len(self.trades)}")
        print(f"最終資産: ${current_capital:,.2f}")
        self.final_capital = current_capital  # 最終資産を記録

    def calculate_metrics(self):
        """パフォーマンス指標の計算"""
        if not self.trades:
            return None
        
        # トレードをDataFrameに変換
        df = pd.DataFrame(self.trades)
        
        # 資産推移の計算
        df['equity'] = self.initial_capital + df['pnl'].cumsum()
        
        # 最大ドローダウンの計算（資産額ベース）
        df['running_max'] = df['equity'].cummax()
        df['drawdown'] = (df['running_max'] - df['equity']) / df['running_max'] * 100
        max_drawdown_pct = df['drawdown'].max()
        
        # 基本的な指標を計算
        total_trades = len(df)
        winning_trades = len(df[df['pnl_rate'] > 0])  # pnlではなくpnl_rateを使用
        losing_trades = len(df[df['pnl_rate'] <= 0])
        
        # 勝率
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 平均損益率
        avg_win_loss_rate = df['pnl_rate'].mean()
        
        # 平均保有期間
        avg_holding_period = df['holding_period'].mean()
        
        # プロフィットファクター
        total_profit = df[df['pnl'] > 0]['pnl'].sum()
        total_loss = abs(df[df['pnl'] <= 0]['pnl'].sum())
        profit_factor = total_profit / total_loss if total_loss != 0 else float('inf')
        
        # CAGRの計算
        start_date = pd.to_datetime(df['entry_date'].min())
        end_date = pd.to_datetime(df['exit_date'].max())
        years = (end_date - start_date).days / 365.25
        final_capital = self.initial_capital + df['pnl'].sum()
        
        if years > 0:
            cagr = ((final_capital / self.initial_capital) ** (1/years) - 1) * 100
        else:
            cagr = 0
        
        # 終了理由の集計
        exit_reasons = df['exit_reason'].value_counts()
        
        # 年間パフォーマンスの計算を修正
        df['year'] = pd.to_datetime(df['entry_date']).dt.strftime('%Y')
        df['cumulative_pnl'] = df['pnl'].cumsum()
        
        # 年ごとの損益を計算
        yearly_pnl = df.groupby('year')['pnl'].sum().reset_index()
        
        # 各年の開始時点の資産を計算
        yearly_returns = []
        current_capital = self.initial_capital
        
        for year in yearly_pnl['year'].values:
            year_pnl = yearly_pnl[yearly_pnl['year'] == year]['pnl'].values[0]
            return_pct = (year_pnl / current_capital) * 100
            
            yearly_returns.append({
                'year': year,
                'pnl': year_pnl,
                'return_pct': return_pct,
                'start_capital': current_capital,
                'end_capital': current_capital + year_pnl
            })
            
            # 次年の開始資産を更新
            current_capital += year_pnl

        # Expected Value (期待値)の計算も修正
        avg_win = df[df['pnl_rate'] > 0]['pnl_rate'].mean()  # 勝ちトレードの平均リターン率
        avg_loss = df[df['pnl_rate'] < 0]['pnl_rate'].mean()  # 負けトレードの平均リターン率
        win_rate_decimal = winning_trades / total_trades if total_trades > 0 else 0  # 小数での勝率
        expected_value_pct = (win_rate_decimal * avg_win) + ((1 - win_rate_decimal) * avg_loss)
        
        # Calmar Ratioの計算
        calmar_ratio = abs(cagr / max_drawdown_pct) if max_drawdown_pct != 0 else float('inf')
        
        # Pareto Ratio (80/20の法則に基づく指標)の計算
        sorted_profits = df[df['pnl'] > 0]['pnl'].sort_values(ascending=False)
        top_20_percent = sorted_profits.head(int(len(sorted_profits) * 0.2))
        pareto_ratio = (top_20_percent.sum() / sorted_profits.sum() * 100) if not sorted_profits.empty else 0
        
        metrics = {
            'number_of_trades': total_trades,
            'win_rate': round(win_rate, 2),
            'avg_win_loss_rate': round(avg_win_loss_rate, 2),
            'avg_holding_period': round(avg_holding_period, 2),
            'profit_factor': round(profit_factor, 2),
            'max_drawdown_pct': round(max_drawdown_pct, 2),
            'initial_capital': self.initial_capital,
            'final_capital': round(final_capital, 2),
            'total_return_pct': round((final_capital - self.initial_capital) / self.initial_capital * 100, 2),
            'exit_reasons': exit_reasons.to_dict(),
            'cagr': round(cagr, 2),
            'yearly_returns': yearly_returns,
            'expected_value_pct': round(expected_value_pct, 2),
            'calmar_ratio': round(calmar_ratio, 2),
            'pareto_ratio': round(pareto_ratio, 1)
        }
        
        # 結果を表示
        print("\nバックテスト結果:")
        print(f"Number of trades: {metrics['number_of_trades']}")
        print(f"Ave win/loss rate: {metrics['avg_win_loss_rate']:.2f}%")
        print(f"Ave holding period: {metrics['avg_holding_period']} days")
        print(f"Win rate: {metrics['win_rate']:.1f}%")
        print(f"Profit factor: {metrics['profit_factor']}")
        print(f"Max drawdown: {metrics['max_drawdown_pct']:.2f}%")
        print(f"\n終了理由の内訳:")
        for reason, count in metrics['exit_reasons'].items():
            print(f"- {reason}: {count}")
        print(f"\n資産推移:")
        print(f"Initial capital: ${metrics['initial_capital']:,.2f}")
        print(f"Final capital: ${metrics['final_capital']:,.2f}")
        print(f"Total return: {metrics['total_return_pct']:.2f}%")
        print(f"Expected Value: {metrics['expected_value_pct']:.2f}%")
        print(f"Calmar Ratio: {metrics['calmar_ratio']:.2f}")
        print(f"Pareto Ratio: {metrics['pareto_ratio']:.1f}%")
        
        return metrics

    def generate_report(self):
        """トレードレポートの生成"""
        if not self.trades:
            print("トレード記録がありません")
            return
        
        # メトリクスを計算
        metrics = self.calculate_metrics()
        
        # reportsディレクトリが存在しない場合は作成
        os.makedirs('reports', exist_ok=True)
        
        # トレード記録をCSVファイルに出力
        output_file = f"reports/earnings_backtest_{self.start_date}_{self.end_date}.csv"
        df = pd.DataFrame(self.trades)
        df = df[['entry_date', 'exit_date', 'ticker', 'holding_period', 
                 'entry_price', 'exit_price', 'pnl_rate', 'pnl', 'exit_reason']]
        df.to_csv(output_file, index=False)
        print(f"\nトレード記録を {output_file} に保存しました")

    def check_risk_management(self, current_date, current_capital):
        """
        過去1ヶ月間の損益が総資産の-risk_limit%を下回っているかチェック
        """
        if not self.trades:
            return True  # トレード履歴がない場合は制限なし
        
        # 現在の日付から1ヶ月前の日付を計算
        one_month_ago = (datetime.strptime(current_date, "%Y-%m-%d") - 
                        timedelta(days=30)).strftime("%Y-%m-%d")
        
        # 過去1ヶ月間の確定したトレードを抽出
        recent_trades = [
            trade for trade in self.trades
            if trade['exit_date'] >= one_month_ago and trade['exit_date'] <= current_date
        ]
        
        if not recent_trades:
            return True  # 過去1ヶ月間に確定したトレードがない場合は制限なし
        
        # 過去1ヶ月間の損益合計を計算
        total_pnl = sum(trade['pnl'] for trade in recent_trades)
        
        # 損益率を計算（現在の総資産に対する割合）
        pnl_ratio = (total_pnl / current_capital) * 100

        print(f"\nリスク管理チェック ({current_date}):")
        print(f"- 過去1ヶ月間の損益: ${total_pnl:,.2f}")
        print(f"- 現在の総資産: ${current_capital:,.2f}")
        print(f"- 過去1ヶ月間の損益: ${total_pnl:,.2f}")
        print(f"- 損益率: {pnl_ratio:.2f}%")
        
        # -risk_limit%を下回っている場合はFalseを返す
        if pnl_ratio < -self.risk_limit:
            print(f"※ 損益率が-{self.risk_limit}%を下回っているため、新規トレードを制限します")
            return False
        
        return True

    def get_text(self, key):
        """言語に応じたテキストを取得"""
        texts = {
            'report_title': {
                'ja': 'バックテストレポート',
                'en': 'Backtest Report'
            },
            'total_trades': {
                'ja': '総トレード数',
                'en': 'Total Trades'
            },
            'win_rate': {
                'ja': '勝率',
                'en': 'Win Rate'
            },
            'avg_pnl': {
                'ja': '平均損益率',
                'en': 'Avg. PnL'
            },
            'profit_factor': {
                'ja': 'プロフィットファクター',
                'en': 'Profit Factor'
            },
            'max_drawdown': {
                'ja': '最大ドローダウン',
                'en': 'Max Drawdown'
            },
            'total_return': {
                'ja': '総リターン',
                'en': 'Total Return'
            },
            'cumulative_pnl': {
                'ja': '累計損益推移',
                'en': 'Cumulative PnL'
            },
            'pnl_distribution': {
                'ja': '損益率分布',
                'en': 'PnL Distribution'
            },
            'yearly_performance': {
                'ja': '年間パフォーマンス',
                'en': 'Yearly Performance'
            },
            'trade_history': {
                'ja': 'トレード履歴',
                'en': 'Trade History'
            },
            'symbol': {
                'ja': '銘柄',
                'en': 'Symbol'
            },
            'entry_date': {
                'ja': 'エントリー日時',
                'en': 'Entry Date'
            },
            'entry_price': {
                'ja': 'エントリー価格',
                'en': 'Entry Price'
            },
            'exit_date': {
                'ja': '決済日時',
                'en': 'Exit Date'
            },
            'exit_price': {
                'ja': '決済価格',
                'en': 'Exit Price'
            },
            'holding_period': {
                'ja': '保有期間',
                'en': 'Holding Period'
            },
            'shares': {
                'ja': '株数',
                'en': 'Shares'
            },
            'pnl_rate': {
                'ja': '損益率',
                'en': 'PnL Rate'
            },
            'pnl': {
                'ja': '損益',
                'en': 'PnL'
            },
            'exit_reason': {
                'ja': '決済理由',
                'en': 'Exit Reason'
            },
            'profit': {
                'ja': '利益',
                'en': 'Profit'
            },
            'loss': {
                'ja': '損失',
                'en': 'Loss'
            },
            'date': {
                'ja': '日時',
                'en': 'Date'
            },
            'pnl_amount': {
                'ja': '損益 ($)',
                'en': 'PnL ($)'
            },
            'year': {
                'ja': '年',
                'en': 'Year'
            },
            'return_pct': {
                'en': 'Return (%)',
                'ja': 'リターン (%)'
            },
            'days': {
                'ja': '日',
                'en': ' days'
            },
            'number_of_trades': {
                'ja': '取引数',
                'en': 'Number of Trades'
            },
            'drawdown': {
                'ja': 'ドローダウン',
                'en': 'Drawdown'
            },
            'drawdown_chart': {
                'ja': 'ドローダウンチャート',
                'en': 'Drawdown Chart'
            },
            'drawdown_amount': {
                'ja': 'ドローダウン額 ($)',
                'en': 'Drawdown Amount ($)'
            },
            'drawdown_pct': {
                'en': 'Drawdown (%)',
                'ja': 'ドローダウン (%)'
            },
            'position_value_chart': {
                'ja': 'ポジション金額推移',
                'en': 'Position Value History'
            },
            'position_value': {
                'ja': 'ポジション金額 ($)',
                'en': 'Position Value ($)'
            },
            'total_position_value': {
                'ja': '保有ポジション金額',
                'en': 'Total Position Value'
            },
            'monthly_performance_heatmap': {
                'ja': '月次パフォーマンスヒートマップ',
                'en': 'Monthly Performance Heatmap'
            },
            'gap_performance': {
                'ja': 'ギャップサイズ別パフォーマンス',
                'en': 'Performance by Gap Size'
            },
            'pre_earnings_trend_performance': {
                'ja': '決算前トレンド別パフォーマンス',
                'en': 'Performance by Pre-Earnings Trend'
            },
            'average_return': {
                'ja': '平均リターン',
                'en': 'Average Return'
            },
            'number_of_trades_gap': {
                'ja': 'ギャップサイズ別トレード数',
                'en': 'Number of Trades by Gap Size'
            },
            'gap_size': {
                'ja': 'ギャップサイズ',
                'en': 'Gap Size'
            },
            'price_change': {
                'ja': '価格変化率',
                'en': 'Price Change'
            },
            'trend_bin': {
                'ja': 'トレンドビン',
                'en': 'Trend Bin'
            },
            'trend_performance': {
                'ja': 'トレンド別パフォーマンス',
                'en': 'Trend Performance'
            },
            'month': {
                'ja': '月',
                'en': 'Month'
            },
            'analysis_title': {
                'ja': '詳細分析',
                'en': 'Detailed Analysis'
            },
            'monthly_performance': {
                'ja': '月次パフォーマンス',
                'en': 'Monthly Performance'
            },
            'gap_analysis': {
                'ja': 'ギャップ分析',
                'en': 'Gap Analysis'
            },
            'trend_analysis': {
                'ja': 'トレンド分析',
                'en': 'Trend Analysis'
            },
            'backtest_report': {
                'ja': 'バックテストレポート',
                'en': 'Backtest Report'
            },
            'equity_curve': {
                'ja': '資産推移',
                'en': 'Equity Curve'
            },
            'cumulative_pnl': {
                'ja': '累積損益',
                'en': 'Cumulative P&L'
            },
            'return_distribution': {
                'ja': 'リターン分布',
                'en': 'Return Distribution'
            },
            'pnl_distribution': {
                'ja': '損益分布',
                'en': 'P&L Distribution'
            },
            'yearly_performance_chart': {
                'ja': '年間パフォーマンス',
                'en': 'Yearly Performance'
            },
            'yearly_performance': {
                'ja': '年間パフォーマンス',
                'en': 'Yearly Performance'
            },
            'position_value_history': {
                'ja': 'ポジション金額推移',
                'en': 'Position Value History'
            },
            'sector_performance': {
                'ja': 'セクター別パフォーマンス',
                'en': 'Sector Performance'
            },
            'industry_performance': {
                'ja': '業種別パフォーマンス（上位15業種）',
                'en': 'Industry Performance (Top 15)'
            },
            'sector': {
                'ja': 'セクター',
                'en': 'Sector'
            },
            'industry': {
                'ja': '業種',
                'en': 'Industry'
            },
            'eps_analysis': {
                'ja': 'EPSサプライズ分析',
                'en': 'EPS Surprise Analysis'
            },
            'eps_growth_performance': {
                'ja': 'EPS成長率パフォーマンス',
                'en': 'EPS Growth Performance'
            },
            'eps_acceleration_performance': {
                'ja': 'EPS成長率加速度パフォーマンス',
                'en': 'EPS Growth Acceleration Performance'
            },
            'eps_surprise': {
                'ja': 'EPSサプライズ',
                'en': 'EPS Surprise'
            },
            'eps_growth': {
                'ja': 'EPS成長率',
                'en': 'EPS Growth'
            },
            'eps_acceleration': {
                'ja': '成長率加速度',
                'en': 'Growth Acceleration'
            },
            'eps_surprise_performance': {
                'ja': 'EPSサプライズ別パフォーマンス',
                'en': 'EPS Surprise Performance'
            },
            'volume_trend_analysis': {
                'ja': '出来高トレンド分析',
                'en': 'Volume Trend Analysis'
            },
            'volume_category': {
                'ja': '出来高カテゴリ',
                'en': 'Volume Category'
            },
            'ma200_analysis': {
                'ja': 'MA200分析',
                'en': 'MA200 Analysis'
            },
            'ma50_analysis': {
                'ja': 'MA50分析',
                'en': 'MA50 Analysis'
            },
            'ma200_category': {
                'ja': 'MA200カテゴリ',
                'en': 'MA200 Category'
            },
            'ma50_category': {
                'ja': 'MA50カテゴリ',
                'en': 'MA50 Category'
            },
            'expected_value': {
                'ja': '期待値',
                'en': 'Expected Value'
            },
            'calmar_ratio': {
                'ja': 'カルマー比率',
                'en': 'Calmar Ratio'
            },
            'pareto_ratio': {
                'ja': 'パレート比率',
                'en': 'Pareto Ratio'
            },
            'backtest_period': {
                'ja': 'バックテスト期間',
                'en': 'Backtest Period'
            },
        }
        return texts[key][self.language]

    def generate_html_report(self):
        """HTMLレポートの生成"""
        if not self.trades:
            print("トレード記録がありません")
            return
        
        # メトリクスを計算
        metrics = self.calculate_metrics()
        
        # トレード記録をDataFrameに変換
        df = pd.DataFrame(self.trades)
        df['entry_date'] = pd.to_datetime(df['entry_date'])
        df = df.sort_values('entry_date')
        df['cumulative_pnl'] = df['pnl'].cumsum()
        
        # セクター情報を取得して追加
        print("\nセクター情報の取得中...")
        sectors = {}
        
        for ticker in tqdm(df['ticker'].unique(), desc="セクター情報取得中"):
            try:
                url = f"https://eodhd.com/api/fundamentals/{ticker}.US"
                params = {'api_token': self.api_key}
                
                response = requests.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    sectors[ticker] = {
                        'sector': data.get('General', {}).get('Sector', 'Unknown'),
                        'industry': data.get('General', {}).get('Industry', 'Unknown')
                    }
                # time.sleep(0.1)  # API制限を考慮
            except Exception as e:
                print(f"セクター情報の取得エラー ({ticker}): {str(e)}")
                sectors[ticker] = {
                    'sector': 'Unknown',
                    'industry': 'Unknown'
                }
        
        # セクター情報をDataFrameに追加
        df['sector'] = df['ticker'].map(lambda x: sectors.get(x, {}).get('sector', 'Unknown'))
        df['industry'] = df['ticker'].map(lambda x: sectors.get(x, {}).get('industry', 'Unknown'))
        
        # 分析チャートを生成
        analysis_charts = self.generate_analysis_charts(df)
        
        # 資産推移の計算
        df['equity'] = self.initial_capital + df['cumulative_pnl']
        df['equity_pct'] = (df['equity'] / self.initial_capital - 1) * 100
        
        # 累積損益チャート
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(
            x=df['entry_date'],
            y=df['equity_pct'],
            mode='lines',
            name=self.get_text('cumulative_pnl'),
            line=dict(color=EarningsBacktest.DARK_THEME['profit_color'])
        ))
        
        fig_equity.update_layout(
            title=self.get_text('equity_curve'),
            xaxis_title=self.get_text('date'),
            yaxis_title=self.get_text('return_pct'),
            xaxis=dict(
                range=[df['entry_date'].min(), df['entry_date'].max()],
                type='date'
            ),
            yaxis=dict(
                type='linear',
                tickformat='.1f',
                ticksuffix='%',
                autorange=True,  # 自動的に範囲を設定
                tickmode='auto'  # 自動的に目盛りを設定
            ),
            template='plotly_dark',
            paper_bgcolor=EarningsBacktest.DARK_THEME['bg_color'],
            plot_bgcolor=EarningsBacktest.DARK_THEME['plot_bg_color']
        )
        
        # グラフをHTMLに変換（IDを指定）
        equity_chart = plot(fig_equity, output_type='div', include_plotlyjs=False)
        
        # IDを追加し、スケール切り替えボタンを追加（JavaScriptを修正）
        equity_chart = equity_chart.replace(
            'class="plotly-graph-div"',
            'class="plotly-graph-div" data-chart-id="equityCurveChart"'
        ).replace(
            '</div>',
            f'''</div>
            <button onclick="toggleYAxisScale()" style="margin: 10px; padding: 5px 10px; background-color: #334155; color: #e2e8f0; border: none; border-radius: 4px; cursor: pointer;">
                Toggle Log Scale
            </button>
            <script>
                function toggleYAxisScale() {{
                    var plotDiv = document.querySelector('.plotly-graph-div[data-chart-id="equityCurveChart"]');
                    if (!plotDiv) {{
                        console.error("Chart div not found");
                        return;
                    }}
                    
                    // Plotlyグラフが初期化されるまで待機
                    if (!window.Plotly || !plotDiv.data) {{
                        console.log("Waiting for Plotly initialization...");
                        setTimeout(toggleYAxisScale, 100);
                        return;
                    }}

                    var currentType = plotDiv.layout.yaxis.type || 'linear';
                    var update = {{}};
                    var data = plotDiv.data[0];
                    
                    if (currentType === 'log') {{
                        // ログスケールからリニアスケールへ
                        update = {{
                            'yaxis.type': 'linear',
                            'yaxis.range': null,
                            'yaxis.tickformat': '.1f',
                            'yaxis.ticksuffix': '%',
                            'yaxis.tickmode': 'auto',
                            'yaxis.autorange': true
                        }};
                        console.log("Switching to Linear Scale");
                        
                        // データを元の値に戻す
                        Plotly.restyle(plotDiv, {{'y': [data._originalY || data.y]}});
                        
                    }} else {{
                        // リニアスケールからログスケールへ
                        // オリジナルのデータを保存
                        data._originalY = data.y;
                        
                        // データの範囲を取得
                        var minValue = Math.min(...data.y);
                        var maxValue = Math.max(...data.y);
                        
                        // データがすべてマイナスの場合は、ログスケールを使用しない
                        if (maxValue <= 0) {{
                            alert("データがすべてマイナスのため、ログスケールを使用できません。");
                            return;
                        }}
                        
                        // マイナス値を含む場合の特別な処理
                        if (minValue < 0) {{
                            // マイナス値を正の値に変換（最小値の絶対値を基準に）
                            var absMin = Math.abs(minValue);
                            var transformedY = data.y.map(v => v + absMin + 1);  // 1を加えて0を避ける
                            
                            // カスタムティックの設定
                            var tickvals = [];
                            var ticktext = [];
                            var currentVal = Math.floor(minValue);
                            var maxVal = Math.ceil(maxValue);
                            
                            while (currentVal <= maxVal) {{
                                tickvals.push(currentVal + absMin + 1);
                                ticktext.push(currentVal.toFixed(1));
                                currentVal = currentVal < 0 ? currentVal + 1 : currentVal * 2;
                            }}
                            
                            update = {{
                                'yaxis.type': 'log',
                                'yaxis.ticktext': ticktext,
                                'yaxis.tickvals': tickvals,
                                'yaxis.tickformat': '.1f',
                                'yaxis.ticksuffix': '%',
                                'yaxis.tickmode': 'array'
                            }};
                            
                            // 変換したデータを設定
                            Plotly.restyle(plotDiv, {{'y': [transformedY]}});
                        }} else {{
                            // 通常のログスケール処理（すべて正の値の場合）
                            update = {{
                                'yaxis.type': 'log',
                                'yaxis.tickformat': '.1f',
                                'yaxis.ticksuffix': '%',
                                'yaxis.dtick': Math.log10(2)
                            }};
                        }}
                        
                        console.log("Switching to Log Scale");
                    }}

                    // レイアウトを更新
                    Plotly.relayout(plotDiv, update).catch(function(err) {{
                        console.error("Error updating layout:", err);
                        alert("スケールの変更に失敗しました。データを確認してください。");
                        // エラーが起きたら元のスケールに戻す
                        var revertUpdate = {{'yaxis.type': currentType, 'yaxis.range': null}};
                        Plotly.relayout(plotDiv, revertUpdate);
                    }});
                }}
            </script>
            </div>''',
            1  # 最初の</div>のみを置換
        )
        
        # ドローダウンチャート
        df['running_max'] = df['equity'].cummax()
        df['drawdown'] = (df['running_max'] - df['equity']) / df['running_max'] * 100
        
        fig_drawdown = go.Figure()
        fig_drawdown.add_trace(go.Scatter(
            x=df['entry_date'],
            y=-df['drawdown'],
            mode='lines',
            name=self.get_text('drawdown'),
            line=dict(color=EarningsBacktest.DARK_THEME['loss_color'])
        ))
        
        fig_drawdown.update_layout(
            title=self.get_text('drawdown_chart'),
            xaxis_title=self.get_text('date'),
            yaxis_title=self.get_text('drawdown_pct'),
            template='plotly_dark',
            paper_bgcolor=EarningsBacktest.DARK_THEME['bg_color'],
            plot_bgcolor=EarningsBacktest.DARK_THEME['plot_bg_color']
        )
        
        drawdown_chart = plot(fig_drawdown, output_type='div', include_plotlyjs=False)
        
        # リターン分布チャート
        fig_dist = go.Figure()

        # プラスとマイナスのリターンを分けて別々のヒストグラムを作成
        positive_returns = df[df['pnl_rate'] >= 0]['pnl_rate']
        negative_returns = df[df['pnl_rate'] < 0]['pnl_rate']

        # マイナスのリターンのヒストグラム
        fig_dist.add_trace(go.Histogram(
            x=negative_returns,
            xbins=dict(
                start=-10,  # -10%から
                end=0,      # 0%まで
                size=2.5    # 2.5%ごとにビンを作成
            ),
            name='Negative Returns',
            marker_color=EarningsBacktest.DARK_THEME['loss_color'],
            hovertemplate='リターン: %{x:.1f}%<br>取引数: %{y}<extra></extra>'
        ))

        # プラスのリターンのヒストグラム
        fig_dist.add_trace(go.Histogram(
            x=positive_returns,
            xbins=dict(
                start=0,    # 0%から
                end=100,    # 100%まで
                size=2.5    # 2.5%ごとにビンを作成
            ),
            name='Positive Returns',
            marker_color=EarningsBacktest.DARK_THEME['profit_color'],
            hovertemplate='リターン: %{x:.1f}%<br>取引数: %{y}<extra></extra>'
        ))

        fig_dist.update_layout(
            title=self.get_text('return_distribution'),
            xaxis_title=self.get_text('return_pct'),
            yaxis_title=self.get_text('number_of_trades'),
            template='plotly_dark',
            paper_bgcolor=EarningsBacktest.DARK_THEME['bg_color'],
            plot_bgcolor=EarningsBacktest.DARK_THEME['plot_bg_color'],
            bargap=0.1,
            showlegend=False,
            barmode='overlay'  # ヒストグラムを重ねて表示
        )
        
        distribution_chart = plot(fig_dist, output_type='div', include_plotlyjs=False)

        # 年間パフォーマンスチャート
        yearly_data = pd.DataFrame(metrics['yearly_returns'])
        fig_yearly = go.Figure()
        fig_yearly.add_trace(go.Bar(
            x=yearly_data['year'],
            y=yearly_data['return_pct'],
            marker_color=[
                EarningsBacktest.DARK_THEME['profit_color'] if x >= 0 
                else EarningsBacktest.DARK_THEME['loss_color'] 
                for x in yearly_data['return_pct']
            ]
        ))
        
        fig_yearly.update_layout(
            title=self.get_text('yearly_performance'),
            xaxis_title=self.get_text('year'),
            yaxis_title=self.get_text('return_pct'),
            template='plotly_dark',
            paper_bgcolor=EarningsBacktest.DARK_THEME['bg_color'],
            plot_bgcolor=EarningsBacktest.DARK_THEME['plot_bg_color']
        )
        
        yearly_chart = plot(fig_yearly, output_type='div', include_plotlyjs=False)
        
        # ポジション金額チャート
        daily_positions = self.calculate_daily_positions()
        fig_positions = go.Figure()
        fig_positions.add_trace(go.Scatter(
            x=daily_positions.index,
            y=daily_positions['total_value'],
            mode='lines',
            name=self.get_text('position_value'),
            line=dict(color=EarningsBacktest.DARK_THEME['line_color'])
        ))
        
        fig_positions.update_layout(
            title=self.get_text('position_value_history'),
            xaxis_title=self.get_text('date'),
            yaxis_title=self.get_text('position_value'),
            template='plotly_dark',
            paper_bgcolor=EarningsBacktest.DARK_THEME['bg_color'],
            plot_bgcolor=EarningsBacktest.DARK_THEME['plot_bg_color']
        )
        
        position_chart = plot(fig_positions, output_type='div', include_plotlyjs=False)
        
        # HTMLテンプレート
        html_template = f"""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Backtest Report</title>
                <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
                <meta charset="UTF-8">
                <style>
                    body {{
                        background-color: {EarningsBacktest.DARK_THEME['bg_color']};
                        color: {EarningsBacktest.DARK_THEME['text_color']};
                        font-family: Arial, sans-serif;
                        margin: 20px;
                    }}
                    .metrics-container {{
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                        gap: 20px;
                        margin: 20px 0;
                    }}
                    .metric-card {{
                        background-color: {EarningsBacktest.DARK_THEME['plot_bg_color']};
                        padding: 15px;
                        border-radius: 8px;
                        text-align: center;
                    }}
                    .metric-value {{
                        font-size: 24px;
                        font-weight: bold;
                        margin: 10px 0;
                    }}
                    .chart-container {{
                        margin: 20px 0;
                        background-color: {EarningsBacktest.DARK_THEME['plot_bg_color']};
                        padding: 20px;
                        border-radius: 8px;
                    }}
                    .trades-table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin: 20px 0;
                        background-color: {EarningsBacktest.DARK_THEME['plot_bg_color']};
                        border-radius: 8px;
                    }}
                    .trades-table th, .trades-table td {{
                        padding: 12px;
                        text-align: left;
                        border-bottom: 1px solid {EarningsBacktest.DARK_THEME['grid_color']};
                    }}
                    .trades-table th {{
                        background-color: {EarningsBacktest.DARK_THEME['bg_color']};
                        color: {EarningsBacktest.DARK_THEME['text_color']};
                        cursor: pointer;
                    }}
                    .profit {{
                        color: {EarningsBacktest.DARK_THEME['profit_color']};
                    }}
                    .loss {{
                        color: {EarningsBacktest.DARK_THEME['loss_color']};
                    }}
                    .asc::after {{
                        content: " ▲";
                    }}
                    .desc::after {{
                        content: " ▼";
                    }}
                </style>
            </head>
            <body>
                <h1>{self.get_text('backtest_report')}</h1>
                
                <div class="metrics-container">
                    {self._generate_metrics_html(df)}
                </div>
                
                <div class="chart-container">
                    <h2>{self.get_text('equity_curve')}</h2>
                    {equity_chart}
                </div>
                
                <div class="chart-container">
                    <h2>{self.get_text('drawdown_chart')}</h2>
                    {drawdown_chart}
                </div>
                
                <div class="chart-container">
                    <h2>{self.get_text('return_distribution')}</h2>
                    {distribution_chart}
                </div>
                
                <div class="chart-container">
                    <h2>{self.get_text('yearly_performance_chart')}</h2>
                    {yearly_chart}
                </div>
                
                <div class="chart-container">
                    <h2>{self.get_text('position_value_history')}</h2>
                    {position_chart}
                </div>
                
                <div class="chart-container">
                    <h2>{self.get_text('analysis_title')}</h2>
                    
                    <div class="analysis-section">
                        <h3>{self.get_text('monthly_performance')}</h3>
                        {analysis_charts['monthly']}
                    </div>
                    
                    <div class="analysis-section">
                        <h3>{self.get_text('sector_performance')}</h3>
                        {analysis_charts['sector']}
                    </div>
                    
                    <div class="analysis-section">
                        <h3>{self.get_text('industry_performance')}</h3>
                        {analysis_charts['industry']}
                    </div>
                    
                    <div class="analysis-section">
                        <h3>{self.get_text('gap_analysis')}</h3>
                        {analysis_charts['gap']}
                    </div>
                    
                    <div class="analysis-section">
                        <h3>{self.get_text('trend_analysis')}</h3>
                        {analysis_charts['trend']}
                    </div>

                    <div class="analysis-section">
                        <h3>{self.get_text('eps_analysis')}</h3>
                        {analysis_charts['eps_surprise']}
                    </div>
                    
                    <div class="analysis-section">
                        <h3>{self.get_text('eps_growth_performance')}</h3>
                        {analysis_charts['eps_growth']}
                    </div>
                    
                    <div class="analysis-section">
                        <h3>{self.get_text('eps_acceleration_performance')}</h3>
                        {analysis_charts['eps_acceleration']}
                    </div>
                    <div class="chart-container">
                        <h3>{self.get_text('volume_trend_analysis')}</h3>
                        {analysis_charts['volume']}
                    </div>
                    
                    <div class="chart-container">
                        <h3>{self.get_text('ma200_analysis')}</h3>
                        {analysis_charts['ma200']}
                    </div>
                    
                    <div class="chart-container">
                        <h3>{self.get_text('ma50_analysis')}</h3>
                        {analysis_charts['ma50']}
                    </div>                
                </div>
                
                <div class="trades-container">
                    <h2>{self.get_text('trade_history')}</h2>
                    {self._generate_trades_table_html()}
                </div>
                
                <script>
                    // テーブルソート機能
                    document.querySelectorAll('.trades-table th').forEach(th => th.addEventListener('click', (() => {{
                        const table = th.closest('table');
                        const tbody = table.querySelector('tbody');
                        const rows = Array.from(tbody.querySelectorAll('tr'));
                        const index = Array.from(th.parentNode.children).indexOf(th);
                        
                        // 数値かどうかを判定（$や%を除去して判定）
                        const isNumeric = !isNaN(rows[0].children[index].textContent.replace(/[^0-9.-]+/g,""));
                        
                        // ソート方向の決定（現在の状態を反転）
                        const direction = th.classList.contains('asc') ? -1 : 1;
                        
                        // ソート処理
                        rows.sort((a, b) => {{
                            const aValue = a.children[index].textContent.replace(/[^0-9.-]+/g,"");
                            const bValue = b.children[index].textContent.replace(/[^0-9.-]+/g,"");
                            
                            if (isNumeric) {{
                                return direction * (parseFloat(aValue) - parseFloat(bValue));
                            }} else {{
                                return direction * aValue.localeCompare(bValue);
                            }}
                        }});
                        
                        // ソート方向インジケータの更新
                        th.closest('tr').querySelectorAll('th').forEach(el => {{
                            el.classList.remove('asc', 'desc');
                        }});
                        th.classList.toggle('asc', direction === 1);
                        th.classList.toggle('desc', direction === -1);
                        
                        // テーブルの更新
                        tbody.append(...rows);
                    }})));
                </script>
                

            </body>
        </html>
        """

        # HTMLファイルの保存
        output_file = f"reports/earnings_backtest_report_{self.start_date}_{self.end_date}.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_template)
        
        print(f"\nHTMLレポートを {output_file} に保存しました")
        
        # ブラウザでレポートを開く
        webbrowser.open('file://' + os.path.realpath(output_file))

    def calculate_daily_positions(self):
        """日次の保有ポジション金額を計算"""
        if not self.trades:
            return pd.DataFrame(columns=['total_value', 'num_positions'])
        
        print("\n=== ポジション計算のデバッグ ===")
        
        # 全期間の確認
        trade_dates = [(pd.to_datetime(t['entry_date']), pd.to_datetime(t['exit_date'])) 
                       for t in self.trades]
        start = min(date[0] for date in trade_dates)
        end = max(date[1] for date in trade_dates)
        print(f"\n計算対象期間: {start} から {end}")
        
        # 日付インデックスの作成
        dates = pd.date_range(start=start, end=end, freq='D')
        print(f"生成された日付インデックス数: {len(dates)}")
        
        # 日次ポジション金額を格納するDataFrame
        daily_positions = pd.DataFrame(
            0,
            index=dates, 
            columns=['total_value', 'num_positions'],
            dtype=float
        )
        
        # 各トレードについて、保有期間中の日次ポジション金額を計算
        for trade in self.trades:
            ticker = trade['ticker']
            entry_date = pd.to_datetime(trade['entry_date'])
            exit_date = pd.to_datetime(trade['exit_date'])
            shares = trade['shares']
            
            print(f"\n処理中のトレード: {ticker}")
            print(f"エントリー日: {entry_date}")
            print(f"イグジット日: {exit_date}")
            print(f"保有株数: {shares}")
            
            # 株価データを取得
            stock_data = self.get_historical_data(
                ticker,
                entry_date.strftime('%Y-%m-%d'),
                exit_date.strftime('%Y-%m-%d')
            )
            
            if stock_data is not None:
                print(f"株価データ取得結果:")
                print(f"- データ期間: {stock_data.index.min()} から {stock_data.index.max()}")
                print(f"- データ件数: {len(stock_data)}")
                print(f"- カラム: {stock_data.columns.tolist()}")
                
                # 保有期間中の各日について
                trade_dates = pd.date_range(entry_date, exit_date)
                print(f"\n保有期間の日付生成:")
                print(f"- 開始日: {trade_dates[0]}")
                print(f"- 終了日: {trade_dates[-1]}")
                print(f"- 日数: {len(trade_dates)}")
                
                last_close = None  # 直前の営業日の終値を保持
                
                for date in trade_dates:
                    if date in stock_data.index:
                        close_price = stock_data.loc[date, 'Close']
                        last_close = close_price  # 営業日の終値を保存
                    else:   
                        # 休場日の場合は直前の終値を使用
                        if last_close is not None:
                            close_price = last_close
                            print(f"\n{date}は休場日のため、直前終値 ${close_price:.2f} を使用")
                        else:
                            print(f"\n{date}のデータなし（直前終値も未取得）")
                            continue
                    
                    position_value = float(shares * close_price)
                    print(f"\n{date}の計算:")
                    print(f"- 終値: ${close_price:.2f}")
                    print(f"- ポジション価値: ${position_value:.2f}")
                    
                    daily_positions.loc[date, 'total_value'] += position_value
                    daily_positions.loc[date, 'num_positions'] += 1.0
            else:
                print("株価データの取得に失敗")
        
        print("\n最終結果:")
        print(daily_positions.head())
        print("\n...")
        print(daily_positions.tail())
        
        return daily_positions

    def analyze_performance(self):
        """バックテストの詳細分析を実行"""
        if not self.trades:
            print("分析するトレードデータがありません")
            return
        
        # トレードデータをDataFrameに変換
        df = pd.DataFrame(self.trades)
        df['entry_date'] = pd.to_datetime(df['entry_date'])
        df['exit_date'] = pd.to_datetime(df['exit_date'])
        
        # 月次パフォーマンス分析
        self._analyze_monthly_performance(df)
        
        # セクター・業種分析
        self._analyze_sector_performance(df)
        
        # EPS分析を追加
        self._analyze_eps_performance(df)
        
        # ギャップ分析
        self._analyze_gap_performance(df)
        
        # トレンド分析
        self._analyze_pre_earnings_trend(df)
        
        # ブレイクアウト分析
        self._analyze_breakout_performance(df)

    def _analyze_monthly_performance(self, df):
        """月次パフォーマンスの分析"""
        print("\n=== 月次パフォーマンス分析 ===")
        
        # 月と年を抽出
        df['year'] = df['entry_date'].dt.year
        df['month'] = df['entry_date'].dt.month
        
        # 月次の集計
        monthly_stats = df.groupby(['year', 'month']).agg({
            'pnl_rate': ['mean', 'std', 'count'],
            'pnl': 'sum'
        }).round(2)
        
        # 月ごとの統計
        monthly_summary = df.groupby('month').agg({
            'pnl_rate': ['mean', 'std', 'count'],
            'pnl': 'sum'
        }).round(2)
        
        print("\n月別平均パフォーマンス:")
        for month in range(1, 13):
            if month in monthly_summary.index:
                stats = monthly_summary.loc[month]
                print(f"\n{month}月:")
                print(f"- 平均リターン: {stats[('pnl_rate', 'mean')]:.2f}%")
                print(f"- 標準偏差: {stats[('pnl_rate', 'std')]:.2f}%")
                print(f"- トレード数: {stats[('pnl_rate', 'count')]}")
                print(f"- 累計損益: ${stats[('pnl', 'sum')]:,.2f}")

    def _analyze_sector_performance(self, df):
        """セクター・業種別パフォーマンスの分析"""
        print("\n=== セクター・業種別パフォーマンス分析 ===")
        
        # EODHDからセクター情報を取得
        sectors = {}
        for ticker in tqdm(df['ticker'].unique(), desc="セクター情報取得中"):
            try:
                url = f"https://eodhd.com/api/fundamentals/{ticker}.US"
                params = {'api_token': self.api_key}
                
                response = requests.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    sectors[ticker] = {
                        'sector': data.get('General', {}).get('Sector', 'Unknown'),
                        'industry': data.get('General', {}).get('Industry', 'Unknown')
                    }
                # time.sleep(0.1)  # API制限を考慮
            except Exception as e:
                print(f"セクター情報の取得エラー ({ticker}): {str(e)}")
                sectors[ticker] = {
                    'sector': 'Unknown',
                    'industry': 'Unknown'
                }
        
        # セクター情報をDataFrameに追加
        df['sector'] = df['ticker'].map(lambda x: sectors.get(x, {}).get('sector', 'Unknown'))
        df['industry'] = df['ticker'].map(lambda x: sectors.get(x, {}).get('industry', 'Unknown'))
        
        # セクター別の統計
        sector_stats = df.groupby('sector').agg({
            'pnl_rate': ['mean', 'std', 'count'],
            'pnl': 'sum'
        }).round(2)
        
        print("\nセクター別パフォーマンス:")
        for sector in sector_stats.index:
            stats = sector_stats.loc[sector]
            print(f"\n{sector}:")
            print(f"- 平均リターン: {stats[('pnl_rate', 'mean')]:.2f}%")
            print(f"- 標準偏差: {stats[('pnl_rate', 'std')]:.2f}%")
            print(f"- トレード数: {stats[('pnl_rate', 'count')]}")
            print(f"- 累計損益: ${stats[('pnl', 'sum')]:,.2f}")

    def _analyze_eps_performance(self, df):
        """EPS関連のパフォーマンス分析"""
        print("\n=== EPS分析 ===")
        
        # entry_dateを確実に日付型に変換
        df['entry_date'] = pd.to_datetime(df['entry_date'])
        
        # EPSデータの取得
        print("\nEPSデータの取得中...")
        eps_data = {}
        for ticker, group in df.groupby('ticker'):
            try:
                # 各銘柄の最新のエントリー日を使用
                latest_entry = group['entry_date'].max()
                eps_info = self._get_eps_data(ticker, latest_entry)
                if eps_info:
                    eps_data[ticker] = eps_info
                # time.sleep(0.1)  # API制限を考慮
                
            except Exception as e:
                print(f"エラー ({ticker}): {str(e)}")
                continue
        
        if not eps_data:
            print("警告: EPSデータが取得できませんでした")
            return df
        
        # EPSデータをDataFrameに追加
        df['eps_surprise'] = df['ticker'].map(lambda x: eps_data.get(x, {}).get('eps_surprise'))
        df['eps_yoy_growth'] = df['ticker'].map(lambda x: eps_data.get(x, {}).get('eps_yoy_growth'))
        df['growth_acceleration'] = df['ticker'].map(lambda x: eps_data.get(x, {}).get('growth_acceleration'))
        
        # カテゴリの作成
        df = self._categorize_eps_metrics(df)
        
        # 各カテゴリごとの分析を実行
        categories = [
            ('surprise_category', 'EPSサプライズ別'),
            ('growth_category', 'EPS成長率別'),
            ('growth_acceleration_category', 'EPS成長率加速度別')
        ]
        
        for category, title in categories:
            stats = df.groupby(category).agg({
                'pnl_rate': ['mean', 'std', 'count'],
                'pnl': ['sum', lambda x: (x > 0).mean() * 100]  # 合計と勝率
            }).round(2)
            
            print(f"\n{title}パフォーマンス:")
            for cat in stats.index:
                if pd.isna(cat):  # NaN/NAの場合はスキップ
                    continue
                s = stats.loc[cat]
                print(f"\n{cat}:")
                print(f"- 平均リターン: {s[('pnl_rate', 'mean')]:.2f}%")
                print(f"- 標準偏差: {s[('pnl_rate', 'std')]:.2f}%")
                print(f"- トレード数: {s[('pnl_rate', 'count')]}")
                print(f"- 勝率: {s[('pnl', '<lambda>')]:.1f}%")
                print(f"- 累計損益: ${s[('pnl', 'sum')]:,.2f}")
        
        # 相関分析
        correlations = {
            'EPSサプライズ': df['eps_surprise'].corr(df['pnl_rate']),
            'EPS成長率': df['eps_yoy_growth'].corr(df['pnl_rate']),
            '成長率加速度': df['growth_acceleration'].corr(df['pnl_rate'])
        }
        
        print("\n=== パフォーマンスとの相関 ===")
        for metric, corr in correlations.items():
            if not pd.isna(corr):  # NaN/NAでない場合のみ表示
                print(f"{metric}との相関係数: {corr:.3f}")
        
        return df

    def _get_eps_data(self, ticker, entry_date):
        """EODHDからEPSデータを取得"""
        try:
            # Calendar APIを使用
            url = f"https://eodhd.com/api/calendar/earnings"
            
            # エントリー日を基準に日付範囲を設定（過去2年分）
            entry_dt = pd.to_datetime(entry_date)
            from_date = (entry_dt - timedelta(days=730)).strftime('%Y-%m-%d')  # エントリー日の2年前
            to_date = entry_dt.strftime('%Y-%m-%d')  # エントリー日
            
            params = {
                'api_token': self.api_key,
                'symbols': f"{ticker}.US",
                'from': from_date,
                'to': to_date,
                'fmt': 'json'
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                earnings_data = data.get('earnings', [])
                
                if not earnings_data:
                    print(f"警告: {ticker}の決算データが見つかりません")
                    return None
                
                # 日付でソート（新しい順）
                earnings_data.sort(key=lambda x: x['date'], reverse=True)
                
                # 四半期データの抽出（8四半期分を取得）
                quarters = []
                for e in earnings_data:
                    quarter_date = pd.to_datetime(e['date'])
                    if len(quarters) == 0 or (quarters[-1]['date'] - quarter_date).days > 60:
                        quarters.append({
                            'date': quarter_date,
                            'eps': float(e['actual']) if e['actual'] is not None else None,
                            'estimate': float(e['estimate']) if e['estimate'] is not None else None
                        })
                    if len(quarters) >= 8:  # 8四半期分取得したら終了
                        break
                
                if len(quarters) < 8:
                    print(f"警告: 十分な四半期データがありません（{len(quarters)}四半期分）")
                    return None
                
                # EPSサプライズの計算（最新四半期）
                current_quarter = quarters[0]
                eps_surprise = None
                if (current_quarter['eps'] is not None and 
                    current_quarter['estimate'] is not None and 
                    abs(current_quarter['estimate']) > 0.0001):
                    eps_surprise = ((current_quarter['eps'] - current_quarter['estimate']) / 
                                  abs(current_quarter['estimate'])) * 100
                
                # YoY成長率の計算（最新四半期）
                current_growth = None
                if (current_quarter['eps'] is not None and 
                    quarters[4]['eps'] is not None and 
                    abs(quarters[4]['eps']) > 0.0001):
                    current_growth = ((current_quarter['eps'] - quarters[4]['eps']) / 
                                    abs(quarters[4]['eps'])) * 100
                
                # 前四半期のYoY成長率
                prev_growth = None
                if (quarters[1]['eps'] is not None and 
                    quarters[5]['eps'] is not None and 
                    abs(quarters[5]['eps']) > 0.0001):
                    prev_growth = ((quarters[1]['eps'] - quarters[5]['eps']) / 
                                 abs(quarters[5]['eps'])) * 100
                
                # 成長率の加速度
                growth_acceleration = None
                if current_growth is not None and prev_growth is not None:
                    growth_acceleration = current_growth - prev_growth
                
                return {
                    'eps_surprise': eps_surprise,
                    'eps_yoy_growth': current_growth,
                    'prev_quarter_growth': prev_growth,
                    'growth_acceleration': growth_acceleration
                }
                
        except Exception as e:
            print(f"EPSデータの取得エラー ({ticker}): {str(e)}")
            if 'response' in locals():
                print(f"APIステータスコード: {response.status_code}")
                print(f"APIレスポンス: {response.text[:200]}")
            return None

    def _categorize_eps_metrics(self, df):
        """EPSメトリクスをカテゴリに分類"""
        # NoneをNaNに変換
        df['eps_surprise'] = pd.to_numeric(df['eps_surprise'], errors='coerce')
        df['eps_yoy_growth'] = pd.to_numeric(df['eps_yoy_growth'], errors='coerce')
        df['growth_acceleration'] = pd.to_numeric(df['growth_acceleration'], errors='coerce')
        
        # サプライズのカテゴリ化
        df['surprise_category'] = pd.cut(
            df['eps_surprise'],
            bins=[-np.inf, -20, -10, 0, 10, 20, np.inf],
            labels=['<-20%', '-20~-10%', '-10~0%', '0~10%', '10~20%', '>20%'],
            include_lowest=True
        )
        
        # YoY成長率のカテゴリ化
        df['growth_category'] = pd.cut(
            df['eps_yoy_growth'],
            bins=[-np.inf, -50, -25, 0, 25, 50, np.inf],
            labels=['<-50%', '-50~-25%', '-25~0%', '0~25%', '25~50%', '>50%'],
            include_lowest=True
        )
        
        # 成長率の加速度をカテゴリ化
        df['growth_acceleration_category'] = pd.cut(
            df['growth_acceleration'],
            bins=[-np.inf, -30, -15, 0, 15, 30, np.inf],
            labels=['Strong Deceleration', 'Deceleration', 'Mild Deceleration', 
                    'Mild Acceleration', 'Acceleration', 'Strong Acceleration'],
            include_lowest=True
        )
        
        # カテゴリの順序を設定
        for col, categories in [
            ('surprise_category', ['<-20%', '-20~-10%', '-10~0%', '0~10%', '10~20%', '>20%']),
            ('growth_category', ['<-50%', '-50~-25%', '-25~0%', '0~25%', '25~50%', '>50%']),
            ('growth_acceleration_category', ['Strong Deceleration', 'Deceleration', 'Mild Deceleration',
                                            'Mild Acceleration', 'Acceleration', 'Strong Acceleration'])
        ]:
            df[col] = pd.Categorical(df[col], categories=categories, ordered=True)
        
        return df

    def _analyze_gap_performance(self, df):
        """ギャップの大きさによるパフォーマンス分析"""
        print("\n=== ギャップサイズ別パフォーマンス分析 ===")
        
        # ギャップ率でビンを作成
        df['gap_bin'] = pd.cut(df['gap'], 
                              bins=[-np.inf, 5, 10, 15, 20, np.inf],
                              labels=['0-5%', '5-10%', '10-15%', '15-20%', '20%+'])
        
        # ギャップサイズ別の統計
        gap_stats = df.groupby('gap_bin').agg({
            'pnl_rate': ['mean', 'std', 'count'],
            'pnl': 'sum'
        }).round(2)
        
        # 勝率の計算
        win_rates = df.groupby('gap_bin').apply(
            lambda x: (x['pnl'] > 0).mean() * 100
        ).round(2)
        
        print("\nギャップサイズ別パフォーマンス:")
        for gap_bin in gap_stats.index:
            stats = gap_stats.loc[gap_bin]
            print(f"\n{gap_bin}:")
            print(f"- 平均リターン: {stats[('pnl_rate', 'mean')]:.2f}%")
            print(f"- 標準偏差: {stats[('pnl_rate', 'std')]:.2f}%")
            print(f"- トレード数: {stats[('pnl_rate', 'count')]}")
            print(f"- 勝率: {win_rates[gap_bin]:.1f}%")
            print(f"- 累計損益: ${stats[('pnl', 'sum')]:,.2f}")

    def _analyze_pre_earnings_trend(self, df):
        """決算前のトレンド分析"""
        print("\n=== 決算前トレンド分析 ===")
        
        # 各トレードの決算前20日間のトレンドを分析
        trends = []
        for _, trade in df.iterrows():
            # 決算前の株価データを取得
            pre_earnings_start = (pd.to_datetime(trade['entry_date']) - 
                                timedelta(days=30)).strftime('%Y-%m-%d')
            stock_data = self.get_historical_data(
                trade['ticker'],
                pre_earnings_start,
                trade['entry_date']
            )
            
            if stock_data is not None and len(stock_data) >= 20:
                # 21日移動平均線を計算
                stock_data['MA21'] = stock_data['Close'].rolling(window=21).mean()
                
                # 20日間の価格変化率を計算
                price_change = ((stock_data['Close'].iloc[-1] - stock_data['Close'].iloc[-20]) / 
                              stock_data['Close'].iloc[-20] * 100)
                
                # 20日移動平均との位置関係
                ma_position = 'above' if stock_data['Close'].iloc[-1] > stock_data['MA21'].iloc[-1] else 'below'
                
                trends.append({
                    'ticker': trade['ticker'],
                    'entry_date': trade['entry_date'],
                    'pre_earnings_change': price_change,
                    'ma_position': ma_position,
                    'pnl_rate': trade['pnl_rate'],
                    'pnl': trade['pnl']  # pnlを追加
                })
        
        trend_df = pd.DataFrame(trends)
        
        if not trend_df.empty:
            # トレンドの強さでビンを作成
            trend_df['trend_bin'] = pd.cut(trend_df['pre_earnings_change'],
                                         bins=[-np.inf, -20, -10, 0, 10, 20, np.inf],
                                         labels=['<-20%', '-20~-10%', '-10~0%', '0~10%', '10~20%', '>20%'])
            
            # トレンド別の統計
            trend_stats = trend_df.groupby('trend_bin').agg({
                'pnl_rate': ['mean', 'std', 'count']
            }).round(2)
            
            print("\nトレンド別パフォーマンス:")
            for trend_bin in trend_stats.index:
                stats = trend_stats.loc[trend_bin]
                print(f"\n{trend_bin}:")
                print(f"- 平均リターン: {stats[('pnl_rate', 'mean')]:.2f}%")
                print(f"- 標準偏差: {stats[('pnl_rate', 'std')]:.2f}%")
                print(f"- トレード数: {stats[('pnl_rate', 'count')]}")
        
        return trend_df  # DataFrameを返す

    def _analyze_breakout_performance(self, df):
        """ブレイクアウトパターンの分析"""
        print("\n=== ブレイクアウトパターン分析 ===")
        
        breakouts = []
        for _, trade in df.iterrows():
            # 決算前の株価データを取得
            pre_earnings_start = (pd.to_datetime(trade['entry_date']) - 
                                timedelta(days=60)).strftime('%Y-%m-%d')
            stock_data = self.get_historical_data(
                trade['ticker'],
                pre_earnings_start,
                trade['entry_date']
            )
            
            if stock_data is not None and len(stock_data) >= 20:
                # 20日高値を計算
                high_20d = stock_data['High'].rolling(window=20).max().iloc[-2]  # 直前日までの20日高値
                
                # ブレイクアウトの判定
                is_breakout = trade['entry_price'] > high_20d
                breakout_percent = ((trade['entry_price'] - high_20d) / high_20d * 100) if is_breakout else 0
                
                breakouts.append({
                    'ticker': trade['ticker'],
                    'entry_date': trade['entry_date'],
                    'is_breakout': is_breakout,
                    'breakout_percent': breakout_percent,
                    'pnl_rate': trade['pnl_rate']
                })
        
        breakout_df = pd.DataFrame(breakouts)
        
        # ブレイクアウトの有無による統計
        breakout_stats = breakout_df.groupby('is_breakout').agg({
            'pnl_rate': ['mean', 'std', 'count']
        }).round(2)
        
        # ブレイクアウトの大きさによる分析
        breakout_df['breakout_bin'] = pd.cut(breakout_df['breakout_percent'],
                                            bins=[-np.inf, 0, 2, 5, 10, np.inf],
                                            labels=['No Breakout', '0-2%', '2-5%', '5-10%', '>10%'])
        
        size_stats = breakout_df.groupby('breakout_bin').agg({
            'pnl_rate': ['mean', 'std', 'count']
        }).round(2)
        
        print("\nブレイクアウトパターン別パフォーマンス:")
        for breakout_bin in size_stats.index:
            stats = size_stats.loc[breakout_bin]
            print(f"\n{breakout_bin}:")
            print(f"- 平均リターン: {stats[('pnl_rate', 'mean')]:.2f}%")
            print(f"- 標準偏差: {stats[('pnl_rate', 'std')]:.2f}%")
            print(f"- トレード数: {stats[('pnl_rate', 'count')]}")

    def generate_analysis_charts(self, df):
        """分析チャートの生成"""
        charts = {}
        
        # EPSデータの取得と追加
        print("\nEPSデータの取得中...")
        eps_data = {}
        
        # 全トレードのユニークな(ticker, entry_date)の組み合わせを取得
        trade_keys = df[['ticker', 'entry_date']].drop_duplicates()
        total_trades = len(trade_keys)
        
        # tqdmを使用して進捗バーを表示
        for _, row in tqdm(trade_keys.iterrows(), 
                          total=total_trades,
                          desc="EPSデータ取得",
                          ncols=100):
            ticker = row['ticker']
            entry_date = row['entry_date']
            trade_key = (ticker, entry_date.strftime('%Y-%m-%d'))
            
            try:
                eps_info = self._get_eps_data(ticker, entry_date)
                
                if eps_info:
                    eps_data[trade_key] = eps_info
                    tqdm.write(f"{ticker} ({entry_date.strftime('%Y-%m-%d')}): EPSデータ取得成功")
                else:
                    tqdm.write(f"{ticker} ({entry_date.strftime('%Y-%m-%d')}): EPSデータなし")
                    
                # time.sleep(0.1)  # API制限を考慮
                
            except Exception as e:
                tqdm.write(f"{ticker} ({entry_date.strftime('%Y-%m-%d')}): エラー - {str(e)}")
                continue

        print(f"\nEPSデータ取得完了: {len(eps_data)}/{total_trades} トレード")
        
        # EPSデータをDataFrameに追加（trade_keyに基づいて）
        df['eps_surprise'] = df.apply(
            lambda x: eps_data.get((x['ticker'], x['entry_date'].strftime('%Y-%m-%d')), {}).get('eps_surprise'),
            axis=1
        )
        df['eps_yoy_growth'] = df.apply(
            lambda x: eps_data.get((x['ticker'], x['entry_date'].strftime('%Y-%m-%d')), {}).get('eps_yoy_growth'),
            axis=1
        )
        df['growth_acceleration'] = df.apply(
            lambda x: eps_data.get((x['ticker'], x['entry_date'].strftime('%Y-%m-%d')), {}).get('growth_acceleration'),
            axis=1
        )

        # EPSメトリクスをカテゴリに分類
        df = self._categorize_eps_metrics(df)
        
        # 月次パフォーマンスと勝率のヒートマップ
        df['year'] = df['entry_date'].dt.year
        df['month'] = df['entry_date'].dt.month
        
        # 平均リターンの計算（observed=Trueを明示的に指定）
        monthly_returns = df.pivot_table(
            values='pnl_rate',
            index='year',
            columns='month',
            aggfunc='mean',
            observed=True  # 警告を解消
        ).round(2)
        
        # 勝率の計算（observed=Trueを明示的に指定）
        monthly_winrate = df.pivot_table(
            values='pnl',
            index='year',
            columns='month',
            aggfunc=lambda x: (x > 0).mean() * 100,
            observed=True  # 警告を解消
        ).round(1)
        
        # サブプロットの作成
        fig = go.Figure()
        
        # 平均リターンのヒートマップ
        fig.add_trace(go.Heatmap(
            z=monthly_returns.values,
            x=monthly_returns.columns,
            y=monthly_returns.index,
            colorscale=[
                [0.0, EarningsBacktest.DARK_THEME['loss_color']],      # -20%以下: 濃い赤
                [0.2, '#ff6b6b'],                                      # -20%～-10%: 薄い赤
                [0.4, '#ffa07a'],                                      # -10%～0%: さらに薄い赤
                [0.5, EarningsBacktest.DARK_THEME['plot_bg_color']],   # 0%: 背景色
                [0.6, '#98fb98'],                                      # 0%～10%: 薄い緑
                [0.8, '#3cb371'],                                      # 10%～20%: 中程度の緑
                [1.0, EarningsBacktest.DARK_THEME['profit_color']]     # 20%以上: 濃い緑
            ],
            zmid=0,  # 0%を中心に色を変える
            zmin=-20,  # -20%以下は同じ色
            zmax=20,   # 20%以上は同じ色
            text=monthly_returns.values.round(1),
            texttemplate='%{text}%',
            hoverongaps=False,
            name=self.get_text('average_return'),
            xaxis='x',
            yaxis='y'
        ))
        
        # 勝率のヒートマップ
        fig.add_trace(go.Heatmap(
            z=monthly_winrate.values,
            x=monthly_winrate.columns,
            y=monthly_winrate.index,
            colorscale=[
                [0, EarningsBacktest.DARK_THEME['loss_color']],
                [0.5, EarningsBacktest.DARK_THEME['plot_bg_color']],
                [1, EarningsBacktest.DARK_THEME['profit_color']]
            ],
            text=monthly_winrate.values.round(1),
            texttemplate='%{text}%',
            hoverongaps=False,
            name=self.get_text('win_rate'),
            xaxis='x2',
            yaxis='y2'
        ))
        
        # レイアウトの更新
        fig.update_layout(
            title=self.get_text('monthly_performance_heatmap'),
            grid=dict(rows=2, columns=1, pattern='independent'),
            annotations=[
                dict(
                    text=self.get_text('average_return'),
                    x=0.5, y=1.1,
                    xref='paper', yref='paper',
                    showarrow=False
                ),
                dict(
                    text=self.get_text('win_rate'),
                    x=0.5, y=0.45,
                    xref='paper', yref='paper',
                    showarrow=False
                )
            ],
            template='plotly_dark',
            paper_bgcolor=EarningsBacktest.DARK_THEME['bg_color'],
            plot_bgcolor=EarningsBacktest.DARK_THEME['plot_bg_color'],
            height=800  # グラフの高さを調整
        )
        
        charts['monthly'] = plot(fig, output_type='div', include_plotlyjs=False)
        
        # ギャップサイズ別パフォーマンス
        gap_stats = df.groupby(pd.cut(df['gap'], 
                                     bins=[-np.inf, 5, 10, 15, 20, np.inf],
                                     labels=['0-5%', '5-10%', '10-15%', '15-20%', '20%+'])
                             ).agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': 'sum'
        }).round(2)
        
        fig_gap = go.Figure()
        fig_gap.add_trace(go.Bar(
            x=gap_stats.index,
            y=gap_stats[('pnl_rate', 'mean')],
            name=self.get_text('average_return'),
            text=gap_stats[('pnl_rate', 'mean')].apply(lambda x: f'{x:.1f}%'),
            textposition='auto'
        ))
        
        fig_gap.add_trace(go.Scatter(
            x=gap_stats.index,
            y=gap_stats[('pnl_rate', 'count')],
            name=self.get_text('number_of_trades_gap'),
            yaxis='y2',
            line=dict(color=EarningsBacktest.DARK_THEME['line_color'])
        ))
        
        fig_gap.update_layout(
            title=self.get_text('gap_performance'),
            xaxis_title=self.get_text('gap_size'),
            yaxis_title=self.get_text('return_pct'),
            yaxis2=dict(
                title=self.get_text('number_of_trades_gap'),
                overlaying='y',
                side='right'
            ),
            template='plotly_dark',
            paper_bgcolor=EarningsBacktest.DARK_THEME['bg_color'],
            plot_bgcolor=EarningsBacktest.DARK_THEME['plot_bg_color']
        )
        
        charts['gap'] = plot(fig_gap, output_type='div', include_plotlyjs=False)
        
        # トレンド分析のチャート
        trend_data = self._calculate_trend_data(df)
        if trend_data is not None and not trend_data.empty and 'trend_bin' in trend_data.columns:
            trend_stats = trend_data.groupby('trend_bin').agg({
                'pnl_rate': ['mean', 'count'],
                'pnl': lambda x: (x > 0).mean() * 100
            }).round(2)
            
            fig_trend = go.Figure(data=[
                go.Bar(
                    x=trend_stats.index,
                    y=trend_stats[('pnl_rate', 'mean')],
                    text=trend_stats[('pnl_rate', 'mean')].apply(lambda x: f'{x:.1f}%'),
                    textposition='auto',
                    marker_color=[
                        EarningsBacktest.DARK_THEME['profit_color'] if x > 0 else EarningsBacktest.DARK_THEME['loss_color']
                        for x in trend_stats[('pnl_rate', 'mean')]
                    ]
                )
            ])
            
            fig_trend.update_layout(
                title=self.get_text('pre_earnings_trend_performance'),
                xaxis_title=self.get_text('price_change'),
                yaxis_title=self.get_text('return_pct'),
                template='plotly_dark',
                paper_bgcolor=EarningsBacktest.DARK_THEME['bg_color'],
                plot_bgcolor=EarningsBacktest.DARK_THEME['plot_bg_color']
            )
            
            charts['trend'] = plot(fig_trend, output_type='div', include_plotlyjs=False)
        else:
            print("トレンドデータが取得できませんでした")
            charts['trend'] = ""
        
        # セクター別パフォーマンスチャート
        sector_stats = df.groupby('sector').agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': lambda x: (x > 0).mean() * 100  # 勝率を計算
        }).round(2)
        
        fig_sector = go.Figure()
        
        # 平均リターンのバー
        fig_sector.add_trace(go.Bar(
            x=sector_stats.index,
            y=sector_stats[('pnl_rate', 'mean')],
            name=self.get_text('average_return'),
            text=sector_stats[('pnl_rate', 'mean')].apply(lambda x: f'{x:.1f}%'),
            textposition='auto',
            marker_color=[
                EarningsBacktest.DARK_THEME['profit_color'] if x > 0 
                else EarningsBacktest.DARK_THEME['loss_color'] 
                for x in sector_stats[('pnl_rate', 'mean')]
            ]
        ))
        
        # 勝率のライン
        fig_sector.add_trace(go.Scatter(
            x=sector_stats.index,
            y=sector_stats[('pnl', '<lambda>')],
            name=self.get_text('win_rate'),
            yaxis='y2',
            line=dict(color=EarningsBacktest.DARK_THEME['line_color'])
        ))
        
        fig_sector.update_layout(
            title=self.get_text('sector_performance'),
            xaxis_title=self.get_text('sector'),
            yaxis_title=self.get_text('return_pct'),
            yaxis2=dict(
                title=self.get_text('win_rate'),
                overlaying='y',
                side='right',
                range=[0, 100]
            ),
            template='plotly_dark',
            paper_bgcolor=EarningsBacktest.DARK_THEME['bg_color'],
            plot_bgcolor=EarningsBacktest.DARK_THEME['plot_bg_color'],
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            )
        )
        
        charts['sector'] = plot(fig_sector, output_type='div', include_plotlyjs=False)
        
        # 業種別パフォーマンスチャート
        industry_stats = df.groupby('industry').agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': lambda x: (x > 0).mean() * 100
        }).round(2)
        
        # トレード数で上位15業種を選択
        top_industries = industry_stats.nlargest(15, ('pnl_rate', 'count'))
        
        fig_industry = go.Figure()
        
        # 平均リターンのバー
        fig_industry.add_trace(go.Bar(
            x=top_industries.index,
            y=top_industries[('pnl_rate', 'mean')],
            name=self.get_text('average_return'),
            text=top_industries[('pnl_rate', 'mean')].apply(lambda x: f'{x:.1f}%'),
            textposition='auto',
            marker_color=[
                EarningsBacktest.DARK_THEME['profit_color'] if x > 0 
                else EarningsBacktest.DARK_THEME['loss_color'] 
                for x in top_industries[('pnl_rate', 'mean')]
            ]
        ))
        
        # 勝率のライン
        fig_industry.add_trace(go.Scatter(
            x=top_industries.index,
            y=top_industries[('pnl', '<lambda>')],
            name=self.get_text('win_rate'),
            yaxis='y2',
            line=dict(color=EarningsBacktest.DARK_THEME['line_color'])
        ))
        
        fig_industry.update_layout(
            title=self.get_text('industry_performance'),
            xaxis_title=self.get_text('industry'),
            yaxis_title=self.get_text('return_pct'),
            yaxis2=dict(
                title=self.get_text('win_rate'),
                overlaying='y',
                side='right',
                range=[0, 100]
            ),
            template='plotly_dark',
            paper_bgcolor=EarningsBacktest.DARK_THEME['bg_color'],
            plot_bgcolor=EarningsBacktest.DARK_THEME['plot_bg_color'],
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            )
        )
        
        # X軸のラベルを45度回転
        fig_industry.update_xaxes(tickangle=45)
        
        charts['industry'] = plot(fig_industry, output_type='div', include_plotlyjs=False)
        
        # EPSサプライズ別パフォーマンスチャート
        surprise_stats = df.groupby('surprise_category', observed=True).agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': lambda x: (x > 0).mean() * 100  # 勝率を計算
        }).round(2)
        
        fig_surprise = go.Figure()
        
        # 平均リターンのバー
        fig_surprise.add_trace(go.Bar(
            x=surprise_stats.index,
            y=surprise_stats[('pnl_rate', 'mean')],
            name=self.get_text('average_return'),
            text=surprise_stats[('pnl_rate', 'mean')].apply(lambda x: f'{x:.1f}%'),
            textposition='auto',
            marker_color=[
                self.DARK_THEME['profit_color'] if x > 0 
                else self.DARK_THEME['loss_color'] 
                for x in surprise_stats[('pnl_rate', 'mean')]
            ]
        ))
        
        # 勝率のライン
        fig_surprise.add_trace(go.Scatter(
            x=surprise_stats.index,
            y=surprise_stats[('pnl', '<lambda>')],
            name=self.get_text('win_rate'),
            yaxis='y2',
            line=dict(color=self.DARK_THEME['line_color'])
        ))
        
        fig_surprise.update_layout(
            title=self.get_text('eps_surprise_performance'),
            xaxis_title=self.get_text('eps_surprise'),
            yaxis_title=self.get_text('return_pct'),
            yaxis2=dict(
                title=self.get_text('win_rate'),
                overlaying='y',
                side='right',
                range=[0, 100]
            ),
            template='plotly_dark',
            paper_bgcolor=self.DARK_THEME['bg_color'],
            plot_bgcolor=self.DARK_THEME['plot_bg_color'],
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            )
        )
        
        charts['eps_surprise'] = plot(fig_surprise, output_type='div', include_plotlyjs=False)
        
        # EPS成長率別パフォーマンスチャート
        growth_stats = df.groupby('growth_category', observed=True).agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': lambda x: (x > 0).mean() * 100
        }).round(2)
        
        fig_growth = go.Figure()
        
        # 平均リターンのバー
        fig_growth.add_trace(go.Bar(
            x=growth_stats.index,
            y=growth_stats[('pnl_rate', 'mean')],
            name=self.get_text('average_return'),
            text=growth_stats[('pnl_rate', 'mean')].apply(lambda x: f'{x:.1f}%'),
            textposition='auto',
            marker_color=[
                self.DARK_THEME['profit_color'] if x > 0 
                else self.DARK_THEME['loss_color'] 
                for x in growth_stats[('pnl_rate', 'mean')]
            ]
        ))
        
        # 勝率のライン
        fig_growth.add_trace(go.Scatter(
            x=growth_stats.index,
            y=growth_stats[('pnl', '<lambda>')],
            name=self.get_text('win_rate'),
            yaxis='y2',
            line=dict(color=self.DARK_THEME['line_color'])
        ))
        
        fig_growth.update_layout(
            title=self.get_text('eps_growth_performance'),
            xaxis_title=self.get_text('eps_growth'),
            yaxis_title=self.get_text('return_pct'),
            yaxis2=dict(
                title=self.get_text('win_rate'),
                overlaying='y',
                side='right',
                range=[0, 100]
            ),
            template='plotly_dark',
            paper_bgcolor=self.DARK_THEME['bg_color'],
            plot_bgcolor=self.DARK_THEME['plot_bg_color'],
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            )
        )
        
        charts['eps_growth'] = plot(fig_growth, output_type='div', include_plotlyjs=False)
        
        # 成長率加速度別パフォーマンスチャート
        acceleration_stats = df.groupby('growth_acceleration_category', observed=True).agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': lambda x: (x > 0).mean() * 100
        }).round(2)
        
        fig_acceleration = go.Figure()
        
        # 平均リターンのバー
        fig_acceleration.add_trace(go.Bar(
            x=acceleration_stats.index,
            y=acceleration_stats[('pnl_rate', 'mean')],
            name=self.get_text('average_return'),
            text=acceleration_stats[('pnl_rate', 'mean')].apply(lambda x: f'{x:.1f}%'),
            textposition='auto',
            marker_color=[
                self.DARK_THEME['profit_color'] if x > 0 
                else self.DARK_THEME['loss_color'] 
                for x in acceleration_stats[('pnl_rate', 'mean')]
            ]
        ))
        
        # 勝率のライン
        fig_acceleration.add_trace(go.Scatter(
            x=acceleration_stats.index,
            y=acceleration_stats[('pnl', '<lambda>')],
            name=self.get_text('win_rate'),
            yaxis='y2',
            line=dict(color=self.DARK_THEME['line_color'])
        ))
        
        fig_acceleration.update_layout(
            title=self.get_text('eps_acceleration_performance'),
            xaxis_title=self.get_text('eps_acceleration'),
            yaxis_title=self.get_text('return_pct'),
            yaxis2=dict(
                title=self.get_text('win_rate'),
                overlaying='y',
                side='right',
                range=[0, 100]
            ),
            template='plotly_dark',
            paper_bgcolor=self.DARK_THEME['bg_color'],
            plot_bgcolor=self.DARK_THEME['plot_bg_color'],
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            )
        )
        
        # X軸のラベルを45度回転（加速度カテゴリは文字列が長いため）
        fig_acceleration.update_xaxes(tickangle=45)
        
        charts['eps_acceleration'] = plot(fig_acceleration, output_type='div', include_plotlyjs=False)
        
        # 出来高トレンド分析のチャート
        volume_data = self._analyze_volume_trend(df)
        if volume_data is not None and not volume_data.empty:
            try:
                volume_stats = volume_data.groupby('volume_category').agg({
                    'pnl_rate': ['mean', 'count'],
                    'pnl': lambda x: (x > 0).mean() * 100
                }).round(2)
                
                fig_volume = go.Figure()
                
                # 平均リターンのバー
                fig_volume.add_trace(go.Bar(
                    x=volume_stats.index,
                    y=volume_stats[('pnl_rate', 'mean')],
                    name=self.get_text('average_return'),
                    text=volume_stats[('pnl_rate', 'mean')].apply(lambda x: f'{x:.1f}%'),
                    textposition='auto',
                    marker_color=[
                        self.DARK_THEME['profit_color'] if x > 0 
                        else self.DARK_THEME['loss_color'] 
                        for x in volume_stats[('pnl_rate', 'mean')]
                    ]
                ))
                
                # 勝率のライン
                fig_volume.add_trace(go.Scatter(
                    x=volume_stats.index,
                    y=volume_stats[('pnl', '<lambda>')],
                    name=self.get_text('win_rate'),
                    yaxis='y2',
                    line=dict(color=self.DARK_THEME['line_color'])
                ))
                
                fig_volume.update_layout(
                    title=self.get_text('volume_trend_analysis'),
                    xaxis_title=self.get_text('volume_category'),
                    yaxis_title=self.get_text('return_pct'),
                    yaxis2=dict(
                        title=self.get_text('win_rate'),
                        overlaying='y',
                        side='right',
                        range=[0, 100]
                    ),
                    template='plotly_dark',
                    paper_bgcolor=self.DARK_THEME['bg_color'],
                    plot_bgcolor=self.DARK_THEME['plot_bg_color'],
                    showlegend=True,
                    legend=dict(
                        orientation='h',
                        yanchor='bottom',
                        y=1.02,
                        xanchor='right',
                        x=1
                    )
                )
                
                # X軸のラベルを45度回転（カテゴリ名が長いため）
                fig_volume.update_xaxes(tickangle=45)
                
                charts['volume'] = plot(fig_volume, output_type='div', include_plotlyjs=False)
            except Exception as e:
                print(f"出来高トレンドチャート生成エラー: {str(e)}")
                charts['volume'] = ""
        else:
            print("出来高トレンドデータが取得できませんでした")
            charts['volume'] = ""
        
        # 移動平均線分析のチャート
        ma_data = self._analyze_ma_position(df)
        
        # デバッグ情報を追加
        print("\nMA分析結果:")
        print(f"データ存在: {ma_data is not None}")
        if ma_data is not None:
            print(f"データ件数: {len(ma_data)}")
            print(f"カラム: {ma_data.columns.tolist()}")
        
        # データが正しく取得できたか確認
        if ma_data is not None and not ma_data.empty:
            # MA200のチャート
            if 'ma200_category' in ma_data.columns:
                try:
                    ma200_stats = ma_data.groupby('ma200_category').agg({
                        'pnl_rate': ['mean', 'count'],
                        'pnl': lambda x: (x > 0).mean() * 100
                    }).round(2)
                    
                    # ... チャート生成コード ...
                    fig_ma200 = go.Figure()
                    fig_ma200.add_trace(go.Bar(
                        x=ma200_stats.index,
                        y=ma200_stats[('pnl_rate', 'mean')],
                        name=self.get_text('average_return'),
                        text=ma200_stats[('pnl_rate', 'mean')].apply(lambda x: f'{x:.1f}%'),
                        textposition='auto',
                        marker_color=[
                            self.DARK_THEME['profit_color'] if x > 0 
                            else self.DARK_THEME['loss_color'] 
                            for x in ma200_stats[('pnl_rate', 'mean')]
                        ]
                    ))
                    
                    # 勝率のライン
                    fig_ma200.add_trace(go.Scatter(
                        x=ma200_stats.index,
                        y=ma200_stats[('pnl', '<lambda>')],
                        name=self.get_text('win_rate'),
                        yaxis='y2',
                        line=dict(color=self.DARK_THEME['line_color'])
                    ))
                    
                    fig_ma200.update_layout(
                        title=self.get_text('ma200_analysis'),
                        xaxis_title=self.get_text('ma200_category'),
                        yaxis_title=self.get_text('return_pct'),
                        yaxis2=dict(
                            title=self.get_text('win_rate'),
                            overlaying='y',
                            side='right',
                            range=[0, 100]
                        ),
                        template='plotly_dark',
                        paper_bgcolor=self.DARK_THEME['bg_color'],
                        plot_bgcolor=self.DARK_THEME['plot_bg_color'],
                        showlegend=True,
                        legend=dict(
                            orientation='h',
                            yanchor='bottom',
                            y=1.02,
                            xanchor='right',
                            x=1
                        )
                    )
                    
                    charts['ma200'] = plot(fig_ma200, output_type='div', include_plotlyjs=False)
                except Exception as e:
                    print(f"MA200チャート生成エラー: {str(e)}")
                    charts['ma200'] = ""  # エラー時は空文字列を設定
            else:
                print("MA200カテゴリが見つかりません")
                charts['ma200'] = ""
        else:
            print("MA分析データが取得できませんでした")
            charts['ma200'] = ""
        
        # MA50も同様に処理
        if ma_data is not None and not ma_data.empty:
            if 'ma50_category' in ma_data.columns:
                try:
                    # ... MA50のチャート生成コード ...
                    ma50_stats = ma_data.groupby('ma50_category').agg({
                        'pnl_rate': ['mean', 'count'],
                        'pnl': lambda x: (x > 0).mean() * 100
                    }).round(2)
                    
                    fig_ma50 = go.Figure()
                    fig_ma50.add_trace(go.Bar(
                        x=ma50_stats.index,
                        y=ma50_stats[('pnl_rate', 'mean')],
                        name=self.get_text('average_return'),
                        text=ma50_stats[('pnl_rate', 'mean')].apply(lambda x: f'{x:.1f}%'),
                        textposition='auto',
                        marker_color=[
                            self.DARK_THEME['profit_color'] if x > 0 
                            else self.DARK_THEME['loss_color'] 
                            for x in ma50_stats[('pnl_rate', 'mean')]
                        ]
                    ))
                    
                    # 勝率のライン
                    fig_ma50.add_trace(go.Scatter(
                        x=ma50_stats.index,
                        y=ma50_stats[('pnl', '<lambda>')],
                        name=self.get_text('win_rate'),
                        yaxis='y2',
                        line=dict(color=self.DARK_THEME['line_color'])
                    ))
                    
                    fig_ma50.update_layout(
                        title=self.get_text('ma50_analysis'),
                        xaxis_title=self.get_text('ma50_category'),
                        yaxis_title=self.get_text('return_pct'),
                        yaxis2=dict(
                            title=self.get_text('win_rate'),
                            overlaying='y',
                            side='right',
                            range=[0, 100]
                        ),
                        template='plotly_dark',
                        paper_bgcolor=self.DARK_THEME['bg_color'],
                        plot_bgcolor=self.DARK_THEME['plot_bg_color'],
                        showlegend=True,
                        legend=dict(
                            orientation='h',
                            yanchor='bottom',
                            y=1.02,
                            xanchor='right',
                            x=1
                        )
                    )
                    
                    charts['ma50'] = plot(fig_ma50, output_type='div', include_plotlyjs=False)
                except Exception as e:
                    print(f"MA50チャート生成エラー: {str(e)}")
                    charts['ma50'] = ""
            else:
                print("MA50カテゴリが見つかりません")
                charts['ma50'] = ""
        else:
            charts['ma50'] = ""
        
        return charts

    def _calculate_trend_data(self, df):
        """決算前のトレンドデータを計算"""
        trends = []
        for _, trade in df.iterrows():
            # 決算前の株価データを取得
            pre_earnings_start = (pd.to_datetime(trade['entry_date']) - 
                                timedelta(days=30)).strftime('%Y-%m-%d')
            stock_data = self.get_historical_data(
                trade['ticker'],
                pre_earnings_start,
                trade['entry_date']
            )
            
            if stock_data is not None and len(stock_data) >= 20:
                # 21日移動平均線を計算
                stock_data['MA21'] = stock_data['Close'].rolling(window=21).mean()
                
                # 20日間の価格変化率を計算
                price_change = ((stock_data['Close'].iloc[-1] - stock_data['Close'].iloc[-20]) / 
                              stock_data['Close'].iloc[-20] * 100)
                
                # 20日移動平均との位置関係
                ma_position = 'above' if stock_data['Close'].iloc[-1] > stock_data['MA21'].iloc[-1] else 'below'
                
                trends.append({
                    'ticker': trade['ticker'],
                    'entry_date': trade['entry_date'],
                    'pre_earnings_change': price_change,
                    'ma_position': ma_position,
                    'pnl_rate': trade['pnl_rate'],
                    'pnl': trade['pnl']  # pnlを追加
                })
        
        trend_df = pd.DataFrame(trends)
        
        if not trend_df.empty:
            # トレンドの強さでビンを作成
            trend_df['trend_bin'] = pd.cut(trend_df['pre_earnings_change'],
                                         bins=[-np.inf, -20, -10, 0, 10, 20, np.inf],
                                         labels=['<-20%', '-20~-10%', '-10~0%', '0~10%', '10~20%', '>20%'])
            
            # トレンド別の統計
            trend_stats = trend_df.groupby('trend_bin').agg({
                'pnl_rate': ['mean', 'std', 'count']
            }).round(2)
            
            print("\nトレンド別パフォーマンス:")
            for trend_bin in trend_stats.index:
                stats = trend_stats.loc[trend_bin]
                print(f"\n{trend_bin}:")
                print(f"- 平均リターン: {stats[('pnl_rate', 'mean')]:.2f}%")
                print(f"- 標準偏差: {stats[('pnl_rate', 'std')]:.2f}%")
                print(f"- トレード数: {stats[('pnl_rate', 'count')]}")
        
        return trend_df  # DataFrameを返す

    def _analyze_breakout_performance(self, df):
        """ブレイクアウトパターンの分析"""
        print("\n=== ブレイクアウトパターン分析 ===")
        
        breakouts = []
        for _, trade in df.iterrows():
            # 決算前の株価データを取得
            pre_earnings_start = (pd.to_datetime(trade['entry_date']) - 
                                timedelta(days=60)).strftime('%Y-%m-%d')
            stock_data = self.get_historical_data(
                trade['ticker'],
                pre_earnings_start,
                trade['entry_date']
            )
            
            if stock_data is not None and len(stock_data) >= 20:
                # 20日高値を計算
                high_20d = stock_data['High'].rolling(window=20).max().iloc[-2]  # 直前日までの20日高値
                
                # ブレイクアウトの判定
                is_breakout = trade['entry_price'] > high_20d
                breakout_percent = ((trade['entry_price'] - high_20d) / high_20d * 100) if is_breakout else 0
                
                breakouts.append({
                    'ticker': trade['ticker'],
                    'entry_date': trade['entry_date'],
                    'is_breakout': is_breakout,
                    'breakout_percent': breakout_percent,
                    'pnl_rate': trade['pnl_rate']
                })
        
        breakout_df = pd.DataFrame(breakouts)
        
        # ブレイクアウトの有無による統計
        breakout_stats = breakout_df.groupby('is_breakout').agg({
            'pnl_rate': ['mean', 'std', 'count']
        }).round(2)
        
        # ブレイクアウトの大きさによる分析
        breakout_df['breakout_bin'] = pd.cut(breakout_df['breakout_percent'],
                                            bins=[-np.inf, 0, 2, 5, 10, np.inf],
                                            labels=['No Breakout', '0-2%', '2-5%', '5-10%', '>10%'])
        
        size_stats = breakout_df.groupby('breakout_bin').agg({
            'pnl_rate': ['mean', 'std', 'count']
        }).round(2)
        
        print("\nブレイクアウトパターン別パフォーマンス:")
        for breakout_bin in size_stats.index:
            stats = size_stats.loc[breakout_bin]
            print(f"\n{breakout_bin}:")
            print(f"- 平均リターン: {stats[('pnl_rate', 'mean')]:.2f}%")
            print(f"- 標準偏差: {stats[('pnl_rate', 'std')]:.2f}%")
            print(f"- トレード数: {stats[('pnl_rate', 'count')]}")

    def _analyze_ma_position(self, df):
        """移動平均線に対する株価の位置を分析"""
        ma_positions = []
        
        print(f"\n移動平均線分析を開始... 処理対象件数: {len(df)}")
        
        for _, trade in df.iterrows():
            try:
                print(f"\n処理中: {trade['ticker']}")
                
                # 決算前250日間のデータを取得(200日MAの計算のため)
                entry_date = pd.to_datetime(trade['entry_date'])
                pre_earnings_start = (entry_date - timedelta(days=300)).strftime('%Y-%m-%d')
                
                # 未来の日付の場合は現在の日付を使用
                current_date = datetime.now()
                if entry_date > current_date:
                    print(f"警告: 未来の日付({entry_date.strftime('%Y-%m-%d')})が指定されています。現在の日付を使用します。")
                    entry_date = current_date
                
                print(f"データ取得期間: {pre_earnings_start} から {entry_date.strftime('%Y-%m-%d')}")
                
                stock_data = self.get_historical_data(
                    trade['ticker'],
                    pre_earnings_start,
                    entry_date.strftime('%Y-%m-%d')
                )
                
                print(f"データ取得結果: {stock_data is not None}")
                if stock_data is not None:
                    print(f"データ件数: {len(stock_data)}")
                
                if stock_data is not None and len(stock_data) >= 200:
                    # 移動平均線を計算
                    stock_data['MA200'] = stock_data['Close'].rolling(window=200).mean()
                    stock_data['MA50'] = stock_data['Close'].rolling(window=50).mean()
                    
                    # 最新の株価と移動平均線の位置関係を計算
                    latest_close = stock_data['Close'].iloc[-1]
                    latest_ma200 = stock_data['MA200'].iloc[-1]
                    latest_ma50 = stock_data['MA50'].iloc[-1]
                    
                    print(f"最新の株価: ${latest_close:.2f}")  # デバッグログ追加
                    print(f"MA200: ${latest_ma200:.2f}")  # デバッグログ追加
                    print(f"MA50: ${latest_ma50:.2f}")  # デバッグログ追加
                    
                    # MA200に対する位置のカテゴリ分類
                    ma200_diff = (latest_close - latest_ma200) / latest_ma200 * 100
                    if ma200_diff > 30:
                        ma200_category = 'Very Far Above MA200 (>30%)'
                    elif ma200_diff > 15:
                        ma200_category = 'Far Above MA200 (15-30%)'
                    elif ma200_diff > 0:
                        ma200_category = 'Above MA200 (0-15%)'
                    elif ma200_diff > -15:
                        ma200_category = 'Below MA200 (-15-0%)'
                    else:
                        ma200_category = 'Very Far Below MA200 (<-15%)'
                    
                    # MA50に対する位置のカテゴリ分類
                    ma50_diff = (latest_close - latest_ma50) / latest_ma50 * 100
                    if ma50_diff > 20:
                        ma50_category = 'Very Far Above MA50 (>20%)'
                    elif ma50_diff > 10:
                        ma50_category = 'Far Above MA50 (10-20%)'
                    elif ma50_diff > 0:
                        ma50_category = 'Above MA50 (0-10%)'
                    elif ma50_diff > -10:
                        ma50_category = 'Below MA50 (-10-0%)'
                    else:
                        ma50_category = 'Very Far Below MA50 (<-10%)'
                    
                    ma_positions.append({
                        'ticker': trade['ticker'],
                        'entry_date': trade['entry_date'],
                        'ma200_category': ma200_category,
                        'ma50_category': ma50_category,
                        'pnl_rate': trade['pnl_rate'],
                        'pnl': trade['pnl']
                    })
                    print(f"銘柄 {trade['ticker']} の分析完了")
                    
                else:
                    print(f"十分なヒストリカルデータがありません")
                    
            except Exception as e:
                print(f"エラー（{trade['ticker']}）: {str(e)}")
                continue
        
        result_df = pd.DataFrame(ma_positions)
        print(f"\n分析完了: {len(result_df)}件")
        
        # データが存在する場合のみカテゴリを設定
        if not result_df.empty:
            print(f"カラム: {result_df.columns.tolist()}")
            
            # MA200カテゴリに順序を設定
            if 'ma200_category' in result_df.columns:
                result_df['ma200_category'] = pd.Categorical(
                    result_df['ma200_category'],
                    categories=[
                        'Very Far Below MA200 (<-15%)',
                        'Below MA200 (-15-0%)',
                        'Above MA200 (0-15%)',
                        'Far Above MA200 (15-30%)',
                        'Very Far Above MA200 (>30%)'
                    ],
                    ordered=True
                )
            
            # MA50カテゴリに順序を設定
            if 'ma50_category' in result_df.columns:
                result_df['ma50_category'] = pd.Categorical(
                    result_df['ma50_category'],
                    categories=[
                        'Very Far Below MA50 (<-10%)',
                        'Below MA50 (-10-0%)',
                        'Above MA50 (0-10%)',
                        'Far Above MA50 (10-20%)',
                        'Very Far Above MA50 (>20%)'
                    ],
                    ordered=True
                )
        
        return result_df

    def _generate_metrics_html(self, df):
        """メトリクスカードのHTML生成"""
        metrics = self.calculate_metrics()
        
        metrics_html = f"""
            <div class="metric-card">
                <h3>{self.get_text('backtest_period')}</h3>
                <div class="metric-value" style="font-size: 20px;">
                    <div>From: {self.start_date}</div>
                    <div>To: {self.end_date}</div>
                </div>
            </div>
            <div class="metric-card">
                <h3>{self.get_text('total_trades')}</h3>
                <div class="metric-value">{metrics['number_of_trades']}</div>
            </div>
            <div class="metric-card">
                <h3>CAGR</h3>
                <div class="metric-value">{metrics['cagr']:.2f}%</div>
            </div>
            <div class="metric-card">
                <h3>{self.get_text('win_rate')}</h3>
                <div class="metric-value">{metrics['win_rate']:.1f}%</div>
            </div>
            <div class="metric-card">
                <h3>{self.get_text('avg_pnl')}</h3>
                <div class="metric-value">{metrics['avg_win_loss_rate']:.2f}%</div>
            </div>
            <div class="metric-card">
                <h3>{self.get_text('profit_factor')}</h3>
                <div class="metric-value">{metrics['profit_factor']:.2f}</div>
            </div>
            <div class="metric-card">
                <h3>{self.get_text('max_drawdown')}</h3>
                <div class="metric-value">{metrics['max_drawdown_pct']:.2f}%</div>
            </div>
            <div class="metric-card">
                <h3>{self.get_text('total_return')}</h3>
                <div class="metric-value">{metrics['total_return_pct']:.2f}%</div>
            </div>
            <div class="metric-card">
                <h3>{self.get_text('expected_value')}</h3>
                <div class="metric-value">{metrics['expected_value_pct']:.2f}%</div>
            </div>
            <div class="metric-card">
                <h3>{self.get_text('calmar_ratio')}</h3>
                <div class="metric-value">{metrics['calmar_ratio']:.2f}</div>
            </div>
            <div class="metric-card">
                <h3>{self.get_text('pareto_ratio')}</h3>
                <div class="metric-value">{metrics['pareto_ratio']:.1f}%</div>
            </div>
        """
        
        return metrics_html

    def _generate_trades_table_html(self):
        """トレード履歴テーブルのHTML生成"""
        rows = []
        df = pd.DataFrame(self.trades).sort_values('entry_date', ascending=False)
        
        for _, trade in df.iterrows():
            pnl_class = 'profit' if trade['pnl'] >= 0 else 'loss'
            holding_period = f"{trade['holding_period']}{self.get_text('days')}"
            
            row = f"""
                <tr>
                    <td>{trade['ticker']}</td>
                    <td>{pd.to_datetime(trade['entry_date']).strftime('%Y-%m-%d')}</td>
                    <td>${trade['entry_price']:.2f}</td>
                    <td>{pd.to_datetime(trade['exit_date']).strftime('%Y-%m-%d')}</td>
                    <td>${trade['exit_price']:.2f}</td>
                    <td>{holding_period}</td>
                    <td>{trade['shares']}</td>
                    <td class="{pnl_class}">{trade['pnl_rate']:.2f}%</td>
                    <td class="{pnl_class}">${trade['pnl']:.2f}</td>
                    <td>{trade['exit_reason']}</td>
                </tr>
            """
            rows.append(row)
        
        table = f"""
            <table class="trades-table">
                <thead>
                    <tr>
                        <th>{self.get_text('symbol')}</th>
                        <th>{self.get_text('entry_date')}</th>
                        <th>{self.get_text('entry_price')}</th>
                        <th>{self.get_text('exit_date')}</th>
                        <th>{self.get_text('exit_price')}</th>
                        <th>{self.get_text('holding_period')}</th>
                        <th>{self.get_text('shares')}</th>
                        <th>{self.get_text('pnl_rate')}</th>
                        <th>{self.get_text('pnl')}</th>
                        <th>{self.get_text('exit_reason')}</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
        """
        
        return table

    def get_market_cap(self, symbol):
        """EODHDから時価総額を取得"""
        try:
            url = f"https://eodhd.com/api/fundamentals/{symbol}.US"
            params = {'api_token': self.api_key}
            
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                market_cap = data.get('Highlights', {}).get('MarketCapitalization')
                if market_cap:
                    return float(market_cap)
            return None
            
        except Exception as e:
            print(f"時価総額の取得エラー ({symbol}): {str(e)}")
            return None

    def _analyze_volume_trend(self, df):
        """決算前の出来高トレンドを分析"""
        volume_trends = []
        
        for _, trade in df.iterrows():
            # 決算前90日間のデータを取得(60日平均と20日平均の比較のため)
            pre_earnings_start = (pd.to_datetime(trade['entry_date']) - 
                                timedelta(days=90)).strftime('%Y-%m-%d')
            stock_data = self.get_historical_data(
                trade['ticker'],
                pre_earnings_start,
                trade['entry_date']
            )
            
            if stock_data is not None and len(stock_data) >= 60:
                # 直近20日と過去60日の平均出来高を計算
                recent_volume = stock_data['Volume'].tail(20).mean()
                historical_volume = stock_data['Volume'].tail(60).mean()
                
                # 出来高変化率を計算
                volume_change = ((recent_volume - historical_volume) / 
                               historical_volume * 100)
                
                # 変化率に基づいてカテゴリ分類（5段階）
                if volume_change >= 100:
                    volume_category = 'Very Large Increase (>100%)'
                elif volume_change >= 50:
                    volume_category = 'Large Increase (50-100%)'
                elif volume_change >= 20:
                    volume_category = 'Moderate Increase (20-50%)'
                elif volume_change >= -20:
                    volume_category = 'Neutral (-20-20%)'
                else:
                    volume_category = 'Decrease (<-20%)'
                
                volume_trends.append({
                    'ticker': trade['ticker'],
                    'entry_date': trade['entry_date'],
                    'volume_change': volume_change,
                    'volume_category': volume_category,
                    'pnl_rate': trade['pnl_rate'],
                    'pnl': trade['pnl']  # pnlを追加
                })
        
        return pd.DataFrame(volume_trends)

def main():
    parser = argparse.ArgumentParser(description='決算スイングトレードのバックテスト')
    parser.add_argument('--start_date', help='開始日 (YYYY-MM-DD形式。未指定の場合、終了日から1ヶ月前の日付)')
    parser.add_argument('--end_date', help='終了日 (YYYY-MM-DD形式。未指定の場合、現在の日付)')
    parser.add_argument('--stop_loss', type=float, default=6,
                      help='ストップロス率 (デフォルト: 6%)')
    parser.add_argument('--trail_stop_ma', type=int, default=21,
                      help='トレーリングストップのMA期間 (デフォルト: 21日)')
    parser.add_argument('--max_holding_days', type=int, default=90,
                      help='最大保有期間 (デフォルト: 90日)')
    parser.add_argument('--initial_capital', type=float, default=100000,
                      help='初期資金 (デフォルト: 10000)')
    parser.add_argument('--position_size', type=float, default=6,
                      help='ポジションサイズ (デフォルト: 6%)')
    parser.add_argument('--slippage', type=float, default=0.3,
                      help='スリッページ (デフォルト: 0.3%)')
    parser.add_argument('--risk_limit', type=float, default=6,
                      help='リスク管理の損益率制限 (デフォルト: 6%)')
    parser.add_argument('--no_partial_profit', action='store_true',
                      help='初日の部分利確を無効にする（デフォルト: 有効）')
    parser.add_argument('--sp500_only', action='store_true',
                      help='S&P 500銘柄のみを対象にする（デフォルト: False）')
    parser.add_argument('--no_mid_small_only', action='store_true',
                      help='中小型株のみを対象にしない（デフォルト: 中小型株のみ対象）')
    parser.add_argument('--language', choices=['ja', 'en'], default='en',
                      help='レポートの言語 (デフォルト: 英語)')
    parser.add_argument('--pre_earnings_change', type=float, default=0,
                      help='過去20日間の価格変化率の閾値 (デフォルト: 0%)')
    
    args = parser.parse_args()
    
    # 現在の日付を取得
    current_date = datetime.now()
    
    # まずend_dateを決定
    if args.end_date:
        end_date = args.end_date
    else:
        end_date = current_date.strftime('%Y-%m-%d')
    
    # 次にstart_dateを決定
    if args.start_date:
        start_date = args.start_date
    else:
        # end_dateから1ヶ月前を計算
        end_date_dt = datetime.strptime(end_date, '%Y-%m-%d')
        start_date = (end_date_dt - timedelta(days=30)).strftime('%Y-%m-%d')

    backtest = EarningsBacktest(
        start_date=start_date,
        end_date=end_date,
        stop_loss=args.stop_loss,
        trail_stop_ma=args.trail_stop_ma,
        max_holding_days=args.max_holding_days,
        initial_capital=args.initial_capital,
        position_size=args.position_size,
        slippage=args.slippage,
        risk_limit=args.risk_limit,
        partial_profit=not args.no_partial_profit,
        sp500_only=args.sp500_only,
        mid_small_only=not args.no_mid_small_only,  # デフォルトでTrue
        language=args.language,
        pre_earnings_change=args.pre_earnings_change
    )
    
    backtest.execute_backtest()
    backtest.generate_report()
    backtest.generate_html_report()
    
    # 詳細分析の実行
    # backtest.analyze_performance()

if __name__ == '__main__':
    main() 
