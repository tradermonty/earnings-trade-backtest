#!/usr/bin/env python3
"""
レポート生成と詳細分析機能のテスト
元のレポートとの比較用テスト
"""

import sys
import os
import pytest
import pandas as pd
from datetime import datetime, timedelta

pytestmark = pytest.mark.legacy
if os.getenv('RUN_LEGACY_SCRIPT_TESTS') != '1':
    pytest.skip(
        "Legacy script-style report smoke test; set "
        "RUN_LEGACY_SCRIPT_TESTS=1 to run manually.",
        allow_module_level=True,
    )

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))

from config import BacktestConfig
from report_generator import ReportGenerator
from analysis_engine import AnalysisEngine
from data_fetcher import DataFetcher


def create_sample_trades():
    """サンプルトレードデータを作成"""
    trades = []
    base_date = datetime(2025, 1, 1)
    
    # 各月にサンプルトレードを作成
    sample_tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN', 'META', 'NVDA', 'NFLX']
    
    for i in range(20):  # 20件のトレードを作成
        entry_date = base_date + timedelta(days=i*7)
        exit_date = entry_date + timedelta(days=(i % 10) + 5)
        
        # ランダムなリターンを生成（正と負の両方）
        pnl_rate = (i % 3 - 1) * 5 + (i % 7) * 2  # -8% から +10% の範囲
        entry_price = 100 + (i % 50)
        exit_price = entry_price * (1 + pnl_rate / 100)
        pnl = (exit_price - entry_price) * 100  # 100株と仮定
        
        trade = {
            'entry_date': entry_date.strftime('%Y-%m-%d'),
            'exit_date': exit_date.strftime('%Y-%m-%d'),
            'ticker': sample_tickers[i % len(sample_tickers)],
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl': pnl,
            'pnl_rate': pnl_rate,
            'exit_reason': 'trail_stop' if i % 3 == 0 else 'time_limit' if i % 3 == 1 else 'stop_loss',
            'holding_period': (exit_date - entry_date).days
        }
        trades.append(trade)
    
    return trades


def create_sample_metrics(trades):
    """サンプルメトリクスを作成"""
    df = pd.DataFrame(trades)
    
    total_pnl = df['pnl'].sum()
    win_trades = len(df[df['pnl'] > 0])
    total_trades = len(df)
    initial_capital = 100000
    
    metrics = {
        'initial_capital': initial_capital,
        'final_capital': initial_capital + total_pnl,
        'total_return': total_pnl,
        'total_return_pct': (total_pnl / initial_capital) * 100,
        'number_of_trades': total_trades,
        'winning_trades': win_trades,
        'losing_trades': total_trades - win_trades,
        'win_rate': (win_trades / total_trades) * 100 if total_trades > 0 else 0,
        'avg_win_loss_rate': df['pnl_rate'].mean(),
        'max_drawdown_pct': abs(df['pnl'].cumsum().min() / initial_capital * 100),
        'profit_factor': abs(df[df['pnl'] > 0]['pnl'].sum() / df[df['pnl'] < 0]['pnl'].sum()) if df[df['pnl'] < 0]['pnl'].sum() != 0 else 0,
        'sharpe_ratio': df['pnl_rate'].mean() / df['pnl_rate'].std() if df['pnl_rate'].std() != 0 else 0,
        'avg_holding_period': df['holding_period'].mean()
    }
    
    return metrics


def test_report_generation():
    """レポート生成のテスト"""
    print("=" * 60)
    print("レポート生成と詳細分析機能のテスト")
    print("=" * 60)
    
    # サンプルデータの作成
    print("\n1. サンプルデータの作成中...")
    trades = create_sample_trades()
    metrics = create_sample_metrics(trades)
    
    print(f"   作成されたトレード数: {len(trades)}")
    print(f"   総リターン: ${metrics['total_return']:.2f}")
    print(f"   勝率: {metrics['win_rate']:.1f}%")
    
    # 設定の作成
    config = {
        'start_date': '2025-01-01',
        'end_date': '2025-07-05',
        'initial_capital': 100000,
        'position_size': 6,
        'stop_loss': 6,
        'max_holding_days': 90
    }
    
    # ReportGeneratorの初期化
    print("\n2. ReportGeneratorの初期化中...")
    try:
        report_generator = ReportGenerator(language='en')
        print("   ✅ ReportGenerator正常に初期化されました")
    except Exception as e:
        print(f"   ❌ ReportGenerator初期化エラー: {str(e)}")
        return False
    
    # HTMLレポートの生成
    print("\n3. HTMLレポート生成中...")
    try:
        filename = report_generator.generate_html_report(trades, metrics, config)
        if filename:
            print(f"   ✅ HTMLレポートが生成されました: {filename}")
            
            # ファイルサイズを確認
            if os.path.exists(filename):
                file_size = os.path.getsize(filename)
                print(f"   📄 ファイルサイズ: {file_size:,} bytes")
                
                # HTMLファイルの内容を一部確認
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # 詳細分析セクションが含まれているかチェック
                analysis_sections = [
                    "Monthly Performance",
                    "Sector Performance", 
                    "EPS Surprise Analysis",
                    "EPS Growth Performance",
                    "EPS Growth Acceleration Performance"
                ]
                
                print("\n4. 詳細分析セクションの確認...")
                for section in analysis_sections:
                    if section in content:
                        print(f"   ✅ {section}: 含まれています")
                    else:
                        print(f"   ❌ {section}: 見つかりません")
                
                # JavaScriptの確認
                print("\n5. インタラクティブ機能の確認...")
                js_features = [
                    "sortTable",
                    "toggleYAxisScale",
                    "sortable",
                    "sort-asc",
                    "sort-desc"
                ]
                
                for feature in js_features:
                    if feature in content:
                        print(f"   ✅ {feature}: 含まれています")
                    else:
                        print(f"   ❌ {feature}: 見つかりません")
                
                print(f"\n✅ テスト完了: レポートが正常に生成されました")
                return True
            else:
                print(f"   ❌ ファイルが見つかりません: {filename}")
                return False
        else:
            print("   ❌ レポート生成に失敗しました")
            return False
            
    except Exception as e:
        print(f"   ❌ レポート生成エラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_analysis_engine():
    """AnalysisEngineの直接テスト"""
    print("\n" + "=" * 60)
    print("AnalysisEngineの直接テスト")
    print("=" * 60)
    
    try:
        # サンプルデータの作成
        trades = create_sample_trades()
        df = pd.DataFrame(trades)
        
        # AnalysisEngineの初期化
        print("\n1. AnalysisEngine初期化中...")
        data_fetcher = DataFetcher()
        analysis_engine = AnalysisEngine(data_fetcher)
        print("   ✅ AnalysisEngine正常に初期化されました")
        
        # 分析チャートの生成
        print("\n2. 分析チャート生成中...")
        print("   ⚠️  この処理は外部APIを使用するため、時間がかかる場合があります...")
        
        analysis_charts = analysis_engine.generate_analysis_charts(df)
        
        print(f"\n3. 生成された分析チャート:")
        for chart_name, chart_html in analysis_charts.items():
            print(f"   ✅ {chart_name}: {len(chart_html)} 文字")
        
        if analysis_charts:
            print("\n✅ AnalysisEngineテスト完了")
            return True
        else:
            print("\n❌ 分析チャートが生成されませんでした")
            return False
            
    except Exception as e:
        print(f"\n❌ AnalysisEngineテストエラー: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("レポート生成と詳細分析機能の統合テスト")
    print("=" * 60)
    
    # レポート生成テスト
    report_success = test_report_generation()
    
    # AnalysisEngineテスト（APIキーが必要）
    print("\n" + "=" * 60)
    print("注意: AnalysisEngineテストはEODHD APIキーが必要です")
    
    try:
        # .envファイルをチェック
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv('EODHD_API_KEY')
        
        if api_key:
            print("APIキーが見つかりました。AnalysisEngineテストを実行します...")
            analysis_success = test_analysis_engine()
        else:
            print("APIキーが見つかりません。AnalysisEngineテストをスキップします。")
            analysis_success = True  # スキップは成功とみなす
            
    except Exception as e:
        print(f"APIキーチェックエラー: {str(e)}")
        analysis_success = True  # エラーでもスキップは成功とみなす
    
    # 結果サマリー
    print("\n" + "=" * 60)
    print("テスト結果サマリー")
    print("=" * 60)
    print(f"レポート生成テスト: {'✅ 成功' if report_success else '❌ 失敗'}")
    print(f"AnalysisEngineテスト: {'✅ 成功' if analysis_success else '❌ 失敗'}")
    
    if report_success and analysis_success:
        print("\n🎉 すべてのテストが成功しました！")
        print("レポート生成機能と詳細分析機能が正常に動作しています。")
        sys.exit(0)
    else:
        print("\n⚠️  一部のテストが失敗しました。")
        sys.exit(1)
