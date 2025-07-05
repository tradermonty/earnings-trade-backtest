"""
個別コンポーネントの詳細テスト
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# srcディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))

from src.config import BacktestConfig, ThemeConfig, TextConfig
from src.data_fetcher import DataFetcher
from src.data_filter import DataFilter
from src.risk_manager import RiskManager
from src.trade_executor import TradeExecutor
from src.metrics_calculator import MetricsCalculator
from src.report_generator import ReportGenerator


class TestTextConfig(unittest.TestCase):
    """TextConfig のテスト"""
    
    def test_get_text_english(self):
        """英語テキスト取得のテスト"""
        text = TextConfig.get_text('total_trades', 'en')
        self.assertEqual(text, 'Total Trades')
    
    def test_get_text_japanese(self):
        """日本語テキスト取得のテスト"""
        text = TextConfig.get_text('total_trades', 'ja')
        self.assertEqual(text, '総トレード数')
    
    def test_get_text_unknown_key(self):
        """未知のキーのテスト"""
        text = TextConfig.get_text('unknown_key', 'en')
        self.assertEqual(text, 'unknown_key')
    
    def test_get_text_unknown_language(self):
        """未知の言語のテスト（英語にフォールバック）"""
        text = TextConfig.get_text('total_trades', 'unknown')
        self.assertEqual(text, 'Total Trades')


class TestThemeConfig(unittest.TestCase):
    """ThemeConfig のテスト"""
    
    def test_dark_theme_colors(self):
        """ダークテーマの色設定テスト"""
        theme = ThemeConfig.DARK_THEME
        self.assertIn('bg_color', theme)
        self.assertIn('text_color', theme)
        self.assertIn('profit_color', theme)
        self.assertIn('loss_color', theme)


class TestDataFilter(unittest.TestCase):
    """DataFilter のテスト"""
    
    def setUp(self):
        """テスト用のDataFilterインスタンスを作成"""
        mock_fetcher = Mock(spec=DataFetcher)
        self.filter = DataFilter(
            data_fetcher=mock_fetcher,
            target_symbols=None,
            pre_earnings_change=-10,
            max_holding_days=90
        )
    
    def test_determine_trade_date_before_market(self):
        """市場開始前の決算発表のトレード日決定テスト"""
        trade_date = self.filter.determine_trade_date('2024-01-15', 'Before Market Open')
        self.assertEqual(trade_date, '2024-01-15')
    
    def test_determine_trade_date_after_market(self):
        """市場終了後の決算発表のトレード日決定テスト"""
        trade_date = self.filter.determine_trade_date('2024-01-15', 'After Market Close')
        self.assertEqual(trade_date, '2024-01-16')
    
    def test_determine_trade_date_unknown(self):
        """不明なタイミングの決算発表のトレード日決定テスト"""
        trade_date = self.filter.determine_trade_date('2024-01-15', 'Unknown')
        self.assertEqual(trade_date, '2024-01-16')
    
    def test_filter_earnings_data_no_earnings_key(self):
        """earningsキーがない場合のエラーテスト"""
        data = {'no_earnings': []}
        with self.assertRaises(KeyError):
            self.filter.filter_earnings_data(data)


class TestTradeExecutor(unittest.TestCase):
    """TradeExecutor のテスト"""
    
    def setUp(self):
        """テスト用のTradeExecutorインスタンスを作成"""
        mock_fetcher = Mock(spec=DataFetcher)
        mock_risk_manager = Mock(spec=RiskManager)
        
        # リスク管理は常にTrueを返す
        mock_risk_manager.check_risk_management.return_value = True
        mock_risk_manager.calculate_position_size.return_value = {
            'shares': 10,
            'position_value': 1000,
            'adjusted_entry_price': 100.3
        }
        
        self.executor = TradeExecutor(
            data_fetcher=mock_fetcher,
            risk_manager=mock_risk_manager,
            initial_capital=10000,
            position_size=6,
            stop_loss=6,
            trail_stop_ma=21,
            max_holding_days=90,
            slippage=0.3,
            partial_profit=True
        )
    
    def test_initialization(self):
        """TradeExecutor の初期化テスト"""
        self.assertEqual(self.executor.initial_capital, 10000)
        self.assertEqual(self.executor.position_size, 6)
        self.assertEqual(self.executor.stop_loss, 6)
        self.assertEqual(self.executor.current_capital, 10000)
    
    def test_execute_backtest_empty_candidates(self):
        """候補銘柄が空の場合のテスト"""
        result = self.executor.execute_backtest([])
        self.assertEqual(len(result), 0)


class TestReportGenerator(unittest.TestCase):
    """ReportGenerator のテスト"""
    
    def setUp(self):
        """テスト用のReportGeneratorインスタンスを作成"""
        self.generator = ReportGenerator(language='en')
    
    def test_initialization(self):
        """ReportGenerator の初期化テスト"""
        self.assertEqual(self.generator.language, 'en')
        self.assertIsNotNone(self.generator.theme)
    
    def test_generate_html_report_no_trades(self):
        """トレードがない場合のHTMLレポート生成テスト"""
        result = self.generator.generate_html_report([], {}, {})
        self.assertEqual(result, "")
    
    def test_generate_csv_report_no_trades(self):
        """トレードがない場合のCSVレポート生成テスト"""
        result = self.generator.generate_csv_report([], {})
        self.assertEqual(result, "")
    
    @patch('os.makedirs')
    @patch('pandas.DataFrame.to_csv')
    def test_generate_csv_report_with_trades(self, mock_to_csv, mock_makedirs):
        """トレードがある場合のCSVレポート生成テスト"""
        trades = [
            {
                'entry_date': '2024-01-01',
                'exit_date': '2024-01-05',
                'ticker': 'AAPL',
                'pnl': 100
            }
        ]
        config = {
            'start_date': '2024-01-01',
            'end_date': '2024-01-31'
        }
        
        result = self.generator.generate_csv_report(trades, config)
        
        self.assertTrue(result.endswith('.csv'))
        mock_to_csv.assert_called_once()


class TestAdvancedMetrics(unittest.TestCase):
    """高度なメトリクス計算のテスト"""
    
    def setUp(self):
        """テスト用のMetricsCalculatorインスタンスを作成"""
        self.calculator = MetricsCalculator(initial_capital=10000)
    
    def test_calculate_daily_positions_empty(self):
        """空のトレードリストの日次ポジション計算"""
        result = self.calculator.calculate_daily_positions([])
        self.assertTrue(result.empty)
    
    def test_calculate_daily_positions_with_trades(self):
        """トレードがある場合の日次ポジション計算"""
        trades = [
            {
                'entry_date': '2024-01-01',
                'exit_date': '2024-01-03',
                'shares': 10,
                'entry_price': 100
            },
            {
                'entry_date': '2024-01-02',
                'exit_date': '2024-01-04',
                'shares': 5,
                'entry_price': 200
            }
        ]
        
        result = self.calculator.calculate_daily_positions(trades)
        
        self.assertFalse(result.empty)
        self.assertIn('date', result.columns)
        self.assertIn('total_value', result.columns)
        self.assertIn('num_positions', result.columns)


class TestEdgeCases(unittest.TestCase):
    """エッジケースのテスト"""
    
    @patch.dict(os.environ, {'EODHD_API_KEY': 'test_key'})
    def test_data_fetcher_with_invalid_response(self):
        """無効なレスポンスを受け取った場合のテスト"""
        fetcher = DataFetcher()
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Network error")
            symbols = fetcher.get_sp500_symbols()
            self.assertEqual(symbols, [])
    
    def test_risk_manager_edge_cases(self):
        """RiskManager のエッジケースのテスト"""
        risk_manager = RiskManager(risk_limit=6)
        
        # 0株のポジションサイズ計算
        result = risk_manager.calculate_position_size(
            capital=100,
            position_size_percent=6,
            entry_price=1000,
            slippage=0.3
        )
        self.assertEqual(result['shares'], 0)
        
        # ゼロ除算の回避テスト
        result = risk_manager.check_stop_loss(0, 0, 6)
        self.assertFalse(result)  # ゼロ価格では損失計算ができないのでFalse
    
    def test_metrics_calculator_edge_cases(self):
        """MetricsCalculator のエッジケースのテスト"""
        calculator = MetricsCalculator(initial_capital=10000)
        
        # 1つのトレードのみの場合
        trades = [
            {
                'entry_date': '2024-01-01',
                'exit_date': '2024-01-05',
                'ticker': 'AAPL',
                'pnl': 100,
                'pnl_rate': 10,
                'holding_period': 4,
                'exit_reason': 'profit_target',
                'entry_price': 100,
                'exit_price': 110,
                'shares': 10
            }
        ]
        
        metrics = calculator.calculate_metrics(trades)
        
        self.assertEqual(metrics['number_of_trades'], 1)
        self.assertEqual(metrics['winning_trades'], 1)
        self.assertEqual(metrics['losing_trades'], 0)
        self.assertEqual(metrics['win_rate'], 100.0)


class TestErrorHandling(unittest.TestCase):
    """エラーハンドリングのテスト"""
    
    def test_config_with_invalid_dates(self):
        """無効な日付を持つ設定のテスト"""
        # 実際には初期化時ではなく、バリデーション時にチェックされる
        config = BacktestConfig(
            start_date='invalid-date',
            end_date='2024-01-31'
        )
        # 設定自体は作成される（バリデーションは別途実行される）
        self.assertEqual(config.start_date, 'invalid-date')
    
    def test_data_fetcher_without_api_key(self):
        """APIキーがない場合のテスト"""
        with patch('os.getenv', return_value=None):  # API_KEYをNoneにする
            with self.assertRaises(ValueError):
                DataFetcher()


if __name__ == '__main__':
    unittest.main()