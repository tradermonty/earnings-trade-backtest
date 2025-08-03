import pandas as pd
from datetime import datetime, timedelta, time
from collections import defaultdict
from typing import Dict, List, Any, Optional, Set
from tqdm import tqdm

from .data_fetcher import DataFetcher
from .earnings_date_validator import EarningsDateValidator
from .news_fetcher import NewsFetcher


class DataFilter:
    """データフィルタリングクラス"""
    
    def __init__(self, data_fetcher: DataFetcher, target_symbols: Optional[Set[str]] = None,
                 min_surprise_percent: float = 5.0, require_positive_eps: bool = True,
                 pre_earnings_change: float = -10, max_holding_days: int = 90,
                 max_gap_percent: float = 10.0,
                 max_ps_ratio: float | None = None, max_pe_ratio: float | None = None,
                 min_profit_margin: float | None = None,
                 enable_date_validation: bool = False, api_key: str = None):
        """DataFilterの初期化"""
        self.data_fetcher = data_fetcher
        self.target_symbols = target_symbols
        self.pre_earnings_change = pre_earnings_change
        self.min_surprise_percent = min_surprise_percent
        self.require_positive_eps = require_positive_eps
        self.max_holding_days = max_holding_days
        self.enable_date_validation = enable_date_validation
        self.max_gap_percent = max_gap_percent

        # Fundamental ratio thresholds
        self.max_ps_ratio = max_ps_ratio
        self.max_pe_ratio = max_pe_ratio
        self.min_profit_margin = min_profit_margin

        # FMPスクリーナーは EarningsBacktest 側で実行し、target_symbols に反映済み
        
        # 決算日検証機能の初期化
        self.earnings_validator = None
        if enable_date_validation and api_key:
            try:
                news_fetcher = NewsFetcher(api_key)
                self.earnings_validator = EarningsDateValidator(news_fetcher)
                print("決算日検証機能が有効化されました")
            except Exception as e:
                print(f"決算日検証機能の初期化に失敗: {e}")
                self.enable_date_validation = False
    
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
        print(f"2. サプライズ率{self.min_surprise_percent}%以上")
        if self.require_positive_eps:
            print("3. 実績値がプラス")
        else:
            print("3. 実績値は不問")
        if self.target_symbols:
            print("4. 指定銘柄のみ (FMPスクリーナー等で抽出済み)")
        
        first_filtered = []
        skipped_count = 0
        
        # tqdmを使用してプログレスバーを表示
        for earning in tqdm(earnings, desc="第1段階フィルタリング"):
            try:
                # 1. .US銘柄のチェック
                if not earning['code'].endswith('.US'):
                    skipped_count += 1
                    continue
                
                # シンボルを取得 (.USを除去)
                symbol = earning['code'][:-3]

                # ターゲットシンボルのフィルタリング
                if self.target_symbols is not None and symbol not in self.target_symbols:
                    skipped_count += 1
                    continue
                
                # 2&3. サプライズ率と実績値のチェック
                try:
                    percent = float(earning.get('percent', 0))
                    actual = float(earning.get('actual', 0))
                except (ValueError, TypeError):
                    skipped_count += 1
                    continue
                
                if percent < self.min_surprise_percent:
                    skipped_count += 1
                    continue
                if self.require_positive_eps and actual <= 0:
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
        print(f"8. ギャップ上限: {self.max_gap_percent}% 以下")
        
        date_stocks = defaultdict(list)
        processed_count = 0
        skipped_count = 0
        
        # tqdmを使用してプログレスバーを表示
        for earning in tqdm(first_filtered, desc="第2段階フィルタリング"):
            try:
                # 決算日の検証（有効化されている場合）
                validated_earning = self._validate_and_adjust_earnings_date(earning)
                
                market_timing = validated_earning.get('before_after_market')
                trade_date = self.determine_trade_date(
                    validated_earning['report_date'], 
                    market_timing
                )
                
                # 銘柄コードから.USを除去
                symbol = earning['code'][:-3]

                # --- Fundamental ratio filter --------------------------------------
                if any([self.max_ps_ratio, self.max_pe_ratio, self.min_profit_margin]) and getattr(self.data_fetcher, 'fmp_fetcher', None):
                    ratios = self.data_fetcher.fmp_fetcher.get_latest_financial_ratios(symbol)
                    if ratios is None:
                        skipped_count += 1
                        tqdm.write(f"- スキップ: Financial ratios 取得失敗")
                        continue
                    ps = ratios.get('priceToSalesRatio')
                    pe = ratios.get('priceToEarningsRatio')
                    npm = ratios.get('netProfitMargin')
                    npm_pct = npm * 100 if npm is not None else None
                    cond = True
                    if self.max_ps_ratio is not None and (ps is None or ps > self.max_ps_ratio):
                        cond = False
                    if self.max_pe_ratio is not None and (pe is None or pe > self.max_pe_ratio):
                        cond = False
                    if self.min_profit_margin is not None and (npm_pct is None or npm_pct < self.min_profit_margin):
                        cond = False
                    if not cond:
                        skipped_count += 1
                        tqdm.write("- スキップ: ファンダメンタル条件未達")
                        continue
                
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

                # トレード日のデータを取得
                trade_result = self._get_trade_date_data(
                    stock_data, trade_date, symbol
                )
                if trade_result is None:
                    skipped_count += 1
                    continue
                
                trade_date_data, prev_day_data, _ = trade_result

                # --- Intraday gap using pre-open price (09:25 ET) ---
                pre_open_price = self.data_fetcher.get_preopen_price(symbol, trade_date)
                if pre_open_price is None:
                    skipped_count += 1
                    tqdm.write(f"- スキップ: プレオープン価格取得失敗 ({symbol} {trade_date})")
                    continue
                gap = (pre_open_price - prev_day_data['Close']) / prev_day_data['Close'] * 100

                # 平均出来高を計算
                avg_volume = stock_data['Volume'].tail(20).mean()
                
                tqdm.write(f"- ギャップ率: {gap:.1f}% (pre-open)")
                tqdm.write(f"- 株価: ${trade_date_data['Open']:.2f}")
                tqdm.write(f"- 平均出来高: {avg_volume:,.0f}")
                
                # フィルタリング条件のチェック
                if not self._check_final_conditions(gap, trade_date_data['Open'], avg_volume):
                    skipped_count += 1
                    continue
                
                # データを保存
                stock_info = {
                    'code': symbol,
                    'report_date': earning['report_date'],
                    'trade_date': trade_date,
                    'price': trade_date_data['Open'],
                    'entry_price': trade_date_data['Open'],
                    'prev_close': prev_day_data['Close'],
                    'gap': gap,
                    'volume': trade_date_data['Volume'],
                    'avg_volume': avg_volume,
                    'percent': float(earning['percent'])
                }
                
                date_stocks[trade_date].append(stock_info)
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
        if gap > self.max_gap_percent:
            tqdm.write(f"- スキップ: ギャップ率が{self.max_gap_percent}%を超過")
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
    
    def _validate_and_adjust_earnings_date(self, earning: Dict) -> Dict:
        """決算日を検証し、必要に応じて調整"""
        if not self.enable_date_validation or not self.earnings_validator:
            return earning
        
        try:
            symbol = earning['code'][:-3]  # .USを除去
            
            # 決算日を検証
            validation_result = self.earnings_validator.validate_earnings_date(
                symbol, 
                earning['report_date']
            )
            
            # 信頼度が一定以上の場合は決算日を調整
            confidence_threshold = 0.6
            if validation_result['confidence'] >= confidence_threshold:
                if validation_result['date_changed']:
                    tqdm.write(f"- 決算日調整: {earning['report_date']} → {validation_result['actual_date']} (信頼度: {validation_result['confidence']:.2f})")
                    
                    # 元の日付を保存
                    earning_copy = earning.copy()
                    earning_copy['original_report_date'] = earning['report_date']
                    earning_copy['report_date'] = validation_result['actual_date']
                    earning_copy['date_validation'] = validation_result
                    
                    return earning_copy
                else:
                    tqdm.write(f"- 決算日確認: {earning['report_date']} (信頼度: {validation_result['confidence']:.2f})")
            else:
                tqdm.write(f"- 決算日検証: 信頼度不足 ({validation_result['confidence']:.2f}), EODHDの日付を使用")
            
            # 検証結果を記録（調整しない場合も）
            earning_copy = earning.copy()
            earning_copy['date_validation'] = validation_result
            return earning_copy
            
        except Exception as e:
            tqdm.write(f"- 決算日検証エラー: {e}")
            return earning