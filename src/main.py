"""
リファクタリングされたEarningsBacktestメインクラス
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging

from .config import BacktestConfig, TextConfig
from .data_fetcher import DataFetcher
from .data_filter import DataFilter
from .risk_manager import RiskManager
from .trade_executor import TradeExecutor
from .metrics_calculator import MetricsCalculator
from .report_generator import ReportGenerator


class EarningsBacktest:
    """earnings-based swing trading backtest system"""
    
    def __init__(self, config: BacktestConfig):
        """EarningsBacktestの初期化"""
        self.config = config
        self._validate_dates()
        self._initialize_components()
        
        # 結果格納用
        self.trades = []
        self.metrics = {}
    
    def _validate_dates(self):
        """日付の妥当性チェック"""
        current_date = datetime.now()
        end_date_dt = datetime.strptime(self.config.end_date, '%Y-%m-%d')
        
        if end_date_dt > current_date:
            print(f"警告: 終了日({self.config.end_date})が未来の日付です。現在の日付を使用します。")
            self.config.end_date = current_date.strftime('%Y-%m-%d')
    
    def _initialize_components(self):
        """各コンポーネントの初期化"""
        # データ取得コンポーネント
        self.data_fetcher = DataFetcher(use_fmp=self.config.use_fmp_data)
        
        # API keyをデータフェッチャーから取得
        self.api_key = self.data_fetcher.api_key
        
        # 銘柄リストの取得
        target_symbols = self._get_target_symbols()
        
        # データフィルタリングコンポーネント
        self.data_filter = DataFilter(
            data_fetcher=self.data_fetcher,
            target_symbols=target_symbols,
            pre_earnings_change=self.config.pre_earnings_change,
            max_holding_days=self.config.max_holding_days,
            enable_date_validation=self.config.enable_earnings_date_validation,
            api_key=self.api_key
        )
        
        # リスク管理コンポーネント
        self.risk_manager = RiskManager(risk_limit=self.config.risk_limit)
        
        # トレード実行コンポーネント
        self.trade_executor = TradeExecutor(
            data_fetcher=self.data_fetcher,
            risk_manager=self.risk_manager,
            initial_capital=self.config.initial_capital,
            position_size=self.config.position_size,
            stop_loss=self.config.stop_loss,
            trail_stop_ma=self.config.trail_stop_ma,
            max_holding_days=self.config.max_holding_days,
            slippage=self.config.slippage,
            partial_profit=self.config.partial_profit,
            margin_ratio=self.config.margin_ratio
        )
        
        # メトリクス計算コンポーネント
        self.metrics_calculator = MetricsCalculator(
            initial_capital=self.config.initial_capital
        )
        
        # レポート生成コンポーネント
        self.report_generator = ReportGenerator(
            language=self.config.language,
            data_fetcher=self.data_fetcher
        )
    
    def _get_target_symbols(self) -> Optional[set]:
        """ターゲット銘柄リストを取得"""
        if not (self.config.sp500_only or self.config.mid_small_only):
            return None
        
        symbols = set()
        
        if self.config.sp500_only:
            sp500_symbols = self.data_fetcher.get_sp500_symbols()
            if sp500_symbols:
                symbols.update(sp500_symbols)
        
        if self.config.mid_small_only:
            mid_small_symbols = self.data_fetcher.get_mid_small_symbols(
                use_market_cap_filter=self.config.use_market_cap_filter,
                min_market_cap=self.config.min_market_cap,
                max_market_cap=self.config.max_market_cap
            )
            if mid_small_symbols:
                symbols.update(mid_small_symbols)
        
        return symbols if symbols else None
    
    def execute_backtest(self) -> Dict[str, Any]:
        """バックテストの実行"""
        print("\nバックテストを開始します...")
        print(f"期間: {self.config.start_date} から {self.config.end_date}")
        print(f"初期資金: ${self.config.initial_capital:,.2f}")
        print(f"ポジションサイズ: {self.config.position_size}%")
        print(f"ストップロス: {self.config.stop_loss}%")
        print(f"トレーリングストップMA: {self.config.trail_stop_ma}日")
        print(f"最大保有期間: {self.config.max_holding_days}日")
        print(f"スリッページ: {self.config.slippage}%")
        
        try:
            # 1. 決算データの取得
            print("\n1. 決算データの取得中...")
            earnings_data = self.data_fetcher.get_earnings_data(
                self.config.start_date, 
                self.config.end_date
            )
            
            # 2. データのフィルタリング
            print("\n2. 銘柄のフィルタリング中...")
            trade_candidates = self.data_filter.filter_earnings_data(earnings_data)
            print(f"フィルタリング後の銘柄数: {len(trade_candidates)}")
            
            if not trade_candidates:
                print("フィルタリング後に銘柄が見つかりませんでした。")
                return self._get_empty_results()
            
            # 3. バックテストの実行
            self.trades = self.trade_executor.execute_backtest(trade_candidates)
            
            if not self.trades:
                print("実行されたトレードがありません。")
                return self._get_empty_results()
            
            # 4. メトリクスの計算
            print("\n6. パフォーマンス指標を計算中...")
            self.metrics = self.metrics_calculator.calculate_metrics(self.trades)
            
            # 5. レポートの生成
            self._generate_reports()
            
            return {
                'trades': self.trades,
                'metrics': self.metrics,
                'config': self._get_config_dict()
            }
            
        except Exception as e:
            print(f"バックテスト実行中にエラーが発生: {str(e)}")
            logging.error(f"Backtest execution error: {str(e)}")
            raise
    
    def _get_empty_results(self) -> Dict[str, Any]:
        """空の結果を返す"""
        empty_metrics = self.metrics_calculator.calculate_metrics([])
        return {
            'trades': [],
            'metrics': empty_metrics,
            'config': self._get_config_dict()
        }
    
    def _get_config_dict(self) -> Dict[str, Any]:
        """設定を辞書形式で取得"""
        return {
            'start_date': self.config.start_date,
            'end_date': self.config.end_date,
            'initial_capital': self.config.initial_capital,
            'position_size': self.config.position_size,
            'stop_loss': self.config.stop_loss,
            'trail_stop_ma': self.config.trail_stop_ma,
            'max_holding_days': self.config.max_holding_days,
            'slippage': self.config.slippage,
            'risk_limit': self.config.risk_limit,
            'partial_profit': self.config.partial_profit,
            'sp500_only': self.config.sp500_only,
            'mid_small_only': self.config.mid_small_only,
            'language': self.config.language,
            'pre_earnings_change': self.config.pre_earnings_change,
            'margin_ratio': self.config.margin_ratio
        }
    
    def _generate_reports(self):
        """レポートの生成"""
        if not self.trades:
            print("トレードデータがないため、レポートを生成できません。")
            return
        
        print("\n7. レポートを生成中...")
        
        # 日次ポジションデータを取得
        daily_positions_data = self.trade_executor.get_daily_positions_data()
        
        # HTMLレポートの生成
        html_file = self.report_generator.generate_html_report(
            self.trades, 
            self.metrics, 
            self._get_config_dict(),
            daily_positions_data
        )
        
        # CSVレポートの生成
        csv_file = self.report_generator.generate_csv_report(
            self.trades, 
            self._get_config_dict()
        )
        
        print(f"HTMLレポート: {html_file}")
        print(f"CSVレポート: {csv_file}")
    
    def get_text(self, key: str) -> str:
        """多言語対応テキストを取得"""
        return TextConfig.get_text(key, self.config.language)
    


def create_backtest_from_args(args) -> EarningsBacktest:
    """コマンドライン引数からバックテストインスタンスを作成"""
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
        partial_profit=not args.no_partial_profit,
        sp500_only=args.sp500_only,
        mid_small_only=getattr(args, 'mid_small_only', False) if not args.sp500_only else False,
        language=args.language,
        pre_earnings_change=args.pre_earnings_change,
        margin_ratio=args.margin_ratio,
        enable_earnings_date_validation=args.enable_date_validation,
        # データソース設定: デフォルトはFMP、--use_eodhd指定時のみEODHD
        use_fmp_data=not getattr(args, 'use_eodhd', False),
        # 時価総額フィルター設定: デフォルトは無効、--use_market_cap_filter指定時のみ有効
        use_market_cap_filter=getattr(args, 'use_market_cap_filter', False),
        min_market_cap=args.min_market_cap * 1e9,  # Convert billions to actual value
        max_market_cap=args.max_market_cap * 1e9   # Convert billions to actual value
    )
    
    return EarningsBacktest(config)