#!/usr/bin/env python3
"""
レポート生成の迅速テスト - 実際のバックテストは実行せずにレポート機能のみテスト
"""

import os
import sys
import pandas as pd
from datetime import datetime, timedelta

# srcディレクトリをパスに追加
project_root = os.path.dirname(__file__)
src_path = os.path.join(project_root, 'src')
sys.path.insert(0, src_path)

# 相対インポートの問題を回避するため、モジュールを直接インポート
import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

# 必要なモジュールを読み込み
config_module = load_module("config", os.path.join(src_path, "config.py"))
data_fetcher_module = load_module("data_fetcher", os.path.join(src_path, "data_fetcher.py"))
analysis_engine_module = load_module("analysis_engine", os.path.join(src_path, "analysis_engine.py"))
report_generator_module = load_module("report_generator", os.path.join(src_path, "report_generator.py"))

def create_mock_trades():
    """詳細なモックトレードデータを作成"""
    trades = []
    base_date = datetime(2025, 1, 1)
    
    tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN', 'META', 'NVDA', 'NFLX', 'CRM', 'ORCL']
    
    for i in range(15):
        entry_date = base_date + timedelta(days=i*5)
        exit_date = entry_date + timedelta(days=(i % 8) + 3)
        
        # より現実的なリターン分布
        if i % 4 == 0:  # 25%は大きな利益
            pnl_rate = 8 + (i % 5) * 2
        elif i % 4 == 1:  # 25%は小さな利益
            pnl_rate = 2 + (i % 3)
        elif i % 4 == 2:  # 25%は小さな損失
            pnl_rate = -(1 + (i % 3))
        else:  # 25%は大きな損失
            pnl_rate = -(4 + (i % 4))
        
        entry_price = 80 + (i % 40) + (i * 2)
        exit_price = entry_price * (1 + pnl_rate / 100)
        pnl = (exit_price - entry_price) * 100  # 100株と仮定
        
        exit_reasons = ['trail_stop', 'time_limit', 'stop_loss', 'partial_profit']
        
        trade = {
            'entry_date': entry_date.strftime('%Y-%m-%d'),
            'exit_date': exit_date.strftime('%Y-%m-%d'),
            'ticker': tickers[i % len(tickers)],
            'entry_price': round(entry_price, 2),
            'exit_price': round(exit_price, 2),
            'pnl': round(pnl, 2),
            'pnl_rate': round(pnl_rate, 2),
            'exit_reason': exit_reasons[i % len(exit_reasons)],
            'holding_period': (exit_date - entry_date).days
        }
        trades.append(trade)
    
    return trades

def create_mock_metrics(trades):
    """詳細なモックメトリクスを作成"""
    df = pd.DataFrame(trades)
    
    total_pnl = df['pnl'].sum()
    win_trades = len(df[df['pnl'] > 0])
    total_trades = len(df)
    initial_capital = 100000
    
    winning_pnl = df[df['pnl'] > 0]['pnl'].sum()
    losing_pnl = df[df['pnl'] < 0]['pnl'].sum()
    
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
        'max_drawdown_pct': 8.5,  # 仮の値
        'profit_factor': abs(winning_pnl / losing_pnl) if losing_pnl != 0 else float('inf'),
        'sharpe_ratio': df['pnl_rate'].mean() / df['pnl_rate'].std() if df['pnl_rate'].std() != 0 else 0,
        'avg_holding_period': df['holding_period'].mean()
    }
    
    return metrics

def main():
    print("=" * 70)
    print("📊 レポート生成機能のクイックテスト")
    print("=" * 70)
    
    try:
        # 1. モックデータの作成
        print("\n1. 📋 モックデータの作成中...")
        trades = create_mock_trades()
        metrics = create_mock_metrics(trades)
        
        print(f"   ✅ トレード数: {len(trades)}")
        print(f"   ✅ 総リターン: ${metrics['total_return']:.2f}")
        print(f"   ✅ 勝率: {metrics['win_rate']:.1f}%")
        print(f"   ✅ プロフィットファクター: {metrics['profit_factor']:.2f}")
        
        # 2. 設定の準備
        config = {
            'start_date': '2025-01-01',
            'end_date': '2025-07-05',
            'initial_capital': 100000,
            'position_size': 6,
            'stop_loss': 6,
            'max_holding_days': 90,
            'trail_stop_ma': 21,
            'risk_limit': 6,
            'slippage': 0.3
        }
        
        # 3. ReportGeneratorの初期化（APIキーなしのモック版）
        print("\n2. 🛠️  ReportGeneratorの初期化中...")
        
        # DataFetcherのモック版を作成
        class MockDataFetcher:
            def __init__(self):
                self.api_key = "mock_key"
            def get_fundamentals_data(self, symbol):
                # モックのセクター情報を返す
                sectors = {
                    'AAPL': {'General': {'Sector': 'Technology', 'Industry': 'Consumer Electronics'}},
                    'MSFT': {'General': {'Sector': 'Technology', 'Industry': 'Software'}},
                    'GOOGL': {'General': {'Sector': 'Technology', 'Industry': 'Internet'}},
                    'TSLA': {'General': {'Sector': 'Consumer Cyclical', 'Industry': 'Auto Manufacturers'}},
                    'AMZN': {'General': {'Sector': 'Consumer Cyclical', 'Industry': 'Internet Retail'}},
                    'META': {'General': {'Sector': 'Technology', 'Industry': 'Social Media'}},
                    'NVDA': {'General': {'Sector': 'Technology', 'Industry': 'Semiconductors'}},
                    'NFLX': {'General': {'Sector': 'Communication Services', 'Industry': 'Entertainment'}},
                    'CRM': {'General': {'Sector': 'Technology', 'Industry': 'Software'}},
                    'ORCL': {'General': {'Sector': 'Technology', 'Industry': 'Software'}}
                }
                return sectors.get(symbol, {'General': {'Sector': 'Unknown', 'Industry': 'Unknown'}})
        
        mock_data_fetcher = MockDataFetcher()
        
        # ReportGeneratorを初期化
        report_generator = report_generator_module.ReportGenerator(
            language='en', 
            data_fetcher=mock_data_fetcher
        )
        print("   ✅ ReportGenerator正常に初期化されました")
        
        # 4. HTMLレポートの生成
        print("\n3. 📄 HTMLレポート生成中...")
        print("   ⚠️  分析エンジンが動作します（モックデータ使用）...")
        
        filename = report_generator.generate_html_report(trades, metrics, config)
        
        if filename and os.path.exists(filename):
            file_size = os.path.getsize(filename)
            print(f"   ✅ レポートが生成されました: {filename}")
            print(f"   📊 ファイルサイズ: {file_size:,} bytes")
            
            # 5. 生成されたレポートの検証
            print("\n4. 🔍 レポート内容の検証中...")
            
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 必須セクションの確認
            required_sections = [
                "Performance Summary",
                "Equity Curve", 
                "Monthly Returns",
                "Drawdown Chart",
                "Return Distribution",
                "Trade Details"
            ]
            
            print("   📊 基本セクション:")
            for section in required_sections:
                status = "✅" if section in content else "❌"
                print(f"      {status} {section}")
            
            # 詳細分析セクションの確認
            analysis_sections = [
                "Monthly Performance",
                "Sector Performance", 
                "EPS Surprise Analysis",
                "EPS Growth Performance",
                "EPS Growth Acceleration Performance"
            ]
            
            print("\n   🔬 詳細分析セクション:")
            analysis_count = 0
            for section in analysis_sections:
                if section in content:
                    print(f"      ✅ {section}")
                    analysis_count += 1
                else:
                    print(f"      ❌ {section}")
            
            # JavaScript機能の確認
            js_features = [
                "sortTable",
                "toggleYAxisScale", 
                "sortable",
                "sort-asc",
                "sort-desc"
            ]
            
            print("\n   ⚙️  JavaScript機能:")
            js_count = 0
            for feature in js_features:
                if feature in content:
                    print(f"      ✅ {feature}")
                    js_count += 1
                else:
                    print(f"      ❌ {feature}")
            
            # 結果サマリー
            print("\n" + "=" * 70)
            print("📋 テスト結果サマリー")
            print("=" * 70)
            
            basic_score = sum(1 for section in required_sections if section in content)
            
            print(f"基本セクション: {basic_score}/{len(required_sections)} ({basic_score/len(required_sections)*100:.1f}%)")
            print(f"詳細分析セクション: {analysis_count}/{len(analysis_sections)} ({analysis_count/len(analysis_sections)*100:.1f}%)")
            print(f"JavaScript機能: {js_count}/{len(js_features)} ({js_count/len(js_features)*100:.1f}%)")
            
            if basic_score == len(required_sections) and analysis_count >= 3 and js_count >= 3:
                print("\n🎉 テスト成功！レポート生成機能が正常に動作しています。")
                print("✅ すべての重要な機能が含まれています。")
                return True
            elif basic_score == len(required_sections):
                print("\n⚠️  基本機能は動作していますが、一部の高度な機能が不足しています。")
                return True
            else:
                print("\n❌ 基本機能に問題があります。修正が必要です。")
                return False
        else:
            print("   ❌ レポート生成に失敗しました")
            return False
            
    except Exception as e:
        print(f"\n❌ テスト中にエラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    if success:
        print("\n✅ クイックテスト完了")
        sys.exit(0)
    else:
        print("\n❌ テスト失敗")
        sys.exit(1)