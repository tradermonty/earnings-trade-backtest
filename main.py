#!/usr/bin/env python3
"""
earnings-trade-backtest main entry point
リファクタリング版のメインエントリーポイント
"""

import argparse
from datetime import datetime, timedelta
import sys
import os
import logging  

# srcディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.main import create_backtest_from_args


def parse_arguments():
    """コマンドライン引数の解析"""
    parser = argparse.ArgumentParser(
        description='Earnings-based swing trading backtest system (Default: FMP data source with US stocks only)',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # 日付設定
    default_end_date = datetime.now().strftime('%Y-%m-%d')
    default_start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    parser.add_argument('--start_date', type=str, default=default_start_date,
                        help='Start date (YYYY-MM-DD format)')
    parser.add_argument('--end_date', type=str, default=default_end_date,
                        help='End date (YYYY-MM-DD format)')
    
    # トレードパラメータ
    parser.add_argument('--stop_loss', type=float, default=6.0,
                        help='Stop loss percentage')
    parser.add_argument('--trail_stop_ma', type=int, default=21,
                        help='Trailing stop moving average period')
    parser.add_argument('--max_holding_days', type=int, default=90,
                        help='Maximum holding period in days')
    parser.add_argument('--initial_capital', type=float, default=100000.0,
                        help='Initial capital amount')
    parser.add_argument('--position_size', type=float, default=15.0,
                        help='Position size as percentage of capital')
    parser.add_argument('--slippage', type=float, default=0.3,
                        help='Slippage percentage')
    parser.add_argument('--risk_limit', type=float, default=6.0,
                        help='Risk limit percentage for stopping new trades')
    parser.add_argument('--pre_earnings_change', type=float, default=0.0,
                        help='Minimum price change percentage 20 days before earnings')
    parser.add_argument('--max_gap', type=float, default=10.0,
                        help='Maximum allowable opening gap percentage (stocks with larger gaps will be excluded)')
    parser.add_argument('--min_surprise', type=float, default=5.0,
                        help='Minimum EPS surprise percentage (default: 5.0%%)')
    parser.add_argument('--margin_ratio', type=float, default=1.5,
                        help='Maximum position to capital ratio (default: 1.5x leverage)')
    
    # トレード設定
    parser.add_argument('--no_partial_profit', action='store_true',
                        help='Disable partial profit taking')
    
    # 銘柄フィルタリング (デフォルト: FMP + 全銘柄)
    parser.add_argument('--sp500_only', action='store_true',
                        help='Trade only S&P 500 stocks')
    parser.add_argument('--mid_small_only', action='store_true',
                        help='Trade only mid/small cap stocks')
    
    # 出力設定
    parser.add_argument('--language', type=str, choices=['en', 'ja'], default='en',
                        help='Output language')
    
    # 決算日検証
    parser.add_argument('--enable_date_validation', action='store_true',
                        help='Enable earnings date validation using news analysis')


    # データソース選択 (デフォルト: FMP)
    parser.add_argument('--use_eodhd', action='store_true',
                        help='Use EODHD instead of default FMP data source (requires EODHD_API_KEY)')
    
    # 時価総額ベースフィルタリング (デフォルト: 無効)
    parser.add_argument('--min_market_cap', type=float, default=5.0,
                        help='Minimum market cap in billions for mid/small cap filtering (default: 1.0B)')
    parser.add_argument('--max_market_cap', type=float, default=0.0,
                        help='Maximum market cap in billions (0 または未指定で上限なし)')

    # FMPスクリーナー追加条件
    parser.add_argument('--screener_price_min', type=float, default=30.0,
                        help='Minimum stock price for FMP screener (default: 10)')
    parser.add_argument('--screener_volume_min', type=int, default=200000,
                        help='Minimum average volume for FMP screener (default: 200,000)')
    # Fundamental filters
    parser.add_argument('--max_ps_ratio', type=float, default=None,
                        help='Maximum P/S ratio for screener (optional)')
    parser.add_argument('--max_pe_ratio', type=float, default=None,
                        help='Maximum P/E ratio for screener (optional)')
    parser.add_argument('--min_profit_margin', type=float, default=None,
                        help='Minimum profit margin percentage for screener (optional)')
    
    parser.add_argument('--log_level', default='INFO',
                    choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'])
    
    # 動的ポジションサイズ設定
    parser.add_argument('--dynamic_position', type=str, 
                       choices=['breadth_8ma', 'advanced_5stage', 'bearish_signal', 'bottom_3stage'],
                       help='Enable dynamic position sizing with specified pattern')
    parser.add_argument('--breadth_csv', type=str, 
                       default='data/market_breadth_data_20250817_ma8.csv',
                       help='Market Breadth CSV file path for dynamic sizing')
    
    return parser.parse_args()


def validate_dates(args):
    """日付の妥当性チェック"""
    try:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
        
        if start_date >= end_date:
            print("エラー: 開始日は終了日より前である必要があります。")
            sys.exit(1)
        
        # 開始日が過去10年を超えている場合の警告
        ten_years_ago = datetime.now() - timedelta(days=365*10)
        if start_date < ten_years_ago:
            print("警告: 開始日が10年以上前に設定されています。データが不完全な可能性があります。")
        
    except ValueError:
        print("エラー: 日付は YYYY-MM-DD 形式で入力してください。")
        sys.exit(1)


def main():
    """メイン関数"""
    # コマンドライン引数の解析
    args = parse_arguments()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s:%(name)s:%(message)s",
        force=True
    )
    
    # 日付の妥当性チェック
    validate_dates(args)
    
    # 設定の表示
    print("=== Earnings Trade Backtest (Refactored Version) ===")
    
    if args.language == 'ja':
        print(f"期間: {args.start_date} から {args.end_date}")
        print(f"初期資金: ${args.initial_capital:,.0f}")
        print(f"ポジションサイズ: {args.position_size}%")
        print(f"ストップロス: {args.stop_loss}%")
        print(f"マージン倍率制限: {args.margin_ratio}倍")
        
        if args.sp500_only:
            print("対象: S&P 500銘柄のみ")
        elif getattr(args, 'mid_small_only', False):
            print("対象: 中型・小型株 (S&P 400/600)")
        else:
            print("対象: 全てのアメリカ銘柄")
        
        if getattr(args, 'use_eodhd', False):
            print("データソース: EODHD")
        else:
            print("データソース: Financial Modeling Prep (FMP)")
        
        print(f"言語: 日本語")
    else:
        print(f"Period: {args.start_date} to {args.end_date}")
        print(f"Initial Capital: ${args.initial_capital:,.0f}")
        print(f"Position Size: {args.position_size}%")
        print(f"Stop Loss: {args.stop_loss}%")
        print(f"Margin Ratio Limit: {args.margin_ratio}x")
        
        if args.sp500_only:
            print("Target: S&P 500 stocks only")
        elif getattr(args, 'mid_small_only', False):
            print("Target: Mid/Small-cap stocks (S&P 400/600)")
        else:
            print("Target: All US stocks")
        
        if getattr(args, 'use_eodhd', False):
            print("Data Source: EODHD")
        else:
            print("Data Source: Financial Modeling Prep (FMP)")
        
        print(f"Language: English")
    print("-" * 50)
    
    try:
        # バックテストインスタンスの作成
        backtest = create_backtest_from_args(args)
        
        # バックテストの実行
        results = backtest.execute_backtest()
        
        print("\n" + "=" * 50)
        print("バックテスト完了!")
        
        if results['trades']:
            print(f"実行されたトレード数: {len(results['trades'])}")
            print(f"最終資産: ${results['metrics']['final_capital']:,.2f}")
            print(f"総リターン: {results['metrics']['total_return_pct']:.2f}%")
            print(f"勝率: {results['metrics']['win_rate']:.1f}%")
        else:
            print("実行されたトレードはありませんでした。")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\nバックテストが中断されました。")
        return 1
    except Exception as e:
        print(f"\nエラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())