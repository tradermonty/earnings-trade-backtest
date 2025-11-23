"""
Tests for multi_condition_backtest.py
複数条件一括比較バックテストのテスト
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# srcディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts', 'analysis'))


class TestConditionsDefinition(unittest.TestCase):
    """CONDITIONS 定義のテスト"""

    def test_conditions_list_exists(self):
        """CONDITIONS リストが存在すること"""
        from multi_condition_backtest import CONDITIONS
        self.assertIsInstance(CONDITIONS, list)

    def test_conditions_has_four_items(self):
        """CONDITIONS に4つの条件が定義されていること"""
        from multi_condition_backtest import CONDITIONS
        self.assertEqual(len(CONDITIONS), 4)

    def test_baseline_condition_exists(self):
        """baseline 条件が存在すること"""
        from multi_condition_backtest import CONDITIONS
        names = [c["name"] for c in CONDITIONS]
        self.assertIn("baseline", names)

    def test_baseline_condition_values(self):
        """baseline 条件の値が正しいこと"""
        from multi_condition_backtest import CONDITIONS
        baseline = next(c for c in CONDITIONS if c["name"] == "baseline")
        self.assertEqual(baseline["min_surprise"], 5.0)
        self.assertEqual(baseline["max_gap"], 10.0)

    def test_condition_1_values(self):
        """condition_1 の値が正しいこと (Surprise 20%, Gap 3%)"""
        from multi_condition_backtest import CONDITIONS
        cond = next(c for c in CONDITIONS if c["name"] == "condition_1")
        self.assertEqual(cond["min_surprise"], 20.0)
        self.assertEqual(cond["max_gap"], 3.0)

    def test_condition_2_values(self):
        """condition_2 の値が正しいこと (Surprise 20%, Gap 2%)"""
        from multi_condition_backtest import CONDITIONS
        cond = next(c for c in CONDITIONS if c["name"] == "condition_2")
        self.assertEqual(cond["min_surprise"], 20.0)
        self.assertEqual(cond["max_gap"], 2.0)

    def test_condition_3_values(self):
        """condition_3 の値が正しいこと (Surprise 30%, Gap 1%)"""
        from multi_condition_backtest import CONDITIONS
        cond = next(c for c in CONDITIONS if c["name"] == "condition_3")
        self.assertEqual(cond["min_surprise"], 30.0)
        self.assertEqual(cond["max_gap"], 1.0)


class TestCreateConfigFromCondition(unittest.TestCase):
    """条件から BacktestConfig を生成するテスト"""

    def test_create_config_with_baseline(self):
        """baseline 条件から正しい Config が生成されること"""
        from multi_condition_backtest import create_config_from_condition

        condition = {"name": "baseline", "min_surprise": 5.0, "max_gap": 10.0}
        config = create_config_from_condition(
            condition,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )

        self.assertEqual(config.min_surprise_percent, 5.0)
        self.assertEqual(config.max_gap_percent, 10.0)
        self.assertEqual(config.start_date, "2024-01-01")
        self.assertEqual(config.end_date, "2024-12-31")

    def test_create_config_with_custom_condition(self):
        """カスタム条件から正しい Config が生成されること"""
        from multi_condition_backtest import create_config_from_condition

        condition = {"name": "condition_1", "min_surprise": 20.0, "max_gap": 3.0}
        config = create_config_from_condition(
            condition,
            start_date="2024-06-01",
            end_date="2024-06-30"
        )

        self.assertEqual(config.min_surprise_percent, 20.0)
        self.assertEqual(config.max_gap_percent, 3.0)


class TestExtractMetrics(unittest.TestCase):
    """バックテスト結果からメトリクスを抽出するテスト"""

    def test_extract_metrics_from_results(self):
        """結果から正しいメトリクスが抽出されること"""
        from multi_condition_backtest import extract_metrics

        # モックの結果データ
        mock_trades = [
            {"pnl_percent": 5.0, "result": "win"},
            {"pnl_percent": -3.0, "result": "loss"},
            {"pnl_percent": 8.0, "result": "win"},
        ]
        mock_metrics = {
            "total_trades": 3,
            "winning_trades": 2,
            "win_rate": 66.67,
            "avg_return": 3.33,
            "total_return": 10.0,
            "sharpe_ratio": 1.5,
            "max_drawdown": -5.0,
        }

        result = extract_metrics("test_condition", mock_trades, mock_metrics)

        self.assertEqual(result["condition"], "test_condition")
        self.assertEqual(result["trades"], 3)
        self.assertAlmostEqual(result["win_rate"], 66.67, places=2)


class TestCLIArguments(unittest.TestCase):
    """CLI引数パースのテスト"""

    def test_parse_default_arguments(self):
        """デフォルト引数が正しくパースされること"""
        from multi_condition_backtest import parse_arguments

        with patch.object(sys, 'argv', ['multi_condition_backtest.py']):
            args = parse_arguments()

            self.assertIsNotNone(args.start_date)
            self.assertIsNotNone(args.end_date)
            self.assertEqual(args.output_dir, "reports")

    def test_parse_custom_arguments(self):
        """カスタム引数が正しくパースされること"""
        from multi_condition_backtest import parse_arguments

        with patch.object(sys, 'argv', [
            'multi_condition_backtest.py',
            '--start_date', '2024-01-01',
            '--end_date', '2024-06-30',
            '--output_dir', 'custom_reports',
            '--verbose'
        ]):
            args = parse_arguments()

            self.assertEqual(args.start_date, "2024-01-01")
            self.assertEqual(args.end_date, "2024-06-30")
            self.assertEqual(args.output_dir, "custom_reports")
            self.assertTrue(args.verbose)


class TestCompareResults(unittest.TestCase):
    """結果比較のテスト"""

    def test_compare_results_returns_dataframe(self):
        """compare_results が DataFrame を返すこと"""
        import pandas as pd
        from multi_condition_backtest import compare_results

        results = [
            {"condition": "baseline", "trades": 100, "win_rate": 60.0, "avg_pnl": 2.5},
            {"condition": "condition_1", "trades": 50, "win_rate": 65.0, "avg_pnl": 4.5},
        ]

        df = compare_results(results)

        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 2)

    def test_compare_results_columns(self):
        """compare_results の DataFrame が必要なカラムを持つこと"""
        import pandas as pd
        from multi_condition_backtest import compare_results

        results = [
            {"condition": "baseline", "trades": 100, "win_rate": 60.0, "avg_pnl": 2.5},
        ]

        df = compare_results(results)

        self.assertIn("condition", df.columns)
        self.assertIn("trades", df.columns)
        self.assertIn("win_rate", df.columns)
        self.assertIn("avg_pnl", df.columns)


class TestFormatComparisonTable(unittest.TestCase):
    """比較テーブルフォーマットのテスト"""

    def test_format_comparison_table_returns_string(self):
        """format_comparison_table が文字列を返すこと"""
        import pandas as pd
        from multi_condition_backtest import format_comparison_table

        df = pd.DataFrame([
            {"condition": "baseline", "trades": 100, "win_rate": 60.0, "avg_pnl": 2.5},
            {"condition": "condition_1", "trades": 50, "win_rate": 65.0, "avg_pnl": 4.5},
        ])

        result = format_comparison_table(df)

        self.assertIsInstance(result, str)
        self.assertIn("baseline", result)
        self.assertIn("condition_1", result)


if __name__ == '__main__':
    unittest.main()
