"""
AnalysisEngineのテストコード
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis_engine import AnalysisEngine
from src.data_fetcher import DataFetcher
from src.config import ThemeConfig


class TestAnalysisEngine(unittest.TestCase):
    """AnalysisEngineのテストクラス"""
    
    def setUp(self):
        """テストの初期設定"""
        # モックのDataFetcherを作成
        self.mock_data_fetcher = Mock(spec=DataFetcher)
        self.mock_data_fetcher.api_key = 'test_api_key'
        
        # AnalysisEngineのインスタンスを作成
        self.analysis_engine = AnalysisEngine(
            data_fetcher=self.mock_data_fetcher,
            theme=ThemeConfig.DARK_THEME
        )
        
        # テスト用のトレードデータ
        self.test_trades_df = pd.DataFrame({
            'ticker': ['AAPL', 'GOOGL', 'MSFT'],
            'entry_date': ['2024-01-15', '2024-01-20', '2024-01-25'],
            'exit_date': ['2024-01-25', '2024-01-30', '2024-02-05'],
            'entry_price': [150.0, 140.0, 380.0],
            'exit_price': [155.0, 135.0, 395.0],
            'pnl': [500.0, -500.0, 1500.0],
            'pnl_rate': [3.33, -3.57, 3.95],
            'sector': ['Technology', 'Technology', 'Technology'],
            'industry': ['Consumer Electronics', 'Internet Services', 'Software']
        })
    
    def test_add_eps_info_with_api_data(self):
        """_add_eps_info メソッドのテスト（APIデータあり）"""
        # モックのAPIレスポンスを設定
        mock_earnings_response = {
            'eps': 3.52,
            'estimate': 3.30
        }
        
        mock_historical_earnings = [
            {'eps': 2.50}, {'eps': 2.60}, {'eps': 2.70}, {'eps': 2.80}, 
            {'eps': 2.90}, {'eps': 3.00}, {'eps': 3.10}, {'eps': 3.20}, {'eps': 3.52}
        ]
        
        # モックの株価データ
        mock_stock_data = pd.DataFrame({
            'date': pd.date_range('2023-12-01', '2024-01-15', freq='D'),
            'Open': np.random.uniform(140, 160, 46),
            'Close': np.random.uniform(140, 160, 46),
            'Volume': np.random.uniform(1000000, 2000000, 46)
        })
        
        # get_historical_dataのモック設定
        self.mock_data_fetcher.get_historical_data.return_value = mock_stock_data
        
        with patch('requests.get') as mock_get:
            # EPSデータのモックレスポンス
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.side_effect = [
                [mock_earnings_response],  # 最新のEPSデータ
                mock_historical_earnings   # 履歴EPSデータ
            ]
            mock_get.return_value = mock_response
            
            # メソッドを実行
            result_df = self.analysis_engine._add_eps_info(self.test_trades_df)
            
            # 検証
            self.assertIn('eps_surprise_percent', result_df.columns)
            self.assertIn('eps_growth_percent', result_df.columns)
            self.assertIn('eps_acceleration', result_df.columns)
            self.assertIn('gap', result_df.columns)
            self.assertIn('pre_earnings_change', result_df.columns)
            self.assertIn('volume_ratio', result_df.columns)
            self.assertIn('price_to_ma200', result_df.columns)
            self.assertIn('price_to_ma50', result_df.columns)
            
            # EPSサプライズ率の計算検証
            expected_surprise = ((3.52 - 3.30) / abs(3.30)) * 100
            self.assertAlmostEqual(result_df['eps_surprise_percent'].iloc[0], expected_surprise, places=2)
    
    def test_add_eps_info_with_no_api_data(self):
        """_add_eps_info メソッドのテスト（APIデータなし）"""
        # get_historical_dataのモック設定（データなし）
        self.mock_data_fetcher.get_historical_data.return_value = None
        
        with patch('requests.get') as mock_get:
            # APIエラーのモック
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response
            
            # メソッドを実行
            result_df = self.analysis_engine._add_eps_info(self.test_trades_df)
            
            # デフォルト値の検証
            self.assertEqual(result_df['eps_surprise_percent'].iloc[0], 0.0)
            self.assertEqual(result_df['eps_growth_percent'].iloc[0], 0.0)
            self.assertEqual(result_df['eps_acceleration'].iloc[0], 0.0)
            self.assertEqual(result_df['volume_ratio'].iloc[0], 1.0)
            self.assertEqual(result_df['price_to_ma200'].iloc[0], 1.0)
            self.assertEqual(result_df['price_to_ma50'].iloc[0], 1.0)
    
    def test_create_sector_performance_chart(self):
        """_create_sector_performance_chart メソッドのテスト"""
        # EPSデータを追加（モック）
        df_with_eps = self.test_trades_df.copy()
        df_with_eps['eps_surprise_percent'] = [10.0, -5.0, 15.0]
        
        # メソッドを実行
        chart_html = self.analysis_engine._create_sector_performance_chart(df_with_eps)
        
        # 検証
        self.assertIsInstance(chart_html, str)
        self.assertIn('sector-performance-chart', chart_html)
        self.assertIn('Technology', chart_html)
    
    def test_create_industry_performance_chart(self):
        """_create_industry_performance_chart メソッドのテスト"""
        # メソッドを実行
        chart_html = self.analysis_engine._create_industry_performance_chart(self.test_trades_df)
        
        # 検証
        self.assertIsInstance(chart_html, str)
        self.assertIn('industry-performance-chart', chart_html)
        self.assertIn('Industry Performance (Top 15)', chart_html)
    
    def test_create_volume_trend_chart(self):
        """_create_volume_trend_chart メソッドのテスト"""
        # volume_ratioを追加
        df_with_volume = self.test_trades_df.copy()
        df_with_volume['volume_ratio'] = [1.2, 2.5, 3.8]
        
        # メソッドを実行
        chart_html = self.analysis_engine._create_volume_trend_chart(df_with_volume)
        
        # 検証
        self.assertIsInstance(chart_html, str)
        self.assertIn('volume-trend-chart', chart_html)
        self.assertIn('Volume Trend Analysis', chart_html)
    
    def test_create_pre_earnings_performance_chart(self):
        """_create_pre_earnings_performance_chart メソッドのテスト"""
        # pre_earnings_changeを追加
        df_with_pre_earnings = self.test_trades_df.copy()
        df_with_pre_earnings['pre_earnings_change'] = [-15.0, 5.0, 25.0]
        
        # メソッドを実行
        chart_html = self.analysis_engine._create_pre_earnings_performance_chart(df_with_pre_earnings)
        
        # 検証
        self.assertIsInstance(chart_html, str)
        self.assertIn('pre-earnings-performance-chart', chart_html)
        self.assertIn('Performance by Pre-Earnings Trend', chart_html)
        # カテゴリの確認（HTMLエンコードされた文字列も考慮）
        self.assertIn('-20~-10%', chart_html)
        self.assertIn('0~10%', chart_html)
        # >20% は HTMLエンコードされて \\u003e20% になる
        self.assertTrue('>20%' in chart_html or '\\u003e20%' in chart_html)
    
    def test_generate_analysis_charts_empty_df(self):
        """generate_analysis_charts メソッドのテスト（空のDataFrame）"""
        empty_df = pd.DataFrame()
        
        # メソッドを実行
        result = self.analysis_engine.generate_analysis_charts(empty_df)
        
        # 検証
        self.assertEqual(result, {})
    
    def test_generate_analysis_charts_with_data(self):
        """generate_analysis_charts メソッドのテスト（データあり）"""
        # モックの設定
        self.mock_data_fetcher.get_fundamentals_data.return_value = {
            'General': {
                'Sector': 'Technology',
                'Industry': 'Software'
            }
        }
        
        # 空の株価データをモック
        self.mock_data_fetcher.get_historical_data.return_value = None
        
        with patch('requests.get') as mock_get:
            # APIエラーのモック（簡略化のため）
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response
            
            # メソッドを実行
            result = self.analysis_engine.generate_analysis_charts(self.test_trades_df)
            
            # 検証 - 必要なチャートが生成されているか
            expected_charts = [
                'monthly_performance',
                'sector_performance',
                'eps_surprise',
                'eps_growth',
                'eps_acceleration',
                'industry_performance',
                'gap_performance',
                'pre_earnings_performance',
                'volume_trend',
                'ma200_analysis',
                'ma50_analysis'
            ]
            
            for chart_name in expected_charts:
                self.assertIn(chart_name, result)
                self.assertIsInstance(result[chart_name], str)
    
    def test_calculate_volume_ratio(self):
        """出来高比率の計算テスト"""
        # テスト用の株価データ
        test_dates = pd.date_range('2023-10-01', '2024-01-15', freq='D')
        test_volume = np.concatenate([
            np.random.uniform(1000000, 1500000, 60),  # 過去60日
            np.random.uniform(2000000, 3000000, len(test_dates) - 60)  # 直近
        ])
        
        mock_stock_data = pd.DataFrame({
            'date': test_dates.strftime('%Y-%m-%d'),
            'Open': np.random.uniform(140, 160, len(test_dates)),
            'Close': np.random.uniform(140, 160, len(test_dates)),
            'Volume': test_volume
        })
        
        # get_historical_dataのモック設定
        self.mock_data_fetcher.get_historical_data.return_value = mock_stock_data
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response
            
            # メソッドを実行
            result_df = self.analysis_engine._add_eps_info(self.test_trades_df.head(1))
            
            # 出来高比率が1より大きいことを確認（直近の出来高が増えているため）
            self.assertGreater(result_df['volume_ratio'].iloc[0], 1.0)
    
    def test_calculate_price_change(self):
        """決算前価格変化率の計算テスト"""
        # テスト用の株価データ（価格が上昇トレンド）
        test_dates = pd.date_range('2023-12-15', '2024-01-15', freq='D')
        test_prices = np.linspace(140, 160, len(test_dates))  # 140から160へ上昇
        
        mock_stock_data = pd.DataFrame({
            'date': test_dates.strftime('%Y-%m-%d'),
            'Open': test_prices,
            'Close': test_prices,
            'Volume': np.random.uniform(1000000, 2000000, len(test_dates))
        })
        
        # get_historical_dataのモック設定
        self.mock_data_fetcher.get_historical_data.return_value = mock_stock_data
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response
            
            # メソッドを実行
            result_df = self.analysis_engine._add_eps_info(self.test_trades_df.head(1))
            
            # 価格変化率が正であることを確認
            self.assertGreater(result_df['pre_earnings_change'].iloc[0], 0)


class TestAnalysisEngineIntegration(unittest.TestCase):
    """AnalysisEngineの統合テスト"""
    
    def setUp(self):
        """テストの初期設定"""
        # 実際のDataFetcherを使用（APIキーが必要）
        if 'EODHD_API_KEY' in os.environ:
            self.data_fetcher = DataFetcher()
            self.analysis_engine = AnalysisEngine(
                data_fetcher=self.data_fetcher,
                theme=ThemeConfig.DARK_THEME
            )
            self.skip_integration_tests = False
        else:
            self.skip_integration_tests = True
    
    def test_real_data_analysis(self):
        """実データを使用した分析テスト"""
        if self.skip_integration_tests:
            self.skipTest("EODHD_API_KEY not found in environment variables")
        
        # 少量のテストデータ
        test_trades_df = pd.DataFrame({
            'ticker': ['AAPL'],
            'entry_date': ['2024-01-15'],
            'exit_date': ['2024-01-25'],
            'entry_price': [185.0],
            'exit_price': [190.0],
            'pnl': [500.0],
            'pnl_rate': [2.70],
            'sector': ['Technology'],
            'industry': ['Consumer Electronics']
        })
        
        # 分析を実行
        result = self.analysis_engine.generate_analysis_charts(test_trades_df)
        
        # 基本的な検証
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)


if __name__ == '__main__':
    # テストの実行
    unittest.main(verbosity=2)