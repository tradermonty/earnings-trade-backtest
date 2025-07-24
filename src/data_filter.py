import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any, Optional, Set
from tqdm import tqdm

from .data_fetcher import DataFetcher


class DataFilter:
    """データフィルタリングクラス"""
    
    def __init__(self, data_fetcher: DataFetcher, target_symbols: Optional[Set[str]] = None, 
                 pre_earnings_change: float = -10, max_holding_days: int = 90):
        """DataFilterの初期化"""
        self.data_fetcher = data_fetcher
        self.target_symbols = target_symbols
        self.pre_earnings_change = pre_earnings_change
        self.max_holding_days = max_holding_days
    
    def determine_trade_date(self, report_date: str, market_timing: str) -> str:
        """決算発表タイミングに基づいてトレード日を決定"""
        base_date = datetime.strptime(report_date, '%Y-%m-%d')
        
        if market_timing and 'Before' in market_timing:
            # 開始前なら当日にトレード
            return base_date.strftime('%Y-%m-%d')
        else:
            # 終了後または不明な場合は翌日にトレード
            trade_date = base_date + timedelta(days=1)
            return trade_date.strftime('%Y-%m-%d')
    
    def filter_earnings_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """決算データのフィルタリング処理"""
        if 'earnings' not in data:
            raise KeyError("JSONデータに'earnings'キーが存在しません")
        
        total_records = len(data['earnings'])
        print(f"\nフィルタリング処理を開始 (全{total_records}件)")
        
        # 第1段階のフィルタリング
        first_filtered = self._first_stage_filter(data['earnings'])
        
        # 第2段階のフィルタリング
        selected_stocks = self._second_stage_filter(first_filtered)
        
        return selected_stocks
    
    def _first_stage_filter(self, earnings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """第1段階フィルタリング：基本条件でのフィルタリング"""
        print("\n=== 第1段階フィルタリング ===")
        print("条件:")
        print("1. .US銘柄のみ")
        print("2. サプライズ率5%以上")
        print("3. 実績値がプラス")
        if self.target_symbols:
            print("4. 指定銘柄のみ")
        
        first_filtered = []
        skipped_count = 0
        
        # tqdmを使用してプログレスバーを表示
        for earning in tqdm(earnings, desc="第1段階フィルタリング"):
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
        print(f"- 処理件数: {len(earnings)}")
        print(f"- 条件適合: {len(first_filtered)}")
        print(f"- スキップ: {skipped_count}")
        
        return first_filtered
    
    def _second_stage_filter(self, first_filtered: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """第2段階フィルタリング：株価・出来高・その他条件でのフィルタリング"""
        print("\n=== 第2段階フィルタリング ===")
        print("条件:")
        print("4. ギャップ率0%以上")
        print("5. 株価10ドル以上")
        print("6. 20日平均出来高20万株以上")
        print(f"7. 過去20日間の価格変化率{self.pre_earnings_change}%以上")
        
        date_stocks = defaultdict(list)
        processed_count = 0
        skipped_count = 0
        
        # tqdmを使用してプログレスバーを表示
        for earning in tqdm(first_filtered, desc="第2段階フィルタリング"):
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
                stock_data = self.data_fetcher.get_historical_data(
                    symbol,
                    (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=60)).strftime("%Y-%m-%d"),
                    (datetime.strptime(trade_date, "%Y-%m-%d") + 
                     timedelta(days=self.max_holding_days + 30)).strftime("%Y-%m-%d")
                )
                
                if stock_data is None or stock_data.empty:
                    tqdm.write("- スキップ: 株価データなし")
                    skipped_count += 1
                    continue

                # DataFrameのカラム名を統一（'close'を'Close'に）
                if 'close' in stock_data.columns:
                    stock_data = stock_data.rename(columns={
                        'open': 'Open', 'high': 'High', 'low': 'Low', 
                        'close': 'Close', 'volume': 'Volume'
                    })
                
                # 日付をインデックスに設定
                stock_data = stock_data.set_index('date')

                # 過去20日間の価格変化率を計算
                price_change_passed = self._check_price_change(
                    stock_data, trade_date, symbol
                )
                if not price_change_passed:
                    skipped_count += 1
                    continue

                # トレード日のデータを取得（ギャップアップ検証強化版）
                trade_result = self._get_trade_date_data_with_validation(
                    stock_data, trade_date, symbol, earning
                )
                if trade_result is None:
                    skipped_count += 1
                    continue
                
                trade_date_data, prev_day_data, gap, actual_trade_date = trade_result

                # 平均出来高を計算
                avg_volume = stock_data['Volume'].tail(20).mean()
                
                tqdm.write(f"- ギャップ率: {gap:.1f}%")
                tqdm.write(f"- 株価: ${trade_date_data['Open']:.2f}")
                tqdm.write(f"- 平均出来高: {avg_volume:,.0f}")
                
                # フィルタリング条件のチェック
                if not self._check_final_conditions(gap, trade_date_data['Open'], avg_volume):
                    skipped_count += 1
                    continue
                
                # データを保存（実際のトレード日を使用）
                stock_info = {
                    'code': symbol,
                    'report_date': earning['report_date'],
                    'trade_date': actual_trade_date,  # 検証後の実際のトレード日
                    'price': trade_date_data['Open'],
                    'entry_price': trade_date_data['Open'],
                    'prev_close': prev_day_data['Close'],
                    'gap': gap,
                    'volume': trade_date_data['Volume'],
                    'avg_volume': avg_volume,
                    'percent': float(earning['percent'])
                }
                
                date_stocks[actual_trade_date].append(stock_info)
                processed_count += 1
                tqdm.write("→ 条件適合")
                
            except Exception as e:
                tqdm.write(f"\n銘柄の処理中にエラー ({earning.get('code', 'Unknown')}): {str(e)}")
                skipped_count += 1
                continue
        
        # 各trade_dateで上位5銘柄を選択
        selected_stocks = self._select_top_stocks(date_stocks)
        
        print(f"\n第2段階フィルタリング結果:")
        print(f"- 処理件数: {len(first_filtered)}")
        print(f"- 条件適合: {processed_count}")
        print(f"- スキップ: {skipped_count}")
        print(f"- 最終選択銘柄数: {len(selected_stocks)}")
        
        return selected_stocks
    
    def _check_price_change(self, stock_data: pd.DataFrame, trade_date: str, symbol: str) -> bool:
        """過去20日間の価格変化率をチェック"""
        try:
            current_close = stock_data.loc[:trade_date].iloc[-1]['Close']
            price_20d_ago = stock_data.loc[:trade_date].iloc[-20]['Close']
            price_change = ((current_close - price_20d_ago) / price_20d_ago) * 100
            tqdm.write(f"- 過去20日間の価格変化率: {price_change:.1f}%")
            
            if price_change < self.pre_earnings_change:
                tqdm.write(f"- スキップ: 価格変化率が{self.pre_earnings_change}%未満")
                return False
            return True
            
        except (KeyError, IndexError):
            tqdm.write("- スキップ: 20日分の価格データなし")
            return False
    
    def _get_trade_date_data(self, stock_data: pd.DataFrame, trade_date: str, symbol: str):
        """トレード日のデータを取得"""
        try:
            trade_date_data = stock_data.loc[trade_date]
            prev_day_data = stock_data.loc[:trade_date].iloc[-2]
            
            # ギャップ率を計算
            gap = ((trade_date_data['Open'] - prev_day_data['Close']) / prev_day_data['Close']) * 100
            
            return trade_date_data, prev_day_data, gap
            
        except (KeyError, IndexError):
            tqdm.write("- スキップ: トレード日のデータなし")
            return None
    
    def _check_final_conditions(self, gap: float, price: float, avg_volume: float) -> bool:
        """最終的なフィルタリング条件をチェック"""
        if gap < 0:
            tqdm.write("- スキップ: ギャップ率が負")
            return False
        if price < 10:
            tqdm.write("- スキップ: 株価が10ドル未満")
            return False
        if avg_volume < 200000:
            tqdm.write("- スキップ: 出来高不足")
            return False
        return True
    
    def _select_top_stocks(self, date_stocks: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """各日付で上位5銘柄を選択"""
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
        
        return selected_stocks
    
    def _get_trade_date_data_with_validation(self, stock_data: pd.DataFrame, trade_date: str, 
                                            symbol: str, earning: Dict) -> Optional[tuple]:
        """
        トレード日のデータを取得し、ギャップアップを検証
        EODHDの決算日の問題を考慮し、決算日の翌日と2日後まで検証対象とし、
        最適なギャップアップ日を自動選択する
        """
        try:
            report_date = earning.get('report_date')
            
            # EODHDの日付ずれ問題対策：決算日の翌日と2日後をチェック
            # （EODHDの決算日が実際より1日早い可能性があるため）
            
            # まずEODHDが示すトレード日を確認
            if trade_date not in stock_data.index:
                tqdm.write(f"- トレード日 {trade_date} のデータなし")
                return None
            
            trade_date_idx = stock_data.index.get_loc(trade_date)
            
            # 最大2日先まで検証
            best_trade_data = None
            best_prev_data = None
            best_gap = -100.0  # 最小値で初期化
            best_trade_date = None
            best_day_offset = 0
            
            for day_offset in range(1, 3):  # 1日後と2日後をチェック
                # 検証日が存在しない場合はスキップ
                if trade_date_idx + day_offset >= len(stock_data):
                    continue
                
                # 検証日のデータを取得
                check_day_data = stock_data.iloc[trade_date_idx + day_offset]
                check_date = check_day_data.name.strftime('%Y-%m-%d')
                
                # 前営業日のデータ（ギャップ計算の基準日）
                prev_day_data = stock_data.iloc[trade_date_idx + day_offset - 1]
                
                # ギャップ率を計算
                gap = ((check_day_data['Open'] - prev_day_data['Close']) / 
                       prev_day_data['Close']) * 100
                
                # 出来高の増加をチェック
                volume_increase = check_day_data['Volume'] / prev_day_data['Volume']
                
                tqdm.write(f"- EODHD決算日: {report_date}, 検証日{day_offset}: {check_date}")
                tqdm.write(f"  → ギャップ: {gap:.1f}%, 出来高増加: {volume_increase:.1f}倍")
                
                # ギャップが2%以上かつ出来高が1.2倍以上の場合、候補として保存
                if gap >= 2.0 and volume_increase >= 1.2:
                    # より良いギャップの日を選択
                    if gap > best_gap:
                        best_trade_data = check_day_data
                        best_prev_data = prev_day_data
                        best_gap = gap
                        best_trade_date = check_date
                        best_day_offset = day_offset
            
            # 条件を満たす日が見つかった場合
            if best_trade_data is not None:
                tqdm.write(f"  → 最適な検証日: {best_trade_date} (決算日+{best_day_offset}日)")
                return best_trade_data, best_prev_data, best_gap, best_trade_date
            
            # 条件を満たす日がない場合、最もギャップの大きい日を返す（後でフィルタされる）
            # 1日後のデータを返す（従来の動作と同じ）
            if trade_date_idx + 1 < len(stock_data):
                actual_trade_day_data = stock_data.iloc[trade_date_idx + 1]
                actual_trade_date = actual_trade_day_data.name.strftime('%Y-%m-%d')
                reported_day_data = stock_data.iloc[trade_date_idx]
                gap = ((actual_trade_day_data['Open'] - reported_day_data['Close']) / 
                       reported_day_data['Close']) * 100
                return actual_trade_day_data, reported_day_data, gap, actual_trade_date
            
            tqdm.write("- スキップ: 検証可能な日のデータなし")
            return None
            
        except Exception as e:
            tqdm.write(f"- エラー: {str(e)}")
            return None