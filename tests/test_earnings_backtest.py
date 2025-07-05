import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from earnings_backtest import EarningsBacktest


class TestEarningsBacktest(unittest.TestCase):
    
    def setUp(self):
        """テスト用のEarningsBacktestインスタンスを作成"""
        with patch.dict(os.environ, {'EODHD_API_KEY': 'test_key'}):
            with patch.object(EarningsBacktest, 'get_sp500_symbols', return_value=['AAPL', 'MSFT']):
                with patch.object(EarningsBacktest, 'get_mid_small_symbols', return_value=['TEST']):
                    self.backtest = EarningsBacktest(
                        start_date='2024-01-01',
                        end_date='2024-01-31',
                        stop_loss=6,
                        trail_stop_ma=21,
                        max_holding_days=90,
                        initial_capital=10000,
                        position_size=6,
                        slippage=0.3,
                        risk_limit=6,
                        sp500_only=False,
                        mid_small_only=False
                    )

    def test_init_parameters(self):
        """初期化パラメータのテスト"""
        self.assertEqual(self.backtest.start_date, '2024-01-01')
        self.assertEqual(self.backtest.end_date, '2024-01-31')
        self.assertEqual(self.backtest.stop_loss, 6)
        self.assertEqual(self.backtest.trail_stop_ma, 21)
        self.assertEqual(self.backtest.max_holding_days, 90)
        self.assertEqual(self.backtest.initial_capital, 10000)
        self.assertEqual(self.backtest.position_size, 6)
        self.assertEqual(self.backtest.slippage, 0.3)
        self.assertEqual(self.backtest.risk_limit, 6)

    def test_future_end_date_adjustment(self):
        """未来の終了日が現在日に調整されることをテスト"""
        with patch.dict(os.environ, {'EODHD_API_KEY': 'test_key'}):
            with patch.object(EarningsBacktest, 'get_sp500_symbols', return_value=[]):
                with patch.object(EarningsBacktest, 'get_mid_small_symbols', return_value=[]):
                    future_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                    backtest = EarningsBacktest(
                        start_date='2024-01-01',
                        end_date=future_date
                    )
                    today = datetime.now().strftime('%Y-%m-%d')
                    self.assertEqual(backtest.end_date, today)

    @patch.dict(os.environ, {'EODHD_API_KEY': ''})
    def test_missing_api_key(self):
        """APIキーが設定されていない場合のエラーテスト"""
        with self.assertRaises(ValueError):
            EarningsBacktest('2024-01-01', '2024-01-31')

    @patch('requests.get')
    def test_get_sp500_symbols_success(self):
        """S&P500シンボル取得の成功テスト"""
        mock_html = """
        <table class="wikitable">
            <tr><th>Symbol</th><th>Company</th></tr>
            <tr><td>AAPL</td><td>Apple Inc.</td></tr>
            <tr><td>MSFT</td><td>Microsoft Corporation</td></tr>
        </table>
        """
        mock_response = Mock()
        mock_response.text = mock_html
        mock_response.raise_for_status.return_value = None
        mock_get = Mock(return_value=mock_response)
        
        with patch('requests.get', mock_get):
            symbols = self.backtest.get_sp500_symbols()
            self.assertIn('AAPL', symbols)
            self.assertIn('MSFT', symbols)
            self.assertEqual(len(symbols), 2)

    @patch('requests.get')
    def test_get_sp500_symbols_failure(self):
        """S&P500シンボル取得の失敗テスト"""
        mock_get = Mock(side_effect=Exception("Network error"))
        
        with patch('requests.get', mock_get):
            symbols = self.backtest.get_sp500_symbols()
            self.assertEqual(symbols, [])

    def test_determine_trade_date_before_market(self):
        """市場開始前の決算発表のトレード日決定テスト"""
        trade_date = self.backtest.determine_trade_date('2024-01-15', 'Before Market Open')
        self.assertEqual(trade_date, '2024-01-15')

    def test_determine_trade_date_after_market(self):
        """市場終了後の決算発表のトレード日決定テスト"""
        trade_date = self.backtest.determine_trade_date('2024-01-15', 'After Market Close')
        self.assertEqual(trade_date, '2024-01-16')

    def test_determine_trade_date_unknown(self):
        """不明なタイミングの決算発表のトレード日決定テスト"""
        trade_date = self.backtest.determine_trade_date('2024-01-15', 'Unknown')
        self.assertEqual(trade_date, '2024-01-16')

    def test_check_risk_management_within_limit(self):
        """リスク制限内の場合のテスト"""
        can_trade = self.backtest.check_risk_management('2024-01-15', 9500)
        self.assertTrue(can_trade)

    def test_check_risk_management_exceed_limit(self):
        """リスク制限を超えた場合のテスト"""
        can_trade = self.backtest.check_risk_management('2024-01-15', 9300)
        self.assertFalse(can_trade)

    def test_get_text_english(self):
        """英語テキスト取得のテスト"""
        self.backtest.language = 'en'
        text = self.backtest.get_text('total_trades')
        self.assertEqual(text, 'Total Trades')

    def test_get_text_japanese(self):
        """日本語テキスト取得のテスト"""
        self.backtest.language = 'ja'
        text = self.backtest.get_text('total_trades')
        self.assertEqual(text, '総トレード数')

    def test_calculate_metrics_no_trades(self):
        """取引がない場合のメトリクス計算テスト"""
        self.backtest.trades = []
        metrics = self.backtest.calculate_metrics()
        
        self.assertEqual(metrics['total_trades'], 0)
        self.assertEqual(metrics['win_rate'], 0)
        self.assertEqual(metrics['avg_return'], 0)
        self.assertEqual(metrics['total_return'], 0)

    def test_calculate_metrics_with_trades(self):
        """取引がある場合のメトリクス計算テスト"""
        self.backtest.trades = [
            {
                'entry_date': '2024-01-01',
                'exit_date': '2024-01-05',
                'symbol': 'AAPL',
                'entry_price': 100,
                'exit_price': 110,
                'return': 10,
                'exit_reason': 'Profit Target'
            },
            {
                'entry_date': '2024-01-02',
                'exit_date': '2024-01-06',
                'symbol': 'MSFT',
                'entry_price': 200,
                'exit_price': 190,
                'return': -5,
                'exit_reason': 'Stop Loss'
            }
        ]
        
        metrics = self.backtest.calculate_metrics()
        
        self.assertEqual(metrics['total_trades'], 2)
        self.assertEqual(metrics['winning_trades'], 1)
        self.assertEqual(metrics['losing_trades'], 1)
        self.assertEqual(metrics['win_rate'], 50.0)
        self.assertEqual(metrics['avg_return'], 2.5)
        self.assertEqual(metrics['total_return'], 5.0)

    @patch('requests.get')
    def test_get_historical_data_success(self):
        """履歴データ取得の成功テスト"""
        mock_response_data = {
            'data': [
                {'date': '2024-01-01', 'open': 100, 'high': 105, 'low': 99, 'close': 103, 'volume': 1000000},
                {'date': '2024-01-02', 'open': 103, 'high': 108, 'low': 102, 'close': 107, 'volume': 1200000}
            ]
        }
        
        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None
        
        with patch('requests.get', return_value=mock_response):
            df = self.backtest.get_historical_data('AAPL', '2024-01-01', '2024-01-31')
            
            self.assertIsInstance(df, pd.DataFrame)
            self.assertEqual(len(df), 2)
            self.assertIn('date', df.columns)
            self.assertIn('close', df.columns)
            self.assertIn('volume', df.columns)

    @patch('requests.get')
    def test_get_historical_data_failure(self):
        """履歴データ取得の失敗テスト"""
        mock_get = Mock(side_effect=Exception("API error"))
        
        with patch('requests.get', mock_get):
            df = self.backtest.get_historical_data('AAPL', '2024-01-01', '2024-01-31')
            self.assertIsNone(df)

    def test_filter_earnings_data_basic_filters(self):
        """決算データの基本フィルタリングテスト"""
        test_data = pd.DataFrame({
            'code': ['AAPL.US', 'MSFT.US', 'GOOGL.US'],
            'actual': [2.5, 1.8, 1.2],
            'estimate': [2.0, 2.0, 1.0],
            'difference': [0.5, -0.2, 0.2],
            'surprise_percent': [25.0, -10.0, 20.0],
            'report_date': ['2024-01-15', '2024-01-16', '2024-01-17']
        })
        
        filtered_data = self.backtest.filter_earnings_data(test_data)
        
        # surprise_percent >= 5% かつ actual > 0 の条件をチェック
        self.assertTrue(all(filtered_data['surprise_percent'] >= 5))
        self.assertTrue(all(filtered_data['actual'] > 0))

    def test_daily_positions_calculation(self):
        """日次ポジション計算のテスト"""
        # テスト用のトレードデータを設定
        self.backtest.trades = [
            {
                'entry_date': '2024-01-01',
                'exit_date': '2024-01-05',
                'symbol': 'AAPL',
                'shares': 100,
                'entry_price': 100,
                'return': 500
            }
        ]
        
        daily_positions = self.backtest.calculate_daily_positions()
        
        self.assertIsInstance(daily_positions, pd.DataFrame)
        if not daily_positions.empty:
            self.assertIn('date', daily_positions.columns)
            self.assertIn('total_value', daily_positions.columns)


class TestEarningsBacktestIntegration(unittest.TestCase):
    """統合テスト"""
    
    @patch.dict(os.environ, {'EODHD_API_KEY': 'test_key'})
    @patch.object(EarningsBacktest, 'get_sp500_symbols')
    @patch.object(EarningsBacktest, 'get_mid_small_symbols')
    @patch.object(EarningsBacktest, 'get_earnings_data')
    @patch.object(EarningsBacktest, 'get_historical_data')
    def test_execute_backtest_integration(self, mock_historical, mock_earnings, mock_mid_small, mock_sp500):
        """バックテスト実行の統合テスト"""
        # モックデータの設定
        mock_sp500.return_value = ['AAPL', 'MSFT']
        mock_mid_small.return_value = ['TEST']
        
        mock_earnings_data = pd.DataFrame({
            'code': ['AAPL.US'],
            'actual': [2.5],
            'estimate': [2.0],
            'difference': [0.5],
            'surprise_percent': [25.0],
            'report_date': ['2024-01-15'],
            'time': ['After Market Close']
        })
        mock_earnings.return_value = mock_earnings_data
        
        mock_historical_data = pd.DataFrame({
            'date': pd.date_range('2024-01-01', '2024-01-31'),
            'open': np.random.uniform(95, 105, 31),
            'high': np.random.uniform(100, 110, 31),
            'low': np.random.uniform(90, 100, 31),
            'close': np.random.uniform(95, 105, 31),
            'volume': np.random.randint(500000, 2000000, 31)
        })
        mock_historical.return_value = mock_historical_data
        
        backtest = EarningsBacktest(
            start_date='2024-01-01',
            end_date='2024-01-31'
        )
        
        # バックテスト実行
        try:
            backtest.execute_backtest()
            # エラーが発生しなければ成功
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"Backtest execution failed: {str(e)}")


if __name__ == '__main__':
    unittest.main()