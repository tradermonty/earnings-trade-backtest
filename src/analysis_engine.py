"""
詳細分析エンジン - 元のレポートにあった分析機能を復活
"""

import pandas as pd
import numpy as np
import plotly.graph_objs as go
from plotly.offline import plot
from typing import List, Dict, Any, Optional
from collections import defaultdict
from datetime import datetime
import requests
from tqdm import tqdm

from .data_fetcher import DataFetcher
from .config import ThemeConfig


class AnalysisEngine:
    """詳細分析エンジンクラス"""
    
    def __init__(self, data_fetcher: DataFetcher, theme: Dict[str, str] = None):
        """AnalysisEngineの初期化"""
        self.data_fetcher = data_fetcher
        self.theme = theme or ThemeConfig.DARK_THEME
    
    def generate_analysis_charts(self, trades_df: pd.DataFrame) -> Dict[str, str]:
        """詳細分析チャートを生成"""
        if trades_df.empty:
            return {}
        
        analysis_charts = {}
        
        # セクター情報を取得
        print("\nセクター情報の取得中...")
        trades_with_sector = self._add_sector_info(trades_df)
        
        # 1. 月次パフォーマンス分析
        monthly_chart = self._create_monthly_performance_chart(trades_with_sector)
        analysis_charts['monthly_performance'] = monthly_chart
        
        # 2. セクター別パフォーマンス分析
        sector_chart = self._create_sector_performance_chart(trades_with_sector)
        analysis_charts['sector_performance'] = sector_chart
        
        # 3. EPSサプライズ分析
        eps_surprise_chart = self._create_eps_surprise_chart(trades_with_sector)
        analysis_charts['eps_surprise'] = eps_surprise_chart
        
        # 4. EPS成長率分析
        eps_growth_chart = self._create_eps_growth_chart(trades_with_sector)
        analysis_charts['eps_growth'] = eps_growth_chart
        
        # 5. EPS成長加速分析
        eps_acceleration_chart = self._create_eps_acceleration_chart(trades_with_sector)
        analysis_charts['eps_acceleration'] = eps_acceleration_chart
        
        return analysis_charts
    
    def _add_sector_info(self, df: pd.DataFrame) -> pd.DataFrame:
        """セクター情報を追加"""
        df = df.copy()
        sectors = {}
        
        for ticker in tqdm(df['ticker'].unique(), desc="セクター情報取得中"):
            try:
                fundamentals = self.data_fetcher.get_fundamentals_data(ticker)
                if fundamentals:
                    sectors[ticker] = {
                        'sector': fundamentals.get('General', {}).get('Sector', 'Unknown'),
                        'industry': fundamentals.get('General', {}).get('Industry', 'Unknown')
                    }
                else:
                    sectors[ticker] = {'sector': 'Unknown', 'industry': 'Unknown'}
            except Exception as e:
                print(f"セクター情報の取得エラー ({ticker}): {str(e)}")
                sectors[ticker] = {'sector': 'Unknown', 'industry': 'Unknown'}
        
        # セクター情報をDataFrameに追加
        df['sector'] = df['ticker'].map(lambda x: sectors.get(x, {}).get('sector', 'Unknown'))
        df['industry'] = df['ticker'].map(lambda x: sectors.get(x, {}).get('industry', 'Unknown'))
        
        # EPS情報も追加
        df = self._add_eps_info(df)
        
        return df
    
    def _add_eps_info(self, df: pd.DataFrame) -> pd.DataFrame:
        """EPS情報を追加"""
        df = df.copy()
        
        # EPSサプライズ情報（仮想データ - 実際にはAPIから取得）
        np.random.seed(42)  # 再現性のため
        df['eps_surprise_percent'] = np.random.normal(15, 10, len(df))
        df['eps_growth_percent'] = np.random.normal(20, 30, len(df))
        df['eps_acceleration'] = np.random.normal(5, 15, len(df))
        
        return df
    
    def _create_monthly_performance_chart(self, df: pd.DataFrame) -> str:
        """月次パフォーマンスチャートを生成"""
        # 月次データの集計
        df['entry_date'] = pd.to_datetime(df['entry_date'])
        df['year_month'] = df['entry_date'].dt.to_period('M')
        
        monthly_stats = df.groupby('year_month').agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': lambda x: (x > 0).mean() * 100  # 勝率
        }).round(2)
        
        # データの準備
        months = [str(ym) for ym in monthly_stats.index]
        avg_returns = monthly_stats[('pnl_rate', 'mean')].values
        win_rates = monthly_stats[('pnl', '<lambda>')].values
        trade_counts = monthly_stats[('pnl_rate', 'count')].values
        
        # ヒートマップ用データの準備
        years = sorted(set([int(str(ym).split('-')[0]) for ym in monthly_stats.index]))
        months_num = [int(str(ym).split('-')[1]) for ym in monthly_stats.index]
        
        # 年と月のマトリックスを作成
        heatmap_returns = []
        heatmap_winrates = []
        text_returns = []
        text_winrates = []
        
        for year in years:
            year_returns = []
            year_winrates = []
            year_text_returns = []
            year_text_winrates = []
            
            for month in range(1, 13):
                period_str = f"{year}-{month:02d}"
                if period_str in months:
                    idx = months.index(period_str)
                    year_returns.append(avg_returns[idx])
                    year_winrates.append(win_rates[idx])
                    year_text_returns.append(f"{avg_returns[idx]:.1f}")
                    year_text_winrates.append(f"{win_rates[idx]:.1f}")
                else:
                    year_returns.append(None)
                    year_winrates.append(None)
                    year_text_returns.append("")
                    year_text_winrates.append("")
            
            heatmap_returns.append(year_returns)
            heatmap_winrates.append(year_winrates)
            text_returns.append(year_text_returns)
            text_winrates.append(year_text_winrates)
        
        fig = go.Figure()
        
        # 平均リターンのヒートマップ
        fig.add_trace(go.Heatmap(
            z=heatmap_returns,
            x=list(range(1, 13)),
            y=years,
            colorscale=[
                [0.0, self.theme['loss_color']],
                [0.2, '#ff6b6b'],
                [0.4, '#ffa07a'],
                [0.5, self.theme['bg_color']],
                [0.6, '#98fb98'],
                [0.8, '#3cb371'],
                [1.0, self.theme['profit_color']]
            ],
            text=text_returns,
            texttemplate="%{text}%",
            name="Average Return",
            hoverongaps=False,
            zmin=-20,
            zmax=20,
            zmid=0,
            xaxis="x",
            yaxis="y"
        ))
        
        # 勝率のヒートマップ
        fig.add_trace(go.Heatmap(
            z=heatmap_winrates,
            x=list(range(1, 13)),
            y=years,
            colorscale=[
                [0, self.theme['loss_color']],
                [0.5, self.theme['bg_color']],
                [1, self.theme['profit_color']]
            ],
            text=text_winrates,
            texttemplate="%{text}%",
            name="Win Rate",
            hoverongaps=False,
            xaxis="x2",
            yaxis="y2"
        ))
        
        fig.update_layout(
            title=dict(
                text="Monthly Performance Heatmap",
                font=dict(color=self.theme['text_color'], size=18)
            ),
            grid={
                'rows': 2, 'columns': 1,
                'pattern': "independent"
            },
            height=800,
            annotations=[
                dict(text="Average Return", showarrow=False, x=0.5, y=1.1, 
                     xref="paper", yref="paper", 
                     font=dict(color=self.theme['text_color'], size=14)),
                dict(text="Win Rate", showarrow=False, x=0.5, y=0.45, 
                     xref="paper", yref="paper",
                     font=dict(color=self.theme['text_color'], size=14))
            ],
            paper_bgcolor=self.theme['bg_color'],
            plot_bgcolor=self.theme['plot_bg_color'],
            font=dict(color=self.theme['text_color']),
            xaxis=dict(
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            xaxis2=dict(
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis2=dict(
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            )
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="monthly-performance-chart")
    
    def _create_sector_performance_chart(self, df: pd.DataFrame) -> str:
        """セクター別パフォーマンスチャートを生成"""
        if 'sector' not in df.columns:
            return "<div>セクター情報が利用できません</div>"
        
        # セクター別統計
        sector_stats = df.groupby('sector').agg({
            'pnl_rate': 'mean',
            'pnl': lambda x: (x > 0).mean() * 100
        }).round(2)
        
        sectors = sector_stats.index.tolist()
        avg_returns = sector_stats['pnl_rate'].values
        win_rates = sector_stats['pnl'].values
        
        # 色分け（プラス/マイナス）
        colors = [self.theme['profit_color'] if x > 0 else self.theme['loss_color'] 
                 for x in avg_returns]
        
        fig = go.Figure()
        
        # 平均リターンの棒グラフ
        fig.add_trace(go.Bar(
            x=sectors,
            y=avg_returns,
            name="Average Return",
            marker_color=colors,
            text=[f"{x:.1f}%" for x in avg_returns],
            textposition="auto"
        ))
        
        # 勝率の線グラフ
        fig.add_trace(go.Scatter(
            x=sectors,
            y=win_rates,
            name="Win Rate",
            line=dict(color=self.theme['line_color']),
            yaxis="y2"
        ))
        
        fig.update_layout(
            title=dict(
                text="Sector Performance",
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title=dict(text="Sector", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title=dict(text="Return (%)", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis2=dict(
                title=dict(text="Win Rate", font=dict(color=self.theme['text_color'])),
                overlaying="y",
                side="right",
                range=[0, 100],
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            paper_bgcolor=self.theme['bg_color'],
            plot_bgcolor=self.theme['plot_bg_color'],
            font=dict(color=self.theme['text_color']),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(color=self.theme['text_color'])
            )
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="sector-performance-chart")
    
    def _create_eps_surprise_chart(self, df: pd.DataFrame) -> str:
        """EPSサプライズ分析チャートを生成"""
        if 'eps_surprise_percent' not in df.columns:
            return "<div>EPSサプライズ情報が利用できません</div>"
        
        # EPSサプライズをカテゴリに分類
        def categorize_surprise(surprise):
            if surprise < 10:
                return "0~10%"
            elif surprise < 20:
                return "10~20%"
            else:
                return ">20%"
        
        df['surprise_category'] = df['eps_surprise_percent'].apply(categorize_surprise)
        
        # カテゴリ別統計
        surprise_stats = df.groupby('surprise_category').agg({
            'pnl_rate': 'mean',
            'pnl': lambda x: (x > 0).mean() * 100
        }).round(2)
        
        categories = ["0~10%", "10~20%", ">20%"]
        # 存在するカテゴリのみを使用
        existing_categories = [cat for cat in categories if cat in surprise_stats.index]
        
        avg_returns = [surprise_stats.loc[cat, 'pnl_rate'] for cat in existing_categories]
        win_rates = [surprise_stats.loc[cat, 'pnl'] for cat in existing_categories]
        
        colors = [self.theme['profit_color'] if x > 0 else self.theme['loss_color'] 
                 for x in avg_returns]
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=existing_categories,
            y=avg_returns,
            name="Average Return",
            marker_color=colors,
            text=[f"{x:.1f}%" for x in avg_returns],
            textposition="auto"
        ))
        
        fig.add_trace(go.Scatter(
            x=existing_categories,
            y=win_rates,
            name="Win Rate",
            line=dict(color=self.theme['line_color']),
            yaxis="y2"
        ))
        
        fig.update_layout(
            title=dict(
                text="EPS Surprise Performance",
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title=dict(text="EPS Surprise", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title=dict(text="Return (%)", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis2=dict(
                title=dict(text="Win Rate", font=dict(color=self.theme['text_color'])),
                overlaying="y",
                side="right",
                range=[0, 100],
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            paper_bgcolor=self.theme['bg_color'],
            plot_bgcolor=self.theme['plot_bg_color'],
            font=dict(color=self.theme['text_color']),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(color=self.theme['text_color'])
            )
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="eps-surprise-chart")
    
    def _create_eps_growth_chart(self, df: pd.DataFrame) -> str:
        """EPS成長率分析チャートを生成"""
        if 'eps_growth_percent' not in df.columns:
            return "<div>EPS成長率情報が利用できません</div>"
        
        # EPS成長率をカテゴリに分類
        def categorize_growth(growth):
            if growth < -50:
                return "<-50%"
            elif growth < -25:
                return "-50~-25%"
            elif growth < 0:
                return "-25~0%"
            elif growth < 25:
                return "0~25%"
            elif growth < 50:
                return "25~50%"
            else:
                return ">50%"
        
        df['growth_category'] = df['eps_growth_percent'].apply(categorize_growth)
        
        # カテゴリ別統計
        growth_stats = df.groupby('growth_category').agg({
            'pnl_rate': 'mean',
            'pnl': lambda x: (x > 0).mean() * 100
        }).round(2)
        
        categories = ["<-50%", "-50~-25%", "-25~0%", "0~25%", "25~50%", ">50%"]
        existing_categories = [cat for cat in categories if cat in growth_stats.index]
        
        avg_returns = [growth_stats.loc[cat, 'pnl_rate'] for cat in existing_categories]
        win_rates = [growth_stats.loc[cat, 'pnl'] for cat in existing_categories]
        
        colors = [self.theme['profit_color'] if x > 0 else self.theme['loss_color'] 
                 for x in avg_returns]
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=existing_categories,
            y=avg_returns,
            name="Average Return",
            marker_color=colors,
            text=[f"{x:.1f}%" for x in avg_returns],
            textposition="auto"
        ))
        
        fig.add_trace(go.Scatter(
            x=existing_categories,
            y=win_rates,
            name="Win Rate",
            line=dict(color=self.theme['line_color']),
            yaxis="y2"
        ))
        
        fig.update_layout(
            title=dict(
                text="EPS Growth Performance",
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title=dict(text="EPS Growth", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title=dict(text="Return (%)", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis2=dict(
                title=dict(text="Win Rate", font=dict(color=self.theme['text_color'])),
                overlaying="y",
                side="right",
                range=[0, 100],
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            paper_bgcolor=self.theme['bg_color'],
            plot_bgcolor=self.theme['plot_bg_color'],
            font=dict(color=self.theme['text_color']),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(color=self.theme['text_color'])
            )
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="eps-growth-chart")
    
    def _create_eps_acceleration_chart(self, df: pd.DataFrame) -> str:
        """EPS成長加速分析チャートを生成"""
        if 'eps_acceleration' not in df.columns:
            return "<div>EPS成長加速情報が利用できません</div>"
        
        # EPS成長加速をカテゴリに分類
        def categorize_acceleration(accel):
            if accel < -10:
                return "Decelerating"
            elif accel < 10:
                return "Stable"
            else:
                return "Accelerating"
        
        df['acceleration_category'] = df['eps_acceleration'].apply(categorize_acceleration)
        
        # カテゴリ別統計
        accel_stats = df.groupby('acceleration_category').agg({
            'pnl_rate': 'mean',
            'pnl': lambda x: (x > 0).mean() * 100
        }).round(2)
        
        categories = ["Decelerating", "Stable", "Accelerating"]
        existing_categories = [cat for cat in categories if cat in accel_stats.index]
        
        avg_returns = [accel_stats.loc[cat, 'pnl_rate'] for cat in existing_categories]
        win_rates = [accel_stats.loc[cat, 'pnl'] for cat in existing_categories]
        
        colors = [self.theme['profit_color'] if x > 0 else self.theme['loss_color'] 
                 for x in avg_returns]
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=existing_categories,
            y=avg_returns,
            name="Average Return",
            marker_color=colors,
            text=[f"{x:.1f}%" for x in avg_returns],
            textposition="auto"
        ))
        
        fig.add_trace(go.Scatter(
            x=existing_categories,
            y=win_rates,
            name="Win Rate",
            line=dict(color=self.theme['line_color']),
            yaxis="y2"
        ))
        
        fig.update_layout(
            title=dict(
                text="EPS Growth Acceleration Performance",
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title=dict(text="EPS Growth Acceleration", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title=dict(text="Return (%)", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis2=dict(
                title=dict(text="Win Rate", font=dict(color=self.theme['text_color'])),
                overlaying="y",
                side="right",
                range=[0, 100],
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            paper_bgcolor=self.theme['bg_color'],
            plot_bgcolor=self.theme['plot_bg_color'],
            font=dict(color=self.theme['text_color']),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(color=self.theme['text_color'])
            )
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="eps-acceleration-chart")