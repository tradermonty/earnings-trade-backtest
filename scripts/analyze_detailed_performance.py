#!/usr/bin/env python3
"""
詳細パフォーマンス分析スクリプト
earnings_backtest_2020_08_01_2024_12_31_all.csv のデータを分析
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

class DetailedPerformanceAnalyzer:
    def __init__(self, csv_file_path):
        """分析クラスの初期化"""
        self.csv_file_path = csv_file_path
        self.df = None
        self.load_data()
        
    def load_data(self):
        """データの読み込みと前処理"""
        print(f"データを読み込み中: {self.csv_file_path}")
        
        try:
            self.df = pd.read_csv(self.csv_file_path)
            print(f"データ読み込み完了: {len(self.df)}件のトレード")
            
            # 日付列の変換
            self.df['entry_date'] = pd.to_datetime(self.df['entry_date'])
            self.df['exit_date'] = pd.to_datetime(self.df['exit_date'])
            
            # 価格帯分類を追加
            self.df['price_range'] = self.df['entry_price'].apply(self.classify_price_range)
            
            # 市場区分分類を価格ベースで推定（実際のデータがないため）
            self.df['market_cap_estimate'] = self.df['entry_price'].apply(self.estimate_market_cap)
            
            # 年月の追加
            self.df['entry_year'] = self.df['entry_date'].dt.year
            self.df['entry_month'] = self.df['entry_date'].dt.month
            self.df['entry_quarter'] = self.df['entry_date'].dt.quarter
            
            # ポジションサイズ（投資額）の計算
            self.df['position_value'] = self.df['entry_price'] * self.df['shares']
            
            print("前処理完了")
            
        except Exception as e:
            print(f"データ読み込みエラー: {e}")
            return None
    
    def classify_price_range(self, price):
        """価格帯分類"""
        if price >= 100:
            return "High Price (>$100)"
        elif price >= 30:
            return "Mid Price ($30-100)"
        else:
            return "Low Price (<$30)"
    
    def estimate_market_cap(self, price):
        """価格ベースの市場区分推定（簡易版）"""
        if price >= 200:
            return "Mega Cap ($200B+)"
        elif price >= 50:
            return "Large Cap ($10B-$200B)"
        elif price >= 15:
            return "Mid Cap ($2B-$10B)"
        else:
            return "Small Cap ($300M-$2B)"
    
    def basic_statistics(self):
        """基本統計情報"""
        print("\n" + "="*60)
        print("基本統計情報")
        print("="*60)
        
        total_trades = len(self.df)
        winning_trades = len(self.df[self.df['pnl'] > 0])
        losing_trades = len(self.df[self.df['pnl'] <= 0])
        win_rate = (winning_trades / total_trades) * 100
        
        total_pnl = self.df['pnl'].sum()
        avg_return = self.df['pnl_rate'].mean()
        avg_holding_days = self.df['holding_period'].mean()
        
        print(f"総トレード数: {total_trades:,}")
        print(f"勝利トレード: {winning_trades:,} ({win_rate:.1f}%)")
        print(f"敗北トレード: {losing_trades:,} ({100-win_rate:.1f}%)")
        print(f"総損益: ${total_pnl:,.2f}")
        print(f"平均リターン: {avg_return:.2f}%")
        print(f"平均保有日数: {avg_holding_days:.1f}日")
        
        print(f"\n価格統計:")
        print(f"最高エントリー価格: ${self.df['entry_price'].max():,.2f}")
        print(f"最低エントリー価格: ${self.df['entry_price'].min():,.2f}")
        print(f"平均エントリー価格: ${self.df['entry_price'].mean():,.2f}")
        print(f"中央値エントリー価格: ${self.df['entry_price'].median():,.2f}")
        
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_return': avg_return,
            'avg_holding_days': avg_holding_days
        }
    
    def price_range_analysis(self):
        """価格帯別詳細分析"""
        print("\n" + "="*60)
        print("価格帯別パフォーマンス分析")
        print("="*60)
        
        price_analysis = self.df.groupby('price_range').agg({
            'pnl': ['count', 'sum', 'mean'],
            'pnl_rate': ['mean', 'std'],
            'holding_period': 'mean',
            'position_value': ['mean', 'sum'],
            'entry_price': ['min', 'max', 'mean', 'median']
        }).round(2)
        
        # 勝率の計算
        win_rates = self.df.groupby('price_range').apply(
            lambda x: (x['pnl'] > 0).sum() / len(x) * 100
        ).round(1)
        
        print("\n価格帯別統計:")
        for price_range in ['High Price (>$100)', 'Mid Price ($30-100)', 'Low Price (<$30)']:
            if price_range in price_analysis.index:
                stats = price_analysis.loc[price_range]
                win_rate = win_rates[price_range]
                
                print(f"\n{price_range}:")
                print(f"  トレード数: {int(stats[('pnl', 'count')]):,}")
                print(f"  勝率: {win_rate:.1f}%")
                print(f"  平均リターン: {stats[('pnl_rate', 'mean')]:.2f}%")
                print(f"  リターン標準偏差: {stats[('pnl_rate', 'std')]:.2f}%")
                print(f"  総損益: ${stats[('pnl', 'sum')]:,.2f}")
                print(f"  平均保有日数: {stats[('holding_period', 'mean')]:.1f}日")
                print(f"  平均ポジションサイズ: ${stats[('position_value', 'mean')]:,.2f}")
                print(f"  価格レンジ: ${stats[('entry_price', 'min')]:.2f} - ${stats[('entry_price', 'max')]:.2f}")
                print(f"  平均価格: ${stats[('entry_price', 'mean')]:.2f}")
        
        return price_analysis, win_rates
    
    def market_cap_analysis(self):
        """推定市場区分別分析"""
        print("\n" + "="*60)
        print("推定市場区分別パフォーマンス分析")
        print("="*60)
        
        cap_analysis = self.df.groupby('market_cap_estimate').agg({
            'pnl': ['count', 'sum', 'mean'],
            'pnl_rate': ['mean', 'std'],
            'holding_period': 'mean',
            'position_value': ['mean', 'sum'],
            'entry_price': ['min', 'max', 'mean']
        }).round(2)
        
        win_rates = self.df.groupby('market_cap_estimate').apply(
            lambda x: (x['pnl'] > 0).sum() / len(x) * 100
        ).round(1)
        
        print("\n市場区分別統計:")
        for market_cap in cap_analysis.index:
            stats = cap_analysis.loc[market_cap]
            win_rate = win_rates[market_cap]
            
            print(f"\n{market_cap}:")
            print(f"  トレード数: {int(stats[('pnl', 'count')]):,}")
            print(f"  勝率: {win_rate:.1f}%")
            print(f"  平均リターン: {stats[('pnl_rate', 'mean')]:.2f}%")
            print(f"  総損益: ${stats[('pnl', 'sum')]:,.2f}")
            print(f"  平均価格: ${stats[('entry_price', 'mean')]:.2f}")
        
        return cap_analysis, win_rates
    
    def temporal_analysis(self):
        """時系列分析"""
        print("\n" + "="*60)
        print("時系列パフォーマンス分析")
        print("="*60)
        
        # 年別分析
        yearly_stats = self.df.groupby('entry_year').agg({
            'pnl': ['count', 'sum', 'mean'],
            'pnl_rate': 'mean',
            'entry_price': 'mean'
        }).round(2)
        
        yearly_win_rates = self.df.groupby('entry_year').apply(
            lambda x: (x['pnl'] > 0).sum() / len(x) * 100
        ).round(1)
        
        # --- 追加: 年別統計CSVへのエクスポート ---
        yearly_summary = yearly_stats.copy()
        yearly_summary[('pnl', 'win_rate')] = yearly_win_rates
        # 列 MultiIndex をフラットにする
        yearly_summary.columns = ['_'.join(col).strip() for col in yearly_summary.columns.values]

        output_csv = self.csv_file_path.replace('.csv', '_yearly_summary.csv')
        try:
            yearly_summary.to_csv(output_csv)
            print(f"年別統計をCSV出力しました: {output_csv}")
        except Exception as e:
            print(f"年別統計CSV出力エラー: {e}")

        # --- 追加: Barチャートによる年別傾向の可視化 ---
        try:
            fig_year = make_subplots(
                rows=1, cols=3,
                subplot_titles=('年別トレード数', '年別総損益', '年別平均リターン')
            )

            years = [str(y) for y in yearly_stats.index]

            # トレード数
            fig_year.add_trace(go.Bar(
                x=years,
                y=yearly_stats[('pnl', 'count')].values,
                name='Trades',
                marker_color='orange'
            ), row=1, col=1)

            # 総損益
            pnl_vals = yearly_stats[('pnl', 'sum')].values
            pnl_colors = ['green' if x > 0 else 'red' for x in pnl_vals]
            fig_year.add_trace(go.Bar(
                x=years,
                y=pnl_vals,
                name='Total PnL',
                marker_color=pnl_colors
            ), row=1, col=2)

            # 平均リターン
            avg_ret_vals = yearly_stats[('pnl_rate', 'mean')].values
            ret_colors = ['green' if x > 0 else 'red' for x in avg_ret_vals]
            fig_year.add_trace(go.Bar(
                x=years,
                y=avg_ret_vals,
                name='Avg Return %',
                marker_color=ret_colors
            ), row=1, col=3)

            fig_year.update_layout(title_text="年別パフォーマンス概要", showlegend=False, height=400)
            fig_year.show()
        except Exception as e:
            print(f"年別チャート作成エラー: {e}")

        print("\n年別統計:")
        for year in sorted(yearly_stats.index):
            stats = yearly_stats.loc[year]
            win_rate = yearly_win_rates[year]
            
            print(f"\n{year}年:")
            print(f"  トレード数: {int(stats[('pnl', 'count')]):,}")
            print(f"  勝率: {win_rate:.1f}%")
            print(f"  平均リターン: {stats[('pnl_rate', 'mean')]:.2f}%")
            print(f"  総損益: ${stats[('pnl', 'sum')]:,.2f}")
            print(f"  平均エントリー価格: ${stats[('entry_price', 'mean')]:.2f}")
        
        return yearly_stats, yearly_win_rates
    
    def exit_reason_analysis(self):
        """手仕舞い理由別分析"""
        print("\n" + "="*60)
        print("手仕舞い理由別分析")
        print("="*60)
        
        exit_stats = self.df.groupby('exit_reason').agg({
            'pnl': ['count', 'sum', 'mean'],
            'pnl_rate': 'mean',
            'holding_period': 'mean'
        }).round(2)
        
        exit_win_rates = self.df.groupby('exit_reason').apply(
            lambda x: (x['pnl'] > 0).sum() / len(x) * 100
        ).round(1)
        
        print("\n手仕舞い理由別統計:")
        for reason in exit_stats.index:
            stats = exit_stats.loc[reason]
            win_rate = exit_win_rates[reason]
            
            print(f"\n{reason}:")
            print(f"  トレード数: {int(stats[('pnl', 'count')]):,}")
            print(f"  勝率: {win_rate:.1f}%")
            print(f"  平均リターン: {stats[('pnl_rate', 'mean')]:.2f}%")
            print(f"  総損益: ${stats[('pnl', 'sum')]:,.2f}")
            print(f"  平均保有日数: {stats[('holding_period', 'mean')]:.1f}日")
        
        return exit_stats, exit_win_rates

    def yearly_segment_analysis(self):
        """年×価格帯・年×市場区分 詳細分析とCSV出力"""
        print("\n" + "="*60)
        print("年×価格帯・年×市場区分 詳細分析")
        print("="*60)

        # --- 年×価格帯 ---
        price_year = self.df.groupby(['entry_year', 'price_range']).agg({
            'pnl': ['count', 'sum', 'mean'],
            'pnl_rate': 'mean',
            'position_value': 'mean'
        }).round(2)

        # 勝率計算を追加
        win_rate_price = self.df.groupby(['entry_year', 'price_range']).apply(
            lambda x: (x['pnl'] > 0).sum() / len(x) * 100
        ).round(1)
        price_year[('pnl', 'win_rate')] = win_rate_price

        # 列名フラット化
        price_year_flat = price_year.copy()
        price_year_flat.columns = ['_'.join(col).strip() for col in price_year_flat.columns.values]

        price_csv = self.csv_file_path.replace('.csv', '_yearly_price_range_summary.csv')
        try:
            price_year_flat.to_csv(price_csv)
            print(f"年×価格帯サマリーをCSV出力しました: {price_csv}")
        except Exception as e:
            print(f"年×価格帯CSV出力エラー: {e}")

        # --- 年×市場区分 ---
        cap_year = self.df.groupby(['entry_year', 'market_cap_estimate']).agg({
            'pnl': ['count', 'sum', 'mean'],
            'pnl_rate': 'mean',
            'position_value': 'mean'
        }).round(2)

        win_rate_cap = self.df.groupby(['entry_year', 'market_cap_estimate']).apply(
            lambda x: (x['pnl'] > 0).sum() / len(x) * 100
        ).round(1)
        cap_year[('pnl', 'win_rate')] = win_rate_cap

        cap_year_flat = cap_year.copy()
        cap_year_flat.columns = ['_'.join(col).strip() for col in cap_year_flat.columns.values]

        cap_csv = self.csv_file_path.replace('.csv', '_yearly_market_cap_summary.csv')
        try:
            cap_year_flat.to_csv(cap_csv)
            print(f"年×市場区分サマリーをCSV出力しました: {cap_csv}")
        except Exception as e:
            print(f"年×市場区分CSV出力エラー: {e}")

        # コンソール表示（簡潔）
        for year in sorted(self.df['entry_year'].unique()):
            print(f"\n--- {year}年 詳細 ---")
            print("価格帯別:")
            if year in price_year.index.get_level_values(0):
                print(price_year.loc[year])
            print("\n市場区分別:")
            if year in cap_year.index.get_level_values(0):
                print(cap_year.loc[year])

        return price_year, cap_year
 
    def create_visualizations(self):
        """詳細可視化の作成"""
        print("\n" + "="*60)
        print("可視化チャート作成中...")
        print("="*60)
        
        # 1. 価格帯別パフォーマンス
        fig1 = make_subplots(
            rows=2, cols=2,
            subplot_titles=('価格帯別勝率', '価格帯別平均リターン', '価格帯別トレード数', '価格帯別総損益'),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]]
        )
        
        price_stats = self.df.groupby('price_range').agg({
            'pnl': ['count', 'sum'],
            'pnl_rate': 'mean'
        })
        
        price_win_rates = self.df.groupby('price_range').apply(
            lambda x: (x['pnl'] > 0).sum() / len(x) * 100
        )
        
        categories = list(price_stats.index)
        
        # 勝率
        fig1.add_trace(go.Bar(
            x=categories, 
            y=price_win_rates.values,
            name='勝率',
            marker_color='lightblue'
        ), row=1, col=1)
        
        # 平均リターン
        avg_returns = price_stats[('pnl_rate', 'mean')].values
        colors = ['green' if x > 0 else 'red' for x in avg_returns]
        fig1.add_trace(go.Bar(
            x=categories,
            y=avg_returns,
            name='平均リターン',
            marker_color=colors
        ), row=1, col=2)
        
        # トレード数
        fig1.add_trace(go.Bar(
            x=categories,
            y=price_stats[('pnl', 'count')].values,
            name='トレード数',
            marker_color='orange'
        ), row=2, col=1)
        
        # 総損益
        total_pnls = price_stats[('pnl', 'sum')].values
        pnl_colors = ['green' if x > 0 else 'red' for x in total_pnls]
        fig1.add_trace(go.Bar(
            x=categories,
            y=total_pnls,
            name='総損益',
            marker_color=pnl_colors
        ), row=2, col=2)
        
        fig1.update_layout(
            title_text="価格帯別詳細パフォーマンス分析",
            showlegend=False,
            height=800
        )
        
        fig1.show()
        
        # 2. 時系列トレンド分析
        monthly_stats = self.df.groupby([self.df['entry_date'].dt.to_period('M')]).agg({
            'pnl': ['count', 'sum'],
            'pnl_rate': 'mean',
            'entry_price': 'mean'
        })
        
        fig2 = make_subplots(
            rows=2, cols=2,
            subplot_titles=('月別トレード数', '月別総損益', '月別平均リターン', '月別平均エントリー価格')
        )
        
        months = [str(period) for period in monthly_stats.index]
        
        fig2.add_trace(go.Scatter(
            x=months,
            y=monthly_stats[('pnl', 'count')].values,
            mode='lines+markers',
            name='トレード数'
        ), row=1, col=1)
        
        fig2.add_trace(go.Scatter(
            x=months,
            y=monthly_stats[('pnl', 'sum')].values,
            mode='lines+markers',
            name='総損益'
        ), row=1, col=2)
        
        fig2.add_trace(go.Scatter(
            x=months,
            y=monthly_stats[('pnl_rate', 'mean')].values,
            mode='lines+markers',
            name='平均リターン'
        ), row=2, col=1)
        
        fig2.add_trace(go.Scatter(
            x=months,
            y=monthly_stats[('entry_price', 'mean')].values,
            mode='lines+markers',
            name='平均エントリー価格'
        ), row=2, col=2)
        
        fig2.update_layout(
            title_text="時系列トレンド分析",
            showlegend=False,
            height=800
        )
        
        # X軸ラベルを回転
        fig2.update_xaxes(tickangle=45)
        fig2.show()
        
        # 3. 価格分布とリターンの関係
        fig3 = px.scatter(
            self.df, 
            x='entry_price', 
            y='pnl_rate',
            color='price_range',
            size='position_value',
            title='エントリー価格 vs リターン分布',
            labels={
                'entry_price': 'エントリー価格 ($)',
                'pnl_rate': 'リターン (%)',
                'position_value': 'ポジションサイズ'
            }
        )
        fig3.show()
        
        print("可視化完了！")
    
    def advanced_analysis(self):
        """高度な分析"""
        print("\n" + "="*60)
        print("高度な分析")
        print("="*60)
        
        # 価格帯とリターンの相関分析
        print("\n価格帯とパフォーマンスの相関:")
        correlation = self.df['entry_price'].corr(self.df['pnl_rate'])
        print(f"エントリー価格とリターンの相関係数: {correlation:.3f}")
        
        # ボラティリティ分析
        print(f"\nボラティリティ分析:")
        overall_volatility = self.df['pnl_rate'].std()
        print(f"全体のリターン標準偏差: {overall_volatility:.2f}%")
        
        for price_range in ['High Price (>$100)', 'Mid Price ($30-100)', 'Low Price (<$30)']:
            if price_range in self.df['price_range'].values:
                volatility = self.df[self.df['price_range'] == price_range]['pnl_rate'].std()
                print(f"{price_range}のリターン標準偏差: {volatility:.2f}%")
        
        # 最高・最低パフォーマンス
        print(f"\n極値分析:")
        best_trade = self.df.loc[self.df['pnl_rate'].idxmax()]
        worst_trade = self.df.loc[self.df['pnl_rate'].idxmin()]
        
        print(f"最高リターントレード:")
        print(f"  銘柄: {best_trade['ticker']}")
        print(f"  エントリー価格: ${best_trade['entry_price']:.2f}")
        print(f"  リターン: {best_trade['pnl_rate']:.2f}%")
        print(f"  日付: {best_trade['entry_date'].strftime('%Y-%m-%d')}")
        
        print(f"\n最低リターントレード:")
        print(f"  銘柄: {worst_trade['ticker']}")
        print(f"  エントリー価格: ${worst_trade['entry_price']:.2f}")
        print(f"  リターン: {worst_trade['pnl_rate']:.2f}%")
        print(f"  日付: {worst_trade['entry_date'].strftime('%Y-%m-%d')}")
    
    def run_complete_analysis(self):
        """完全分析の実行"""
        print("詳細パフォーマンス分析を開始...")
        
        if self.df is None:
            print("データが読み込まれていません。")
            return
        
        # 各分析の実行
        basic_stats = self.basic_statistics()
        price_analysis, price_win_rates = self.price_range_analysis()
        cap_analysis, cap_win_rates = self.market_cap_analysis()
        temporal_stats, temporal_win_rates = self.temporal_analysis()
        exit_stats, exit_win_rates = self.exit_reason_analysis()

        # 年×詳細分析
        price_year_stats, cap_year_stats = self.yearly_segment_analysis()
        
        # 可視化
        self.create_visualizations()
        
        # 高度な分析
        self.advanced_analysis()
        
        print(f"\n" + "="*60)
        print("分析完了！")
        print("="*60)
        
        return {
            'basic_stats': basic_stats,
            'price_analysis': price_analysis,
            'cap_analysis': cap_analysis,
            'temporal_stats': temporal_stats,
            'exit_stats': exit_stats,
            'price_year_stats': price_year_stats,
            'cap_year_stats': cap_year_stats
        }

if __name__ == "__main__":
    # 分析の実行
    csv_path = "/Users/takueisaotome/PycharmProjects/earnings-trade-backtest/reports/earnings_backtest_2020_08_01_2024_12_31_all.csv"
    
    analyzer = DetailedPerformanceAnalyzer(csv_path)
    results = analyzer.run_complete_analysis()