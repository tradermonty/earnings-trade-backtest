import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# srcディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))

from src.config import BacktestConfig
from src.main import EarningsBacktest
from src.data_fetcher import DataFetcher
from src.data_filter import DataFilter
from src.risk_manager import RiskManager
from src.trade_executor import TradeExecutor
from src.metrics_calculator import MetricsCalculator
from src.report_generator import ReportGenerator


class TestBacktestConfig(unittest.TestCase):
    """BacktestConfig のテスト"""
    
    def test_config_creation(self):
        """設定の作成テスト"""
        config = BacktestConfig(
            start_date='2024-01-01',
            end_date='2024-01-31'
        )

        self.assertEqual(config.start_date, '2024-01-01')
        self.assertEqual(config.end_date, '2024-01-31')
        self.assertEqual(config.stop_loss, 6)
        self.assertEqual(config.initial_capital, 10000)

    def test_min_surprise_percent_default_value(self):
        """min_surprise_percent のデフォルト値テスト"""
        config = BacktestConfig(
            start_date='2024-01-01',
            end_date='2024-01-31'
        )

        # デフォルト値は 5.0% であるべき
        self.assertEqual(config.min_surprise_percent, 5.0)

    def test_min_surprise_percent_custom_value(self):
        """min_surprise_percent のカスタム値テスト"""
        config = BacktestConfig(
            start_date='2024-01-01',
            end_date='2024-01-31',
            min_surprise_percent=20.0
        )

        # カスタム値が設定されるべき
        self.assertEqual(config.min_surprise_percent, 20.0)


class TestCLIArguments(unittest.TestCase):
    """CLI引数のテスト"""

    def test_min_surprise_argument_default(self):
        """--min_surprise のデフォルト値テスト"""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
        from main import parse_arguments

        # 引数なしでパース (sys.argvをモック)
        with patch.object(sys, 'argv', ['main.py', '--start_date', '2024-01-01', '--end_date', '2024-01-31']):
            args = parse_arguments()
            # デフォルト値は 5.0 であるべき
            self.assertEqual(args.min_surprise, 5.0)

    def test_min_surprise_argument_custom(self):
        """--min_surprise のカスタム値テスト"""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
        from main import parse_arguments

        # --min_surprise 20.0 を指定
        with patch.object(sys, 'argv', ['main.py', '--start_date', '2024-01-01', '--end_date', '2024-01-31', '--min_surprise', '20.0']):
            args = parse_arguments()
            self.assertEqual(args.min_surprise, 20.0)


class TestConfigToDataFilterIntegration(unittest.TestCase):
    """BacktestConfig から DataFilter への値受け渡しテスト"""

    def test_earnings_backtest_passes_min_surprise_to_data_filter(self):
        """EarningsBacktest が min_surprise_percent を DataFilter に渡すことを確認"""
        # src/main.pyのソースコードを読んで、DataFilter呼び出しにmin_surprise_percentが含まれているか確認
        import inspect
        from src.main import EarningsBacktest

        # _initialize_components メソッドでDataFilterを初期化しているので、そちらを確認
        source = inspect.getsource(EarningsBacktest._initialize_components)

        # DataFilter呼び出しにmin_surprise_percentが含まれているか確認
        self.assertIn('min_surprise_percent', source,
                      "EarningsBacktest._initialize_components should pass min_surprise_percent to DataFilter")


class TestDataFetcher(unittest.TestCase):
    """DataFetcher のテスト"""
    
    @patch.dict(os.environ, {'EODHD_API_KEY': 'test_key'})
    def test_data_fetcher_initialization(self):
        """DataFetcher の初期化テスト"""
        fetcher = DataFetcher()
        self.assertEqual(fetcher.api_key, 'test_key')
    
    @patch('requests.get')
    def test_get_sp500_symbols_success(self, mock_get):
        """S&P500シンボル取得の成功テスト"""
        mock_html = """
        <table class="wikitable">
            <tr><th>Symbol</th></tr>
            <tr><td>AAPL</td></tr>
            <tr><td>MSFT</td></tr>
        </table>
        """
        mock_response = Mock()
        mock_response.text = mock_html
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        with patch.dict(os.environ, {'EODHD_API_KEY': 'test_key'}):
            fetcher = DataFetcher()
            symbols = fetcher.get_sp500_symbols()
            self.assertIn('AAPL', symbols)
            self.assertIn('MSFT', symbols)


class TestRiskManager(unittest.TestCase):
    """RiskManager のテスト"""
    
    def setUp(self):
        """テスト用のRiskManagerインスタンスを作成"""
        self.risk_manager = RiskManager(risk_limit=6)
    
    def test_check_risk_management_no_trades(self):
        """トレード履歴がない場合のリスク管理テスト"""
        result = self.risk_manager.check_risk_management('2024-01-15', 10000, [])
        self.assertTrue(result)
    
    def test_calculate_position_size(self):
        """ポジションサイズ計算のテスト"""
        result = self.risk_manager.calculate_position_size(
            capital=10000,
            position_size_percent=6,
            entry_price=100,
            slippage=0.3
        )
        
        self.assertEqual(result['shares'], 5)  # 600 / 100.3 = 5.98... -> 5
        self.assertAlmostEqual(result['adjusted_entry_price'], 100.3, places=2)
    
    def test_check_stop_loss(self):
        """ストップロス条件のテスト"""
        # ストップロスに達した場合
        result = self.risk_manager.check_stop_loss(
            current_price=94,
            entry_price=100,
            stop_loss_percent=6
        )
        self.assertTrue(result)
        
        # ストップロスに達していない場合
        result = self.risk_manager.check_stop_loss(
            current_price=96,
            entry_price=100,
            stop_loss_percent=6
        )
        self.assertFalse(result)
    
    def test_should_partial_profit(self):
        """部分利確条件のテスト"""
        # 部分利確ターゲットに達した場合
        result = self.risk_manager.should_partial_profit(
            current_price=108,
            entry_price=100,
            target_percent=8
        )
        self.assertTrue(result)
        
        # 部分利確ターゲットに達していない場合
        result = self.risk_manager.should_partial_profit(
            current_price=105,
            entry_price=100,
            target_percent=8
        )
        self.assertFalse(result)


class TestMetricsCalculator(unittest.TestCase):
    """MetricsCalculator のテスト"""
    
    def setUp(self):
        """テスト用のMetricsCalculatorインスタンスを作成"""
        self.calculator = MetricsCalculator(initial_capital=10000)
    
    def test_calculate_metrics_no_trades(self):
        """トレードがない場合のメトリクス計算テスト"""
        metrics = self.calculator.calculate_metrics([])
        
        self.assertEqual(metrics['total_trades'], 0)
        self.assertEqual(metrics['win_rate'], 0)
        self.assertEqual(metrics['initial_capital'], 10000)
        self.assertEqual(metrics['final_capital'], 10000)
    
    def test_calculate_metrics_with_trades(self):
        """トレードがある場合のメトリクス計算テスト"""
        trades = [
            {
                'entry_date': '2024-01-01',
                'exit_date': '2024-01-05',
                'ticker': 'AAPL',
                'entry_price': 100,
                'exit_price': 110,
                'pnl': 100,
                'pnl_rate': 10,
                'holding_period': 4,
                'exit_reason': 'Profit Target',
                'shares': 10
            },
            {
                'entry_date': '2024-01-02',
                'exit_date': '2024-01-06',
                'ticker': 'MSFT',
                'entry_price': 200,
                'exit_price': 190,
                'pnl': -100,
                'pnl_rate': -5,
                'holding_period': 4,
                'exit_reason': 'Stop Loss',
                'shares': 10
            }
        ]
        
        metrics = self.calculator.calculate_metrics(trades)
        
        self.assertEqual(metrics['number_of_trades'], 2)
        self.assertEqual(metrics['winning_trades'], 1)
        self.assertEqual(metrics['losing_trades'], 1)
        self.assertEqual(metrics['win_rate'], 50.0)
        self.assertEqual(metrics['final_capital'], 10000.0)  # 100 - 100 = 0 profit


class TestEarningsBacktest(unittest.TestCase):
    """EarningsBacktest メインクラスのテスト"""
    
    @patch.dict(os.environ, {'EODHD_API_KEY': 'test_key'})
    def setUp(self):
        """テスト用のEarningsBacktestインスタンスを作成"""
        config = BacktestConfig(
            start_date='2024-01-01',
            end_date='2024-01-31'
        )
        
        with patch.object(DataFetcher, 'get_sp500_symbols', return_value=['AAPL', 'MSFT']):
            with patch.object(DataFetcher, 'get_mid_small_symbols', return_value=['TEST']):
                self.backtest = EarningsBacktest(config)
    
    def test_initialization(self):
        """初期化のテスト"""
        self.assertEqual(self.backtest.config.start_date, '2024-01-01')
        self.assertEqual(self.backtest.config.end_date, '2024-01-31')
        self.assertIsInstance(self.backtest.data_fetcher, DataFetcher)
        self.assertIsInstance(self.backtest.risk_manager, RiskManager)
        self.assertIsInstance(self.backtest.metrics_calculator, MetricsCalculator)
    
    def test_get_config_dict(self):
        """設定辞書取得のテスト"""
        config_dict = self.backtest._get_config_dict()
        
        self.assertEqual(config_dict['start_date'], '2024-01-01')
        self.assertEqual(config_dict['end_date'], '2024-01-31')
        self.assertEqual(config_dict['initial_capital'], 10000)
        self.assertEqual(config_dict['position_size'], 6)
    
    @patch.object(DataFetcher, 'get_earnings_data')
    @patch.object(DataFilter, 'filter_earnings_data')
    @patch.object(TradeExecutor, 'execute_backtest')
    def test_execute_backtest_no_candidates(self, mock_execute, mock_filter, mock_earnings):
        """候補銘柄がない場合のバックテストテスト"""
        mock_earnings.return_value = {'earnings': []}
        mock_filter.return_value = []
        
        results = self.backtest.execute_backtest()
        
        self.assertEqual(len(results['trades']), 0)
        self.assertEqual(results['metrics']['total_trades'], 0)
        mock_execute.assert_not_called()
    
    @patch.object(DataFetcher, 'get_earnings_data')
    @patch.object(DataFilter, 'filter_earnings_data')
    @patch.object(TradeExecutor, 'execute_backtest')
    @patch.object(ReportGenerator, 'generate_html_report')
    @patch.object(ReportGenerator, 'generate_csv_report')
    def test_execute_backtest_with_trades(self, mock_csv, mock_html, mock_execute, 
                                         mock_filter, mock_earnings):
        """トレードがある場合のバックテストテスト"""
        # モックデータの設定
        mock_earnings.return_value = {'earnings': [{'code': 'AAPL.US'}]}
        mock_filter.return_value = [{'code': 'AAPL', 'trade_date': '2024-01-15'}]
        mock_execute.return_value = [
            {
                'entry_date': '2024-01-15',
                'exit_date': '2024-01-20',
                'ticker': 'AAPL',
                'pnl': 100,
                'pnl_rate': 10,
                'holding_period': 5,
                'exit_reason': 'profit_target',
                'entry_price': 100,
                'exit_price': 110,
                'shares': 10
            }
        ]
        mock_html.return_value = 'test.html'
        mock_csv.return_value = 'test.csv'
        
        results = self.backtest.execute_backtest()
        
        self.assertEqual(len(results['trades']), 1)
        self.assertEqual(results['trades'][0]['ticker'], 'AAPL')
        mock_execute.assert_called_once()
        mock_html.assert_called_once()
        mock_csv.assert_called_once()


class TestIntegration(unittest.TestCase):
    """統合テスト"""
    
    @patch.dict(os.environ, {'EODHD_API_KEY': 'test_key'})
    @patch.object(DataFetcher, 'get_sp500_symbols')
    @patch.object(DataFetcher, 'get_mid_small_symbols')
    @patch.object(DataFetcher, 'get_earnings_data')
    @patch.object(DataFetcher, 'get_historical_data')
    @patch.object(ReportGenerator, 'generate_html_report')
    @patch.object(ReportGenerator, 'generate_csv_report')
    def test_full_backtest_integration(self, mock_csv, mock_html, mock_historical, 
                                      mock_earnings, mock_mid_small, mock_sp500):
        """フルバックテストの統合テスト"""
        # モックデータの設定
        mock_sp500.return_value = ['AAPL', 'MSFT']
        mock_mid_small.return_value = ['TEST']
        
        mock_earnings_data = {
            'earnings': [{
                'code': 'AAPL.US',
                'actual': 2.5,
                'estimate': 2.0,
                'percent': 25.0,
                'report_date': '2024-01-15',
                'before_after_market': 'After Market Close'
            }]
        }
        mock_earnings.return_value = mock_earnings_data
        
        # 株価データのモック
        dates = pd.date_range('2024-01-01', '2024-02-29')
        mock_historical_data = pd.DataFrame({
            'date': dates,
            'open': np.random.uniform(95, 105, len(dates)),
            'high': np.random.uniform(100, 110, len(dates)),
            'low': np.random.uniform(90, 100, len(dates)),
            'close': np.random.uniform(95, 105, len(dates)),
            'volume': np.random.randint(500000, 2000000, len(dates))
        })
        mock_historical.return_value = mock_historical_data
        
        mock_html.return_value = 'test.html'
        mock_csv.return_value = 'test.csv'
        
        # バックテストの実行
        config = BacktestConfig(
            start_date='2024-01-01',
            end_date='2024-01-31'
        )
        
        backtest = EarningsBacktest(config)
        results = backtest.execute_backtest()
        
        # 結果の検証
        self.assertIsInstance(results, dict)
        self.assertIn('trades', results)
        self.assertIn('metrics', results)
        self.assertIn('config', results)


if __name__ == '__main__':
    unittest.main()