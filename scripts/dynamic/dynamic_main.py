#!/usr/bin/env python3
"""
動的ポジションサイズ統合バックテストシステム
既存のmain.pyを変更せずに動的ポジションサイズ機能を統合

Usage:
    python dynamic_main.py --start_date 2020-09-01 --end_date 2025-06-30 --pattern breadth_8ma
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd

# 既存のsrcモジュールをインポート（importlibを使用してrelative import問題を回避）
import importlib.util

# srcモジュールの動的インポート
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)

def import_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# 各モジュールを個別にインポート
config_module = import_module_from_path("config", os.path.join(src_path, "config.py"))
BacktestConfig = config_module.BacktestConfig

data_fetcher_module = import_module_from_path("data_fetcher", os.path.join(src_path, "data_fetcher.py"))
DataFetcher = data_fetcher_module.DataFetcher

data_filter_module = import_module_from_path("data_filter", os.path.join(src_path, "data_filter.py"))
DataFilter = data_filter_module.DataFilter

risk_manager_module = import_module_from_path("risk_manager", os.path.join(src_path, "risk_manager.py"))
RiskManager = risk_manager_module.RiskManager

trade_executor_module = import_module_from_path("trade_executor", os.path.join(src_path, "trade_executor.py"))
TradeExecutor = trade_executor_module.TradeExecutor

metrics_module = import_module_from_path("metrics_calculator", os.path.join(src_path, "metrics_calculator.py"))
MetricsCalculator = metrics_module.MetricsCalculator

report_module = import_module_from_path("report_generator", os.path.join(src_path, "report_generator.py"))
ReportGenerator = report_module.ReportGenerator

# 動的ポジションサイズモジュールをインポート
scripts_path = os.path.join(os.path.dirname(__file__), 'scripts', 'dynamic_position_size')

breadth_module = import_module_from_path("breadth_manager", os.path.join(scripts_path, "breadth_manager.py"))
MarketBreadthManager = breadth_module.MarketBreadthManager

position_module = import_module_from_path("position_calculator", os.path.join(scripts_path, "position_calculator.py"))
PositionCalculator = position_module.PositionCalculator

dynamic_config_module = import_module_from_path("dynamic_config", os.path.join(scripts_path, "config.py"))
DynamicPositionSizeConfig = dynamic_config_module.DynamicPositionSizeConfig


class DynamicEarningsBacktest:
    """動的ポジションサイズ機能を統合したバックテストシステム"""
    
    def __init__(self, config: BacktestConfig, dynamic_config: Optional[DynamicPositionSizeConfig] = None):
        """
        Args:
            config: 基本バックテスト設定
            dynamic_config: 動的ポジションサイズ設定（Noneの場合は固定サイズ）
        """
        self.config = config
        self.dynamic_config = dynamic_config
        self.use_dynamic_sizing = dynamic_config is not None
        
        # 既存コンポーネントの初期化
        self._validate_dates()
        self._initialize_components()
        
        # 動的ポジションサイズコンポーネント
        if self.use_dynamic_sizing:
            self._initialize_dynamic_components()
        
        # 結果格納用
        self.trades = []
        self.metrics = {}
    
    def _validate_dates(self):
        """日付の妥当性チェック（既存システムと同じ）"""
        current_date = datetime.now()
        end_date_dt = datetime.strptime(self.config.end_date, '%Y-%m-%d')
        
        if end_date_dt > current_date:
            print(f"警告: 終了日({self.config.end_date})が未来の日付です。現在の日付を使用します。")
            self.config.end_date = current_date.strftime('%Y-%m-%d')
    
    def _initialize_components(self):
        """既存コンポーネントの初期化"""
        # データ取得コンポーネント
        self.data_fetcher = DataFetcher(use_fmp=self.config.use_fmp_data)
        self.api_key = self.data_fetcher.api_key
        
        # 銘柄リストの取得
        if self.config.target_symbols:
            self.target_symbols = list(self.config.target_symbols)
        else:
            self.target_symbols = self.data_fetcher.get_target_symbols(
                sp500_only=self.config.sp500_only,
                mid_small_only=self.config.mid_small_only
            )
        
        print(f"対象銘柄数: {len(self.target_symbols)}")
        
        # その他コンポーネント
        self.data_filter = DataFilter(self.config)
        self.risk_manager = RiskManager(self.config)
        self.trade_executor = TradeExecutor(self.config)
        self.metrics_calculator = MetricsCalculator(self.config)
        self.report_generator = ReportGenerator(self.config)
    
    def _initialize_dynamic_components(self):
        """動的ポジションサイズコンポーネントの初期化"""
        try:
            # Market Breadth Manager
            if not os.path.exists(self.dynamic_config.breadth_csv_path):
                raise FileNotFoundError(f"Market Breadth CSV not found: {self.dynamic_config.breadth_csv_path}")
            
            self.breadth_manager = MarketBreadthManager(self.dynamic_config.breadth_csv_path)
            
            # データカバレッジ検証
            coverage = self.breadth_manager.validate_backtest_coverage(
                self.config.start_date, self.config.end_date
            )
            
            if not coverage['covered']:
                raise ValueError(f"Market Breadth data does not cover backtest period: {coverage}")
            
            # Position Calculator
            self.position_calculator = PositionCalculator(self.dynamic_config)
            
            print(f"✅ Dynamic Position Size System initialized:")
            print(f"   Pattern: {self.dynamic_config.position_pattern}")
            print(f"   Description: {self.dynamic_config.get_pattern_description()}")
            print(f"   Data Coverage: {coverage['available_period']}")
            
        except Exception as e:
            print(f"❌ Failed to initialize Dynamic Position Size System: {e}")
            print("   Falling back to fixed position sizing")
            self.use_dynamic_sizing = False
    
    def run_backtest(self):
        """動的ポジションサイズでバックテストを実行"""
        print("=" * 60)
        print("=== Earnings Trade Backtest ===")
        if self.use_dynamic_sizing:
            print(f"=== Dynamic Position Size: {self.dynamic_config.position_pattern} ===")
        else:
            print("=== Fixed Position Size ===")
        print("=" * 60)
        
        print(f"期間: {self.config.start_date} から {self.config.end_date}")
        print(f"初期資金: ${self.config.initial_capital:,.2f}")
        if self.use_dynamic_sizing:
            print(f"ポジションサイズ: 動的調整（{self.dynamic_config.position_pattern}）")
            ranges = self.dynamic_config.get_position_size_ranges()
            print(f"ポジションサイズ範囲: {min(ranges.values()):.1f}% - {max(ranges.values()):.1f}%")
        else:
            print(f"ポジションサイズ: {self.config.position_size:.1f}%")
        print(f"ストップロス: {self.config.stop_loss:.1f}%")
        print("-" * 50)
        
        try:
            # 1. データ取得とフィルタリング
            earnings_data = self._fetch_and_filter_data()
            
            if not earnings_data:
                print("フィルタリング後に銘柄が見つかりませんでした。")
                return
            
            # 2. トレード実行
            self._execute_trades(earnings_data)
            
            # 3. メトリクス計算
            self._calculate_metrics()
            
            # 4. レポート生成
            self._generate_report()
            
        except Exception as e:
            print(f"バックテスト実行中にエラーが発生しました: {e}")
            raise
    
    def _fetch_and_filter_data(self):
        """データ取得とフィルタリング（既存システムと同じ）"""
        print("データを取得しています...")
        
        # Earnings データ取得
        earnings_data = self.data_fetcher.get_earnings_data(
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            symbols=self.target_symbols
        )
        
        print(f"取得したearningsデータ: {len(earnings_data)}件")
        
        if not earnings_data:
            return []
        
        # フィルタリング
        filtered_data = self.data_filter.filter_earnings_data(earnings_data)
        print(f"フィルタリング後の銘柄数: {len(filtered_data)}")
        
        return filtered_data
    
    def _execute_trades(self, earnings_data):
        """トレード実行（動的ポジションサイズ統合）"""
        print("トレードを実行しています...")
        
        for earnings in earnings_data:
            try:
                entry_date = pd.to_datetime(earnings['date'])
                
                # 動的ポジションサイズを計算
                if self.use_dynamic_sizing:
                    position_size = self._calculate_dynamic_position_size(entry_date)
                else:
                    position_size = self.config.position_size
                
                # 一時的にposition_sizeを更新
                original_position_size = self.config.position_size
                self.config.position_size = position_size
                
                # リスクチェック
                if not self.risk_manager.check_risk_limits(self.trades):
                    self.config.position_size = original_position_size
                    continue
                
                # トレード実行
                trade_result = self.trade_executor.execute_trade(earnings)
                
                if trade_result:
                    # 動的ポジションサイズ情報を追加
                    if self.use_dynamic_sizing:
                        market_data = self.breadth_manager.get_market_data(entry_date)
                        trade_result['dynamic_position_size'] = position_size
                        trade_result['original_position_size'] = original_position_size
                        if market_data:
                            trade_result['breadth_8ma'] = market_data['breadth_8ma']
                            trade_result['market_condition'] = self.breadth_manager.get_market_condition(
                                market_data['breadth_8ma']
                            )
                    
                    self.trades.append(trade_result)
                    
                    # 進捗表示
                    if len(self.trades) % 10 == 0:
                        print(f"  実行済みトレード数: {len(self.trades)}")
                
                # position_sizeを元に戻す
                self.config.position_size = original_position_size
                
            except Exception as e:
                print(f"トレード実行中にエラー: {e}")
                continue
        
        print(f"実行されたトレード数: {len(self.trades)}")
    
    def _calculate_dynamic_position_size(self, entry_date: datetime) -> float:
        """動的ポジションサイズを計算"""
        market_data = self.breadth_manager.get_market_data(entry_date)
        
        if market_data:
            position_size, reason = self.position_calculator.calculate_position_size(
                market_data, entry_date
            )
            
            if self.dynamic_config.log_position_changes:
                print(f"  {entry_date.strftime('%Y-%m-%d')}: {position_size:.1f}% ({reason})")
            
            return position_size
        else:
            return self.dynamic_config.default_position_size
    
    def _calculate_metrics(self):
        """メトリクス計算"""
        if not self.trades:
            self.metrics = {}
            return
        
        self.metrics = self.metrics_calculator.calculate_all_metrics(self.trades)
        
        # 動的ポジションサイズ特有のメトリクスを追加
        if self.use_dynamic_sizing and self.trades:
            self._add_dynamic_metrics()
    
    def _add_dynamic_metrics(self):
        """動的ポジションサイズ特有のメトリクスを追加"""
        trades_df = pd.DataFrame(self.trades)
        
        if 'dynamic_position_size' in trades_df.columns:
            self.metrics['dynamic_position_stats'] = {
                'avg_position_size': trades_df['dynamic_position_size'].mean(),
                'min_position_size': trades_df['dynamic_position_size'].min(),
                'max_position_size': trades_df['dynamic_position_size'].max(),
                'std_position_size': trades_df['dynamic_position_size'].std()
            }
            
            # 市場状況別統計
            if 'market_condition' in trades_df.columns:
                condition_stats = trades_df.groupby('market_condition').agg({
                    'dynamic_position_size': ['count', 'mean'],
                    'pnl': ['sum', 'mean']
                }).round(2)
                self.metrics['market_condition_stats'] = condition_stats.to_dict()
    
    def _generate_report(self):
        """レポート生成"""
        if not self.trades:
            print("トレードデータがないため、レポートを生成できません。")
            return
        
        # メトリクス表示
        print("\n" + "=" * 50)
        print("バックテスト完了!")
        print(f"実行されたトレード数: {self.metrics.get('total_trades', 0)}")
        print(f"最終資産: ${self.metrics.get('final_portfolio_value', 0):,.2f}")
        print(f"総リターン: {self.metrics.get('total_return', 0):.2f}%")
        print(f"勝率: {self.metrics.get('win_rate', 0):.1f}%")
        
        if self.use_dynamic_sizing and 'dynamic_position_stats' in self.metrics:
            print(f"\n動的ポジションサイズ統計:")
            stats = self.metrics['dynamic_position_stats']
            print(f"  平均ポジションサイズ: {stats['avg_position_size']:.1f}%")
            print(f"  ポジションサイズ範囲: {stats['min_position_size']:.1f}% - {stats['max_position_size']:.1f}%")
        
        # HTMLレポート生成
        report_filename = self.report_generator.generate_report(self.trades, self.metrics)
        print(f"\n{report_filename}")
        
        # CSVエクスポート（動的ポジションサイズ情報含む）
        if self.use_dynamic_sizing:
            csv_filename = self.report_generator.export_to_csv(
                self.trades, 
                filename_suffix=f"_dynamic_{self.dynamic_config.position_pattern}"
            )
        else:
            csv_filename = self.report_generator.export_to_csv(self.trades)
        
        print(f"{csv_filename}")


def create_dynamic_config(args) -> Optional[DynamicPositionSizeConfig]:
    """コマンドライン引数から動的ポジションサイズ設定を作成"""
    if not args.pattern:
        return None
    
    return DynamicPositionSizeConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        stop_loss=args.stop_loss,
        trail_stop_ma=args.trail_stop_ma,
        max_holding_days=args.max_holding_days,
        initial_capital=args.initial_capital,
        position_size=args.position_size,
        slippage=args.slippage,
        risk_limit=args.risk_limit,
        partial_profit=args.partial_profit,
        sp500_only=args.sp500_only,
        mid_small_only=args.mid_small_only,
        language=args.language,
        pre_earnings_change=args.pre_earnings_change,
        margin_ratio=args.margin_ratio,
        use_fmp_data=args.use_fmp_data,
        enable_earnings_date_validation=args.enable_earnings_date_validation,
        max_gap_percent=args.max_gap_percent,
        max_ps_ratio=args.max_ps_ratio,
        max_pe_ratio=args.max_pe_ratio,
        min_profit_margin=args.min_profit_margin,
        screener_price_min=args.screener_price_min,
        screener_volume_min=args.screener_volume_min,
        min_market_cap=args.min_market_cap,
        max_market_cap=args.max_market_cap,
        
        # 動的ポジションサイズ設定
        position_pattern=args.pattern,
        breadth_csv_path=args.breadth_csv,
        enable_logging=args.enable_logging,
        log_position_changes=args.log_position_changes
    )


def parse_arguments():
    """コマンドライン引数の解析（既存main.pyと同じ + 動的ポジションサイズ）"""
    parser = argparse.ArgumentParser(description='Dynamic Position Size Earnings Backtest')
    
    # 既存のmain.pyと同じ引数
    parser.add_argument('--start_date', type=str, default='2024-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, default='2024-12-31', help='End date (YYYY-MM-DD)')
    parser.add_argument('--stop_loss', type=float, default=6.0, help='Stop loss percentage')
    parser.add_argument('--trail_stop_ma', type=int, default=21, help='Trailing stop MA period')
    parser.add_argument('--max_holding_days', type=int, default=90, help='Maximum holding period')
    parser.add_argument('--initial_capital', type=float, default=100000.0, help='Initial capital')
    parser.add_argument('--position_size', type=float, default=15.0, help='Position size percentage')
    parser.add_argument('--slippage', type=float, default=0.3, help='Slippage percentage')
    parser.add_argument('--risk_limit', type=float, default=6.0, help='Risk limit percentage')
    parser.add_argument('--partial_profit', action='store_true', help='Enable partial profit taking')
    parser.add_argument('--sp500_only', action='store_true', help='Trade S&P 500 stocks only')
    parser.add_argument('--mid_small_only', action='store_true', default=True, help='Trade mid/small cap stocks only')
    parser.add_argument('--language', type=str, default='en', choices=['en', 'ja'], help='Report language')
    parser.add_argument('--pre_earnings_change', type=float, default=0.0, help='Minimum price change before earnings')
    parser.add_argument('--margin_ratio', type=float, default=1.5, help='Margin ratio')
    parser.add_argument('--use_fmp_data', action='store_true', default=True, help='Use Financial Modeling Prep data')
    parser.add_argument('--enable_earnings_date_validation', action='store_true', help='Enable earnings date validation')
    parser.add_argument('--max_gap_percent', type=float, default=10.0, help='Maximum gap percentage')
    parser.add_argument('--max_ps_ratio', type=float, help='Maximum P/S ratio')
    parser.add_argument('--max_pe_ratio', type=float, help='Maximum P/E ratio')
    parser.add_argument('--min_profit_margin', type=float, help='Minimum profit margin')
    parser.add_argument('--screener_price_min', type=float, default=30.0, help='Minimum stock price for screener')
    parser.add_argument('--screener_volume_min', type=int, default=200000, help='Minimum volume for screener')
    parser.add_argument('--min_market_cap', type=float, default=5e9, help='Minimum market cap')
    parser.add_argument('--max_market_cap', type=float, default=50e9, help='Maximum market cap')
    
    # 動的ポジションサイズ専用引数
    parser.add_argument('--pattern', type=str, 
                       choices=['breadth_8ma', 'advanced_5stage', 'bearish_signal', 'bottom_3stage'],
                       help='Dynamic position sizing pattern (if not specified, uses fixed sizing)')
    parser.add_argument('--breadth_csv', type=str, default='data/market_breadth_data_20250817_ma8.csv',
                       help='Market Breadth CSV file path')
    parser.add_argument('--enable_logging', action='store_true', help='Enable detailed logging')
    parser.add_argument('--log_position_changes', action='store_true', help='Log position size changes')
    
    return parser.parse_args()


def main():
    """メイン実行関数"""
    args = parse_arguments()
    
    # 基本設定作成
    config = BacktestConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        stop_loss=args.stop_loss,
        trail_stop_ma=args.trail_stop_ma,
        max_holding_days=args.max_holding_days,
        initial_capital=args.initial_capital,
        position_size=args.position_size,
        slippage=args.slippage,
        risk_limit=args.risk_limit,
        partial_profit=args.partial_profit,
        sp500_only=args.sp500_only,
        mid_small_only=args.mid_small_only,
        language=args.language,
        pre_earnings_change=args.pre_earnings_change,
        margin_ratio=args.margin_ratio,
        use_fmp_data=args.use_fmp_data,
        enable_earnings_date_validation=args.enable_earnings_date_validation,
        max_gap_percent=args.max_gap_percent,
        max_ps_ratio=args.max_ps_ratio,
        max_pe_ratio=args.max_pe_ratio,
        min_profit_margin=args.min_profit_margin,
        screener_price_min=args.screener_price_min,
        screener_volume_min=args.screener_volume_min,
        min_market_cap=args.min_market_cap,
        max_market_cap=args.max_market_cap
    )
    
    # 動的ポジションサイズ設定作成
    dynamic_config = create_dynamic_config(args)
    
    # バックテスト実行
    backtest = DynamicEarningsBacktest(config, dynamic_config)
    backtest.run_backtest()


if __name__ == "__main__":
    main()