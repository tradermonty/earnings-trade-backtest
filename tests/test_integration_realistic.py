"""
実際の使用環境に近いテストデータでの総合試験
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os
from unittest.mock import Mock, patch
import json

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis_engine import AnalysisEngine
from src.data_fetcher import DataFetcher
from src.config import ThemeConfig
from src.trade_executor import TradeExecutor
from src.risk_manager import RiskManager
from src.report_generator import ReportGenerator


class TestRealisticIntegration(unittest.TestCase):
    """実際の使用環境に近いデータでの総合試験"""
    
    def setUp(self):
        """テストの初期設定"""
        # 実際のDataFetcher形式に合わせたモックデータを作成
        self.mock_data_fetcher = Mock(spec=DataFetcher)
        self.mock_data_fetcher.api_key = 'test_api_key'
        
        # AnalysisEngineのインスタンスを作成
        self.analysis_engine = AnalysisEngine(
            data_fetcher=self.mock_data_fetcher,
            theme=ThemeConfig.DARK_THEME
        )
        
        # 実際のバックテスト結果に近いテストデータを作成
        self.realistic_trades_df = self._create_realistic_trades_data()
        
    def _create_realistic_trades_data(self):
        """実際のバックテスト結果に近いトレードデータを作成"""
        # 実際の2024年のバックテスト結果から抽出したパターン
        realistic_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'NFLX',
            'AMD', 'INTC', 'ORCL', 'CRM', 'ADBE', 'PYPL', 'SPOT', 'SHOP',
            'ZM', 'DOCU', 'SNOW', 'PLTR', 'RBLX', 'COIN', 'SQ', 'UBER',
            'LYFT', 'ABNB', 'DASH', 'PINS', 'SNAP', 'TWTR'
        ]
        
        # 30銘柄のトレードデータを生成
        num_trades = 30
        np.random.seed(42)  # 再現可能な結果のため
        
        # 2024年の実際の取引期間を模擬
        start_dates = pd.date_range('2024-01-02', '2024-11-30', freq='7D')[:num_trades]
        
        trades_data = []
        for i in range(num_trades):
            entry_date = start_dates[i]
            # 保有期間を現実的な範囲でランダム化（1-90日）
            holding_days = np.random.randint(1, 91)
            exit_date = entry_date + timedelta(days=holding_days)
            
            # 現実的な価格レンジ
            entry_price = np.random.uniform(50, 500)
            # 現実的なリターン分布（-20%から+50%）
            return_rate = np.random.normal(2.0, 15.0)  # 平均2%、標準偏差15%
            exit_price = entry_price * (1 + return_rate / 100)
            
            # 現実的なポジションサイズ（$5000-$20000）
            position_value = np.random.uniform(5000, 20000)
            shares = int(position_value / entry_price)
            pnl = (exit_price - entry_price) * shares
            
            # エグジット理由の現実的な分布
            exit_reasons = ['trailing_stop', 'stop_loss', 'max_holding', 'end_of_data']
            weights = [0.4, 0.3, 0.2, 0.1]
            exit_reason = np.random.choice(exit_reasons, p=weights)
            
            # セクターの現実的な分布
            sectors = ['Technology', 'Healthcare', 'Financials', 'Consumer Discretionary', 
                      'Industrials', 'Communication Services', 'Energy']
            sector = np.random.choice(sectors, p=[0.4, 0.15, 0.15, 0.1, 0.1, 0.05, 0.05])
            
            trades_data.append({
                'ticker': realistic_tickers[i],
                'entry_date': entry_date.strftime('%Y-%m-%d'),
                'exit_date': exit_date.strftime('%Y-%m-%d'),
                'entry_price': round(entry_price, 2),
                'exit_price': round(exit_price, 2),
                'shares': shares,
                'pnl': round(pnl, 2),
                'pnl_rate': round(return_rate, 2),
                'holding_period': holding_days,
                'exit_reason': exit_reason,
                'sector': sector,
                'industry': f'{sector} Industry {i%3 + 1}'
            })
        
        return pd.DataFrame(trades_data)
    
    def _create_realistic_stock_data(self, ticker, start_date, end_date):
        """実際のEODHD APIレスポンス形式に合わせた株価データを作成"""
        # 日付範囲を作成
        dates = pd.date_range(start_date, end_date, freq='D')
        # 営業日のみフィルタ（土日を除く）
        business_dates = [d for d in dates if d.weekday() < 5]
        
        if len(business_dates) == 0:
            return None
        
        # 現実的な株価推移を生成
        base_price = np.random.uniform(100, 300)
        price_changes = np.random.normal(0, 0.02, len(business_dates))  # 日次2%の標準偏差
        prices = [base_price]
        
        for change in price_changes[1:]:
            new_price = prices[-1] * (1 + change)
            prices.append(max(new_price, 1.0))  # 最低$1
        
        # EODHD APIの実際の形式に合わせたカラム名（小文字）
        stock_data = pd.DataFrame({
            'date': [d.strftime('%Y-%m-%d') for d in business_dates],
            'open': [round(p * np.random.uniform(0.98, 1.02), 2) for p in prices],
            'high': [round(p * np.random.uniform(1.01, 1.05), 2) for p in prices],
            'low': [round(p * np.random.uniform(0.95, 0.99), 2) for p in prices],
            'close': [round(p, 2) for p in prices],
            'volume': [int(np.random.uniform(1000000, 10000000)) for _ in business_dates]
        })
        
        return stock_data
    
    def _create_realistic_earnings_data(self, ticker, entry_date):
        """実際のEODHD API形式に合わせた決算データを作成"""
        # 現実的なEPS値
        eps_actual = round(np.random.uniform(0.5, 5.0), 2)
        eps_estimate = round(eps_actual * np.random.uniform(0.8, 1.2), 2)
        
        return [{
            'date': entry_date,
            'ticker': ticker,
            'eps': eps_actual,
            'estimate': eps_estimate,
            'revenue': int(np.random.uniform(1000000000, 50000000000)),
            'revenue_estimate': int(np.random.uniform(1000000000, 50000000000))
        }]
    
    def test_analysis_engine_with_realistic_data(self):
        """実際のデータ形式でAnalysisEngineをテスト"""
        print(f"\n=== 実際のデータ形式でのAnalysisEngineテスト ===")
        print(f"テストデータ: {len(self.realistic_trades_df)}件のトレード")
        
        # DataFetcherのモック設定
        def mock_get_historical_data(ticker, start_date, end_date):
            return self._create_realistic_stock_data(ticker, start_date, end_date)
        
        def mock_get_fundamentals_data(ticker):
            sectors = ['Technology', 'Healthcare', 'Financials']
            industries = ['Software', 'Biotechnology', 'Banks']
            return {
                'General': {
                    'Sector': np.random.choice(sectors),
                    'Industry': np.random.choice(industries)
                }
            }
        
        self.mock_data_fetcher.get_historical_data.side_effect = mock_get_historical_data
        self.mock_data_fetcher.get_fundamentals_data.side_effect = mock_get_fundamentals_data
        
        # リクエストのモック（EPS API呼び出し用）
        with patch('requests.get') as mock_get:
            def mock_api_response(*args, **kwargs):
                url = args[0]
                params = kwargs.get('params', {})
                
                # 決算データAPI
                if 'calendar/earnings' in url:
                    symbols = params.get('symbols', '')
                    ticker = symbols.replace('.US', '') if symbols else 'TEST'
                    from_date = params.get('from', '2024-01-01')
                    
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = self._create_realistic_earnings_data(ticker, from_date)
                    return mock_response
                
                # デフォルトレスポンス
                mock_response = Mock()
                mock_response.status_code = 404
                mock_response.json.return_value = []
                return mock_response
            
            mock_get.side_effect = mock_api_response
            
            # 分析チャートを生成
            print("分析チャートを生成中...")
            charts = self.analysis_engine.generate_analysis_charts(self.realistic_trades_df)
            
            # 基本的な検証
            self.assertIsInstance(charts, dict)
            self.assertGreater(len(charts), 0)
            
            print(f"生成されたチャート数: {len(charts)}")
            
            # 各チャートの詳細検証
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
                with self.subTest(chart=chart_name):
                    self.assertIn(chart_name, charts, f"{chart_name} チャートが生成されていません")
                    self.assertIsInstance(charts[chart_name], str, f"{chart_name} チャートがHTML文字列ではありません")
                    self.assertGreater(len(charts[chart_name]), 100, f"{chart_name} チャートの内容が短すぎます")
            
            print("✅ 全てのチャートが正常に生成されました")
    
    def test_data_distribution_validation(self):
        """データ分布の妥当性を検証"""
        print(f"\n=== データ分布の妥当性検証 ===")
        
        # DataFetcherのモック設定（多様なデータ生成）
        def mock_get_historical_data_diverse(ticker, start_date, end_date):
            stock_data = self._create_realistic_stock_data(ticker, start_date, end_date)
            if stock_data is None:
                return None
            
            # 意図的に多様な価格変化パターンを作成
            ticker_index = hash(ticker) % len(self.realistic_trades_df)
            
            if ticker_index % 5 == 0:
                # 強い上昇トレンド
                multiplier = np.linspace(0.8, 1.3, len(stock_data))
            elif ticker_index % 5 == 1:
                # 強い下降トレンド  
                multiplier = np.linspace(1.2, 0.7, len(stock_data))
            elif ticker_index % 5 == 2:
                # 横ばいトレンド
                multiplier = np.random.normal(1.0, 0.05, len(stock_data))
            elif ticker_index % 5 == 3:
                # ボラタイルな動き
                multiplier = np.random.normal(1.0, 0.15, len(stock_data))
            else:
                # 通常の動き
                multiplier = np.random.normal(1.0, 0.08, len(stock_data))
            
            # 価格にパターンを適用
            base_close = stock_data['close'].iloc[0]
            stock_data['close'] = base_close * multiplier
            stock_data['open'] = stock_data['close'] * np.random.uniform(0.98, 1.02, len(stock_data))
            stock_data['high'] = stock_data[['open', 'close']].max(axis=1) * np.random.uniform(1.0, 1.03, len(stock_data))
            stock_data['low'] = stock_data[['open', 'close']].min(axis=1) * np.random.uniform(0.97, 1.0, len(stock_data))
            
            # 出来高パターン
            if ticker_index % 3 == 0:
                # 高出来高
                stock_data['volume'] = stock_data['volume'] * np.random.uniform(2.0, 4.0, len(stock_data))
            elif ticker_index % 3 == 1:
                # 低出来高
                stock_data['volume'] = stock_data['volume'] * np.random.uniform(0.3, 0.7, len(stock_data))
            
            return stock_data
        
        self.mock_data_fetcher.get_historical_data.side_effect = mock_get_historical_data_diverse
        self.mock_data_fetcher.get_fundamentals_data.return_value = {
            'General': {'Sector': 'Technology', 'Industry': 'Software'}
        }
        
        # EPS APIのモック
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = [{'eps': 2.5, 'estimate': 2.0}]
            mock_get.return_value = mock_response
            
            # _add_eps_infoメソッドを直接テスト
            print("EPS情報とテクニカル指標を計算中...")
            enhanced_df = self.analysis_engine._add_eps_info(self.realistic_trades_df)
            
            # データの分布を検証
            print("\n=== 計算結果の分布検証 ===")
            
            # pre_earnings_change の分布
            pre_earnings_values = enhanced_df['pre_earnings_change'].dropna()
            print(f"Pre-earnings変化率:")
            print(f"  件数: {len(pre_earnings_values)}")
            print(f"  範囲: {pre_earnings_values.min():.2f}% - {pre_earnings_values.max():.2f}%")
            print(f"  平均: {pre_earnings_values.mean():.2f}%")
            print(f"  ユニーク値数: {pre_earnings_values.nunique()}")
            
            # 全て同じ値でないことを確認
            self.assertGreater(pre_earnings_values.nunique(), 1, 
                             "pre_earnings_change の値が全て同じです")
            
            # volume_ratio の分布
            volume_values = enhanced_df['volume_ratio'].dropna()
            print(f"\n出来高比率:")
            print(f"  件数: {len(volume_values)}")
            print(f"  範囲: {volume_values.min():.2f} - {volume_values.max():.2f}")
            print(f"  平均: {volume_values.mean():.2f}")
            print(f"  ユニーク値数: {volume_values.nunique()}")
            
            self.assertGreater(volume_values.nunique(), 1, 
                             "volume_ratio の値が全て同じです")
            
            # MA比率の分布
            ma200_values = enhanced_df['price_to_ma200'].dropna()
            ma50_values = enhanced_df['price_to_ma50'].dropna()
            
            print(f"\nMA200比率: 範囲 {ma200_values.min():.2f} - {ma200_values.max():.2f}, ユニーク値数: {ma200_values.nunique()}")
            print(f"MA50比率: 範囲 {ma50_values.min():.2f} - {ma50_values.max():.2f}, ユニーク値数: {ma50_values.nunique()}")
            
            self.assertGreater(ma200_values.nunique(), 1, "MA200比率の値が全て同じです")
            self.assertGreater(ma50_values.nunique(), 1, "MA50比率の値が全て同じです")
            
            print("\n✅ 全ての指標で適切な分布が確認されました")
    
    def test_chart_binning_distribution(self):
        """チャートのビニング分布を詳細に検証"""
        print(f"\n=== チャートビニング分布の詳細検証 ===")
        
        # 明確に異なる値を持つテストデータを作成
        test_df = pd.DataFrame({
            'ticker': ['TEST1', 'TEST2', 'TEST3', 'TEST4', 'TEST5', 'TEST6'],
            'entry_date': ['2024-01-15'] * 6,
            'exit_date': ['2024-01-25'] * 6,
            'pnl': [500.0, -300.0, 800.0, -600.0, 1200.0, -900.0],  # 必要なカラムを追加
            'pnl_rate': [5.0, -5.0, 15.0, -15.0, 25.0, -25.0],
            'sector': ['Technology'] * 6,
            'industry': ['Software'] * 6,
            'pre_earnings_change': [-25.0, -15.0, -5.0, 5.0, 15.0, 25.0],  # 各ビンに1つずつ
            'volume_ratio': [1.2, 1.7, 2.5, 3.5, 4.5, 5.0],  # 各ビンに分散
            'price_to_ma200': [0.85, 0.95, 1.05, 1.15, 1.25, 1.35],  # 各ビンに分散
            'price_to_ma50': [0.90, 0.97, 1.02, 1.07, 1.12, 1.20],  # 各ビンに分散
            'gap': [-2.0, 1.0, 3.0, 6.0, 12.0, 15.0]  # 各ビンに分散
        })
        
        # 各チャートのビニング分布をテスト
        charts_to_test = [
            ('pre_earnings_performance', '_create_pre_earnings_performance_chart'),
            ('volume_trend', '_create_volume_trend_chart'),
            ('ma200_analysis', '_create_ma200_analysis_chart'),
            ('ma50_analysis', '_create_ma50_analysis_chart'),
            ('gap_performance', '_create_gap_performance_chart')
        ]
        
        for chart_name, method_name in charts_to_test:
            with self.subTest(chart=chart_name):
                print(f"\n--- {chart_name} チャートのビニング検証 ---")
                
                # チャートを生成
                chart_method = getattr(self.analysis_engine, method_name)
                chart_html = chart_method(test_df)
                
                # HTMLにビンの情報が含まれているかチェック
                self.assertIsInstance(chart_html, str)
                self.assertGreater(len(chart_html), 100)
                
                # チャートに複数のカテゴリが含まれていることを確認
                if chart_name == 'pre_earnings_performance':
                    expected_categories = ['<-20%', '-20~-10%', '-10~0%', '0~10%', '10~20%', '>20%']
                elif chart_name == 'volume_trend':
                    expected_categories = ['1.0-1.5x', '1.5-2.0x', '2.0-3.0x', '3.0-4.0x', '4.0x+']
                elif chart_name == 'gap_performance':
                    expected_categories = ['Negative', '0-2%', '2-5%', '5-10%', '10%+']
                else:
                    expected_categories = ['90%', '100%', '110%', '120%']  # MA charts
                
                found_categories = []
                for category in expected_categories:
                    if category in chart_html or category.replace('%', '\\u0025') in chart_html:
                        found_categories.append(category)
                
                print(f"  期待カテゴリ数: {len(expected_categories)}")
                print(f"  発見カテゴリ数: {len(found_categories)}")
                print(f"  発見カテゴリ: {found_categories}")
                
                # 少なくとも2つ以上のカテゴリがあることを確認
                self.assertGreaterEqual(len(found_categories), 2, 
                                      f"{chart_name}: 複数のカテゴリに分散されていません")
                
                print(f"  ✅ {chart_name} のビニングは正常です")
        
        print(f"\n✅ 全てのチャートで適切なビニング分布が確認されました")
    
    def test_end_to_end_analysis_pipeline(self):
        """エンドツーエンドの分析パイプラインテスト"""
        print(f"\n=== エンドツーエンド分析パイプラインテスト ===")
        
        # リアルなデータフローをシミュレート
        self.mock_data_fetcher.get_historical_data.side_effect = lambda ticker, start_date, end_date: \
            self._create_realistic_stock_data(ticker, start_date, end_date)
        
        self.mock_data_fetcher.get_fundamentals_data.side_effect = lambda ticker: {
            'General': {
                'Sector': np.random.choice(['Technology', 'Healthcare', 'Financials']),
                'Industry': np.random.choice(['Software', 'Biotechnology', 'Banks'])
            }
        }
        
        with patch('requests.get') as mock_get:
            # 多様なEPSデータを返すモック
            def variable_eps_response(*args, **kwargs):
                mock_response = Mock()
                mock_response.status_code = 200
                
                # ティッカーに基づいて異なるEPSパターンを生成
                url = args[0]
                if 'calendar/earnings' in url:
                    params = kwargs.get('params', {})
                    symbols = params.get('symbols', '')
                    ticker_hash = hash(symbols) % 10
                    
                    if ticker_hash < 2:
                        # 高サプライズ
                        eps_data = [{'eps': 3.5, 'estimate': 2.0}]
                    elif ticker_hash < 4:
                        # 低サプライズ
                        eps_data = [{'eps': 1.8, 'estimate': 2.0}]
                    elif ticker_hash < 6:
                        # ミスサプライズ
                        eps_data = [{'eps': 1.5, 'estimate': 2.5}]
                    else:
                        # 標準的なサプライズ
                        eps_data = [{'eps': 2.1, 'estimate': 2.0}]
                    
                    mock_response.json.return_value = eps_data
                else:
                    mock_response.json.return_value = []
                
                return mock_response
            
            mock_get.side_effect = variable_eps_response
            
            print("完全な分析パイプラインを実行中...")
            
            # 完全な分析を実行
            start_time = datetime.now()
            charts = self.analysis_engine.generate_analysis_charts(self.realistic_trades_df)
            end_time = datetime.now()
            
            processing_time = (end_time - start_time).total_seconds()
            print(f"処理時間: {processing_time:.2f}秒")
            
            # 結果の包括的検証
            self.assertIsInstance(charts, dict)
            self.assertGreater(len(charts), 5, "十分な数のチャートが生成されていません")
            
            # 各チャートの品質チェック
            quality_metrics = {}
            for chart_name, chart_html in charts.items():
                # HTMLの基本的な妥当性
                self.assertIsInstance(chart_html, str, f"{chart_name}: HTML文字列ではありません")
                self.assertGreater(len(chart_html), 50, f"{chart_name}: HTML内容が短すぎます")
                
                # Plotlyチャートの要素が含まれているか
                plotly_indicators = ['plotly', 'data', 'layout', 'config']
                plotly_score = sum(1 for indicator in plotly_indicators if indicator in chart_html.lower())
                quality_metrics[chart_name] = plotly_score
                
                self.assertGreater(plotly_score, 0, f"{chart_name}: Plotlyチャートの要素が見つかりません")
            
            print(f"\n=== チャート品質メトリクス ===")
            for chart_name, score in quality_metrics.items():
                print(f"  {chart_name}: {score}/4")
            
            avg_quality = sum(quality_metrics.values()) / len(quality_metrics)
            print(f"平均品質スコア: {avg_quality:.2f}/4")
            
            self.assertGreater(avg_quality, 1.5, "チャートの品質が低すぎます")
            
            print(f"\n✅ エンドツーエンドテストが成功しました")
            print(f"  - 生成チャート数: {len(charts)}")
            print(f"  - 処理時間: {processing_time:.2f}秒")
            print(f"  - 平均品質: {avg_quality:.2f}/4")


if __name__ == '__main__':
    # 詳細な出力でテストを実行
    unittest.main(verbosity=2, buffer=False)