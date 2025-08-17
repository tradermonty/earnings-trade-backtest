#!/usr/bin/env python3
"""
動的ポジションサイズ調整バックテスト実行スクリプト

4つのパターンをサポート:
1. breadth_8ma: シンプル3段階
2. advanced_5stage: 細分化5段階  
3. bearish_signal: Bearish Signal連動
4. bottom_3stage: ボトム検出3段階戦略
"""

import argparse
import sys
import os
import logging
from datetime import datetime, timedelta

# パスの設定
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
sys.path.insert(0, os.path.join(script_dir, '..', 'src'))

from dynamic_position_size import (
    DynamicPositionSizeConfig,
    DynamicPositionSizeBacktest
)


def parse_arguments():
    """コマンドライン引数の解析"""
    parser = argparse.ArgumentParser(
        description='Dynamic Position Size Backtest with Market Breadth Index',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # 基本設定
    default_end_date = datetime.now().strftime('%Y-%m-%d')
    default_start_date = "2020-09-01"  # Market Breadthデータがある期間
    
    parser.add_argument('--start_date', type=str, default=default_start_date,
                        help='Start date (YYYY-MM-DD format)')
    parser.add_argument('--end_date', type=str, default=default_end_date,
                        help='End date (YYYY-MM-DD format)')
    
    # 動的ポジションサイズ設定
    parser.add_argument('--pattern', type=str, default='breadth_8ma',
                        choices=['breadth_8ma', 'advanced_5stage', 'bearish_signal', 'bottom_3stage'],
                        help='Position sizing pattern to use')
    
    parser.add_argument('--breadth_csv', type=str, 
                        default='data/market_breadth_data_20250817_ma8.csv',
                        help='Path to Market Breadth Index CSV file')
    
    # Pattern 1: 基本3段階設定
    parser.add_argument('--stress_position', type=float, default=8.0,
                        help='Position size for stress market (breadth_8ma < 0.4)')
    parser.add_argument('--normal_position', type=float, default=15.0,
                        help='Position size for normal market')
    parser.add_argument('--bullish_position', type=float, default=20.0,
                        help='Position size for bullish market (breadth_8ma >= 0.7)')
    
    # Pattern 2: 細分化5段階設定
    parser.add_argument('--extreme_stress_position', type=float, default=6.0,
                        help='Position size for extreme stress (< 0.3)')
    parser.add_argument('--extreme_bullish_position', type=float, default=25.0,
                        help='Position size for extreme bullish (>= 0.8)')
    
    # Pattern 3: Bearish Signal設定
    parser.add_argument('--bearish_multiplier', type=float, default=0.6,
                        help='Multiplier when bearish signal is active')
    
    # Pattern 4: ボトム検出3段階設定
    parser.add_argument('--bearish_stage_mult', type=float, default=0.7,
                        help='Stage 1: Bearish signal multiplier')
    parser.add_argument('--bottom_8ma_mult', type=float, default=1.3,
                        help='Stage 2: 8MA bottom detection multiplier')
    parser.add_argument('--bottom_200ma_mult', type=float, default=1.6,
                        help='Stage 3: 200MA bottom detection multiplier')
    
    # トレードパラメータ
    parser.add_argument('--stop_loss', type=float, default=10.0,
                        help='Stop loss percentage')
    parser.add_argument('--initial_capital', type=float, default=100000.0,
                        help='Initial capital amount')
    parser.add_argument('--margin_ratio', type=float, default=1.5,
                        help='Margin ratio')
    
    # 制限設定
    parser.add_argument('--min_position', type=float, default=5.0,
                        help='Minimum position size')
    parser.add_argument('--max_position', type=float, default=25.0,
                        help='Maximum position size')
    
    # ログ・出力設定
    parser.add_argument('--enable_logging', action='store_true', default=True,
                        help='Enable detailed logging')
    parser.add_argument('--disable_logging', action='store_true', default=False,
                        help='Disable detailed logging')
    parser.add_argument('--output_dir', type=str, default='reports',
                        help='Output directory for reports')
    
    # 比較実行
    parser.add_argument('--compare_all', action='store_true', default=False,
                        help='Run all 4 patterns and compare results')
    parser.add_argument('--compare_with_base', action='store_true', default=True,
                        help='Compare with base strategy (fixed position size)')
    
    return parser.parse_args()


def create_config_from_args(args) -> DynamicPositionSizeConfig:
    """コマンドライン引数から設定を作成"""
    
    # ログ設定の決定
    enable_logging = args.enable_logging and not args.disable_logging
    
    config = DynamicPositionSizeConfig(
        # 基本設定
        start_date=args.start_date,
        end_date=args.end_date,
        stop_loss=args.stop_loss,
        initial_capital=args.initial_capital,
        margin_ratio=args.margin_ratio,
        
        # 動的ポジションサイズ設定
        position_pattern=args.pattern,
        breadth_csv_path=args.breadth_csv,
        
        # Pattern 1: 基本3段階
        stress_position_size=args.stress_position,
        normal_position_size=args.normal_position,
        bullish_position_size=args.bullish_position,
        
        # Pattern 2: 細分化5段階
        extreme_stress_position=args.extreme_stress_position,
        stress_position=args.stress_position,
        normal_position=args.normal_position,
        bullish_position=args.bullish_position,
        extreme_bullish_position=args.extreme_bullish_position,
        
        # Pattern 3: Bearish Signal
        bearish_reduction_multiplier=args.bearish_multiplier,
        
        # Pattern 4: ボトム検出3段階
        bearish_stage_multiplier=args.bearish_stage_mult,
        bottom_8ma_multiplier=args.bottom_8ma_mult,
        bottom_200ma_multiplier=args.bottom_200ma_mult,
        
        # 制限設定
        min_position_size=args.min_position,
        max_position_size=args.max_position,
        
        # ログ設定
        enable_logging=enable_logging,
        enable_state_tracking=True,
        log_position_changes=enable_logging
    )
    
    return config


def run_single_pattern(config: DynamicPositionSizeConfig, output_dir: str) -> dict:
    """単一パターンでバックテストを実行"""
    
    print(f"\\n{'='*60}")
    print(f"Running Dynamic Position Size Backtest")
    print(f"Pattern: {config.position_pattern}")
    print(f"Description: {config.get_pattern_description()}")
    print(f"Period: {config.start_date} to {config.end_date}")
    print(f"{'='*60}")
    
    try:
        # バックテスト実行
        backtest = DynamicPositionSizeBacktest(config)
        results = backtest.run_backtest()
        
        # 結果表示
        print_results(results, config.position_pattern)
        
        # レポート生成
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(output_dir, 
            f"dynamic_backtest_{config.position_pattern}_{timestamp}.html")
        
        backtest.generate_report(results, report_path)
        
        return results
        
    except Exception as e:
        print(f"Error running backtest: {e}")
        if config.enable_logging:
            logging.exception("Detailed error information:")
        return {}


def run_pattern_comparison(base_config: DynamicPositionSizeConfig, output_dir: str):
    """全4パターンの比較実行"""
    
    print(f"\\n{'='*60}")
    print("Running All Pattern Comparison")
    print(f"{'='*60}")
    
    patterns = ['breadth_8ma', 'advanced_5stage', 'bearish_signal', 'bottom_3stage']
    all_results = {}
    
    for pattern in patterns:
        print(f"\\n--- Running {pattern} ---")
        
        # 設定をコピーしてパターンを変更
        pattern_config = base_config.copy_with_pattern(pattern)
        
        try:
            backtest = DynamicPositionSizeBacktest(pattern_config)
            results = backtest.run_backtest()
            all_results[pattern] = results
            
            # 簡潔な結果表示
            metrics = results.get('metrics', {})
            comparison = results.get('comparison', {})
            
            print(f"  Total Return: {metrics.get('total_return', 0):.2f}%")
            print(f"  Win Rate: {metrics.get('win_rate', 0)*100:.1f}%")
            print(f"  Improvement: {comparison.get('improvement_percentage', 0):+.1f}%")
            
        except Exception as e:
            print(f"  Error in {pattern}: {e}")
            all_results[pattern] = {}
    
    # 比較結果表示
    print_comparison_results(all_results)
    
    # 比較レポート生成
    generate_comparison_report(all_results, base_config, output_dir)


def print_results(results: dict, pattern: str):
    """結果を表示"""
    metrics = results.get('metrics', {})
    comparison = results.get('comparison', {})
    
    print(f"\\n📊 Results for {pattern}:")
    print(f"  Total Trades: {metrics.get('total_trades', 0)}")
    print(f"  Win Rate: {metrics.get('win_rate', 0)*100:.1f}%")
    print(f"  Total Return: {metrics.get('total_return', 0):.2f}%")
    print(f"  Average Return: {metrics.get('avg_return', 0):.2f}%")
    
    if 'position_size_stats' in metrics:
        pos_stats = metrics['position_size_stats']
        print(f"  Avg Position Size: {pos_stats['mean']:.1f}%")
        print(f"  Position Range: {pos_stats['min']:.1f}% - {pos_stats['max']:.1f}%")
    
    if comparison:
        print(f"\\n📈 Improvement vs Base:")
        print(f"  Base Return: {comparison['base_total_return']:.2f}%")
        print(f"  Dynamic Return: {comparison['dynamic_total_return']:.2f}%")
        print(f"  Improvement: {comparison['improvement_absolute']:.2f}% ({comparison['improvement_percentage']:+.1f}%)")


def print_comparison_results(all_results: dict):
    """全パターンの比較結果を表示"""
    
    print(f"\\n{'='*60}")
    print("📊 PATTERN COMPARISON RESULTS")
    print(f"{'='*60}")
    
    # 結果をソート（総リターン順）
    sorted_results = sorted(
        [(pattern, results) for pattern, results in all_results.items() if results],
        key=lambda x: x[1].get('metrics', {}).get('total_return', 0),
        reverse=True
    )
    
    print(f"{'Rank':<4} {'Pattern':<15} {'Return':<10} {'WinRate':<8} {'Improvement':<12} {'AvgPos':<8}")
    print("-" * 65)
    
    for i, (pattern, results) in enumerate(sorted_results, 1):
        metrics = results.get('metrics', {})
        comparison = results.get('comparison', {})
        
        total_return = metrics.get('total_return', 0)
        win_rate = metrics.get('win_rate', 0) * 100
        improvement = comparison.get('improvement_percentage', 0)
        avg_pos = metrics.get('position_size_stats', {}).get('mean', 0)
        
        print(f"{i:<4} {pattern:<15} {total_return:>8.2f}% {win_rate:>6.1f}% {improvement:>+10.1f}% {avg_pos:>6.1f}%")
    
    # 最優秀パターンを強調
    if sorted_results:
        best_pattern, best_results = sorted_results[0]
        best_return = best_results.get('metrics', {}).get('total_return', 0)
        print(f"\\n🏆 Best Pattern: {best_pattern} ({best_return:.2f}% return)")


def generate_comparison_report(all_results: dict, base_config: DynamicPositionSizeConfig, output_dir: str):
    """比較レポートを生成"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(output_dir, f"pattern_comparison_{timestamp}.html")
        
        # 簡易HTMLレポート生成
        html_content = generate_comparison_html(all_results, base_config)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"\\n📄 Comparison report generated: {report_path}")
        
    except Exception as e:
        print(f"Error generating comparison report: {e}")


def generate_comparison_html(all_results: dict, config: DynamicPositionSizeConfig) -> str:
    """比較レポートのHTML生成"""
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dynamic Position Size Pattern Comparison</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
            th {{ background-color: #f2f2f2; }}
            .best {{ background-color: #d4edda; }}
            .config {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <h1>Dynamic Position Size Pattern Comparison Report</h1>
        
        <div class="config">
            <h3>Configuration</h3>
            <p>Period: {config.start_date} to {config.end_date}</p>
            <p>Initial Capital: ${config.initial_capital:,.0f}</p>
            <p>Stop Loss: {config.stop_loss}%</p>
            <p>CSV File: {config.breadth_csv_path}</p>
        </div>
        
        <h2>Pattern Comparison Results</h2>
        <table>
            <tr>
                <th>Pattern</th>
                <th>Total Return (%)</th>
                <th>Win Rate (%)</th>
                <th>Total Trades</th>
                <th>Improvement (%)</th>
                <th>Avg Position Size (%)</th>
            </tr>
    """
    
    # 結果をソート
    sorted_results = sorted(
        [(pattern, results) for pattern, results in all_results.items() if results],
        key=lambda x: x[1].get('metrics', {}).get('total_return', 0),
        reverse=True
    )
    
    for i, (pattern, results) in enumerate(sorted_results):
        metrics = results.get('metrics', {})
        comparison = results.get('comparison', {})
        
        row_class = "best" if i == 0 else ""
        
        html += f"""
            <tr class="{row_class}">
                <td>{pattern}</td>
                <td>{metrics.get('total_return', 0):.2f}</td>
                <td>{metrics.get('win_rate', 0)*100:.1f}</td>
                <td>{metrics.get('total_trades', 0)}</td>
                <td>{comparison.get('improvement_percentage', 0):+.1f}</td>
                <td>{metrics.get('position_size_stats', {}).get('mean', 0):.1f}</td>
            </tr>
        """
    
    html += """
        </table>
        
        <h3>Legend</h3>
        <ul>
            <li><strong>breadth_8ma</strong>: Simple 3-stage adjustment based on Breadth Index 8MA</li>
            <li><strong>advanced_5stage</strong>: Advanced 5-stage refined adjustment</li>
            <li><strong>bearish_signal</strong>: Bearish Signal responsive adjustment</li>
            <li><strong>bottom_3stage</strong>: 3-stage bottom detection strategy</li>
        </ul>
        
        <p><em>Report generated on """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</em></p>
    </body>
    </html>
    """
    
    return html


def main():
    """メイン関数"""
    args = parse_arguments()
    
    # 設定作成
    config = create_config_from_args(args)
    
    print("Dynamic Position Size Backtest System")
    print(f"Market Breadth CSV: {config.breadth_csv_path}")
    print(f"CSV exists: {config.validate_csv_file()}")
    
    # CSVファイル存在確認
    if not config.validate_csv_file():
        print(f"ERROR: Market Breadth CSV file not found: {config.breadth_csv_path}")
        print("Please check the file path and try again.")
        return 1
    
    try:
        if args.compare_all:
            # 全パターン比較実行
            run_pattern_comparison(config, args.output_dir)
        else:
            # 単一パターン実行
            results = run_single_pattern(config, args.output_dir)
            
            if not results:
                return 1
        
        print(f"\\n✅ Dynamic Position Size Backtest completed successfully!")
        return 0
        
    except KeyboardInterrupt:
        print("\\n⚠️  Backtest interrupted by user")
        return 1
    except Exception as e:
        print(f"\\n❌ Backtest failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())