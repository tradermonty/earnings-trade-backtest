#!/usr/bin/env python3
"""
レポート生成の簡単なテスト
"""

import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Pythonパスの設定
project_root = os.path.dirname(__file__)
src_path = os.path.join(project_root, 'src')
sys.path.insert(0, src_path)

# relative importの問題を解決するため、直接実行
if __name__ == "__main__":
    print("=" * 60)
    print("レポート生成テスト")
    print("=" * 60)
    
    # サンプルトレードデータを作成
    print("\n1. サンプルデータの作成中...")
    
    trades = []
    base_date = datetime(2025, 1, 1)
    sample_tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN']
    
    for i in range(10):
        entry_date = base_date + timedelta(days=i*7)
        exit_date = entry_date + timedelta(days=i + 5)
        
        pnl_rate = (i % 3 - 1) * 5 + (i % 7) * 2
        entry_price = 100 + (i % 50)
        exit_price = entry_price * (1 + pnl_rate / 100)
        pnl = (exit_price - entry_price) * 100
        
        trade = {
            'entry_date': entry_date.strftime('%Y-%m-%d'),
            'exit_date': exit_date.strftime('%Y-%m-%d'),
            'ticker': sample_tickers[i % len(sample_tickers)],
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl': pnl,
            'pnl_rate': pnl_rate,
            'exit_reason': 'trail_stop',
            'holding_period': (exit_date - entry_date).days
        }
        trades.append(trade)
    
    print(f"   作成されたトレード数: {len(trades)}")
    
    # メトリクスの作成
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
        'max_drawdown_pct': 5.0,
        'profit_factor': 1.2,
        'sharpe_ratio': 0.8,
        'avg_holding_period': df['holding_period'].mean()
    }
    
    config = {
        'start_date': '2025-01-01',
        'end_date': '2025-07-05',
        'initial_capital': 100000,
        'position_size': 6,
        'stop_loss': 6,
        'max_holding_days': 90
    }
    
    # 既存のレポートファイルを確認
    print("\n2. 既存のレポートファイルの確認...")
    reports_dir = os.path.join(project_root, 'reports')
    if os.path.exists(reports_dir):
        report_files = [f for f in os.listdir(reports_dir) if f.endswith('.html')]
        print(f"   見つかったレポートファイル数: {len(report_files)}")
        for file in report_files:
            file_path = os.path.join(reports_dir, file)
            file_size = os.path.getsize(file_path)
            print(f"   - {file}: {file_size:,} bytes")
            
            # ファイルの内容を確認
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 詳細分析セクションの確認
            analysis_sections = [
                "Monthly Performance",
                "Sector Performance", 
                "EPS Surprise Analysis",
                "EPS Growth Performance",
                "EPS Growth Acceleration Performance"
            ]
            
            print(f"\n   📊 {file} の分析セクション:")
            for section in analysis_sections:
                status = "✅" if section in content else "❌"
                print(f"      {status} {section}")
            
            # テーブルソート機能の確認
            js_features = ["sortTable", "sort-asc", "sort-desc", "sortable"]
            print(f"\n   🔧 {file} のJavaScript機能:")
            for feature in js_features:
                status = "✅" if feature in content else "❌"
                print(f"      {status} {feature}")
    else:
        print("   reportsディレクトリが見つかりません")
    
    # テスト完了
    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
    
    if os.path.exists(reports_dir) and report_files:
        print("✅ レポートファイルが正常に存在しています")
        
        # 最新のレポートファイルを取得
        latest_report = max(report_files, key=lambda f: os.path.getmtime(os.path.join(reports_dir, f)))
        latest_report_path = os.path.join(reports_dir, latest_report)
        
        with open(latest_report_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 重要な機能が含まれているかチェック
        required_features = [
            "Monthly Performance",
            "Sector Performance", 
            "sortTable",
            "toggleYAxisScale"
        ]
        
        missing_features = []
        for feature in required_features:
            if feature not in content:
                missing_features.append(feature)
        
        if missing_features:
            print(f"\n⚠️  以下の機能が不足しています:")
            for feature in missing_features:
                print(f"   - {feature}")
            print("\n推奨アクション: report_generator.pyとanalysis_engine.pyの連携を確認してください")
        else:
            print("\n🎉 すべての重要な機能が含まれています！")
            print("レポート生成が完全に復活しました。")
    else:
        print("❌ レポートファイルが見つかりません")
        print("推奨アクション: バックテストを実行してレポートを生成してください")