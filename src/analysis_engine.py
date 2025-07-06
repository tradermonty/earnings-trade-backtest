"""
詳細分析エンジン - 元のレポートにあった分析機能を復活
"""

import pandas as pd
import numpy as np
import plotly.graph_objs as go
from plotly.offline import plot
from typing import List, Dict, Any, Optional
from collections import defaultdict
from datetime import datetime, timedelta
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
        
        # 6. 業界パフォーマンス分析（Top 15）
        industry_chart = self._create_industry_performance_chart(trades_with_sector)
        analysis_charts['industry_performance'] = industry_chart
        
        # 7. ギャップサイズ別パフォーマンス分析
        gap_performance_chart = self._create_gap_performance_chart(trades_with_sector)
        analysis_charts['gap_performance'] = gap_performance_chart
        
        # 8. 決算前トレンド別パフォーマンス分析
        pre_earnings_chart = self._create_pre_earnings_performance_chart(trades_with_sector)
        analysis_charts['pre_earnings_performance'] = pre_earnings_chart
        
        # 9. 出来高トレンド分析
        volume_chart = self._create_volume_trend_chart(trades_with_sector)
        analysis_charts['volume_trend'] = volume_chart
        
        # 10. MA200分析
        ma200_chart = self._create_ma200_analysis_chart(trades_with_sector)
        analysis_charts['ma200_analysis'] = ma200_chart
        
        # 11. MA50分析
        ma50_chart = self._create_ma50_analysis_chart(trades_with_sector)
        analysis_charts['ma50_analysis'] = ma50_chart
        
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
        """EPS情報と追加分析データを追加"""
        df = df.copy()
        
        # EPS情報を取得
        eps_surprise_data = []
        eps_growth_data = []
        eps_acceleration_data = []
        
        for _, trade in df.iterrows():
            try:
                # EODHDからEPSデータを取得
                url = f"https://eodhd.com/api/calendar/earnings"
                params = {
                    'api_token': self.data_fetcher.api_key,
                    'fmt': 'json',
                    'from': (pd.to_datetime(trade['entry_date']) - timedelta(days=5)).strftime('%Y-%m-%d'),
                    'to': trade['entry_date'],
                    'symbols': f"{trade['ticker']}.US"
                }
                
                response = requests.get(url, params=params)
                if response.status_code == 200:
                    earnings_data = response.json()
                    if earnings_data and len(earnings_data) > 0:
                        latest_earnings = earnings_data[-1]
                        
                        # EPSサプライズ率の計算
                        if 'eps' in latest_earnings and 'estimate' in latest_earnings:
                            actual_eps = latest_earnings['eps']
                            estimate_eps = latest_earnings['estimate']
                            if estimate_eps != 0:
                                eps_surprise = ((actual_eps - estimate_eps) / abs(estimate_eps)) * 100
                                eps_surprise_data.append(eps_surprise)
                            else:
                                eps_surprise_data.append(0.0)
                        else:
                            eps_surprise_data.append(0.0)
                        
                        # EPS成長率の計算（前年同期比）
                        # 過去のEPSデータを取得
                        hist_params = {
                            'api_token': self.data_fetcher.api_key,
                            'fmt': 'json',
                            'from': (pd.to_datetime(trade['entry_date']) - timedelta(days=370)).strftime('%Y-%m-%d'),
                            'to': trade['entry_date'],
                            'symbols': f"{trade['ticker']}.US"
                        }
                        
                        hist_response = requests.get(url, params=hist_params)
                        if hist_response.status_code == 200:
                            hist_earnings = hist_response.json()
                            if len(hist_earnings) >= 5:  # 前年同期のデータがある場合
                                current_eps = hist_earnings[-1].get('eps', 0)
                                year_ago_eps = hist_earnings[-5].get('eps', 0)
                                if year_ago_eps != 0:
                                    eps_growth = ((current_eps - year_ago_eps) / abs(year_ago_eps)) * 100
                                    eps_growth_data.append(eps_growth)
                                else:
                                    eps_growth_data.append(0.0)
                            else:
                                eps_growth_data.append(0.0)
                        else:
                            eps_growth_data.append(0.0)
                            
                        # EPS加速度（仮の計算 - 2期前との成長率の差）
                        if len(hist_earnings) >= 9:
                            prev_growth = ((hist_earnings[-5].get('eps', 0) - hist_earnings[-9].get('eps', 0)) / 
                                         abs(hist_earnings[-9].get('eps', 0)) * 100) if hist_earnings[-9].get('eps', 0) != 0 else 0
                            current_growth = eps_growth_data[-1]
                            eps_acceleration_data.append(current_growth - prev_growth)
                        else:
                            eps_acceleration_data.append(0.0)
                    else:
                        eps_surprise_data.append(0.0)
                        eps_growth_data.append(0.0)
                        eps_acceleration_data.append(0.0)
                else:
                    eps_surprise_data.append(0.0)
                    eps_growth_data.append(0.0)
                    eps_acceleration_data.append(0.0)
            except:
                eps_surprise_data.append(0.0)
                eps_growth_data.append(0.0)
                eps_acceleration_data.append(0.0)
        
        df['eps_surprise_percent'] = eps_surprise_data
        df['eps_growth_percent'] = eps_growth_data
        df['eps_acceleration'] = eps_acceleration_data
        
        # ギャップサイズの計算（既存のgapカラムがある場合はそれを使用）
        if 'gap' not in df.columns:
            gap_data = []
            for _, trade in df.iterrows():
                try:
                    # エントリー日とその前日の株価データを取得
                    stock_data = self.data_fetcher.get_historical_data(
                        trade['ticker'],
                        (pd.to_datetime(trade['entry_date']) - timedelta(days=5)).strftime('%Y-%m-%d'),
                        trade['entry_date']
                    )
                    
                    if stock_data is not None and len(stock_data) >= 2:
                        # エントリー日のオープン価格と前日のクローズ価格を取得
                        entry_date_str = trade['entry_date']
                        if entry_date_str in stock_data['date'].values:
                            entry_idx = stock_data[stock_data['date'] == entry_date_str].index[0]
                            if entry_idx > 0:
                                entry_open = stock_data.iloc[entry_idx]['Open']
                                prev_close = stock_data.iloc[entry_idx - 1]['Close']
                                gap = ((entry_open - prev_close) / prev_close) * 100
                                gap_data.append(gap)
                            else:
                                gap_data.append(0.0)
                        else:
                            gap_data.append(0.0)
                    else:
                        gap_data.append(0.0)
                except:
                    gap_data.append(0.0)
            
            df['gap'] = gap_data
        
        # 決算前20日間の価格変化率を計算
        pre_earnings_changes = []
        for _, trade in df.iterrows():
            # 決算前30日間のデータを取得（20日間の変化率を計算するため）
            pre_earnings_start = (pd.to_datetime(trade['entry_date']) - 
                                timedelta(days=30)).strftime('%Y-%m-%d')
            try:
                stock_data = self.data_fetcher.get_historical_data(
                    trade['ticker'],
                    pre_earnings_start,
                    trade['entry_date']
                )
                
                if stock_data is not None and len(stock_data) >= 20:
                    # 20日間の価格変化率を計算
                    price_change = ((stock_data['Close'].iloc[-1] - stock_data['Close'].iloc[-20]) / 
                                  stock_data['Close'].iloc[-20] * 100)
                    pre_earnings_changes.append(price_change)
                else:
                    pre_earnings_changes.append(0.0)  # デフォルト値
            except:
                pre_earnings_changes.append(0.0)  # エラー時のデフォルト値
        
        df['pre_earnings_change'] = pre_earnings_changes
        
        # 出来高関連データを計算
        volume_changes = []
        for _, trade in df.iterrows():
            # 決算前90日間のデータを取得
            pre_earnings_start = (pd.to_datetime(trade['entry_date']) - 
                                timedelta(days=90)).strftime('%Y-%m-%d')
            try:
                stock_data = self.data_fetcher.get_historical_data(
                    trade['ticker'],
                    pre_earnings_start,
                    trade['entry_date']
                )
                
                if stock_data is not None and len(stock_data) >= 60:
                    # 直近20日と過去60日の平均出来高を計算
                    recent_volume = stock_data['Volume'].tail(20).mean()
                    historical_volume = stock_data['Volume'].tail(60).mean()
                    
                    # 出来高比率を計算（recent / historicalの比率）
                    volume_ratio = recent_volume / historical_volume if historical_volume > 0 else 1.0
                    volume_changes.append(volume_ratio)
                else:
                    volume_changes.append(1.0)  # デフォルト値
            except:
                volume_changes.append(1.0)  # エラー時のデフォルト値
        
        df['volume_ratio'] = volume_changes
        
        # 移動平均関連データを計算
        ma200_ratios = []
        ma50_ratios = []
        
        for _, trade in df.iterrows():
            try:
                # 移動平均計算のために十分な期間のデータを取得
                stock_data = self.data_fetcher.get_historical_data(
                    trade['ticker'],
                    (pd.to_datetime(trade['entry_date']) - timedelta(days=250)).strftime('%Y-%m-%d'),
                    trade['entry_date']
                )
                
                if stock_data is not None and len(stock_data) >= 200:
                    # DataFrameに変換してインデックスを設定
                    stock_df = pd.DataFrame(stock_data)
                    stock_df['date'] = pd.to_datetime(stock_df['date'])
                    stock_df.set_index('date', inplace=True)
                    
                    # 移動平均を計算
                    stock_df['MA200'] = stock_df['Close'].rolling(window=200).mean()
                    stock_df['MA50'] = stock_df['Close'].rolling(window=50).mean()
                    
                    # エントリー日の価格と移動平均を取得
                    entry_date_dt = pd.to_datetime(trade['entry_date'])
                    if entry_date_dt in stock_df.index:
                        latest_close = stock_df.loc[entry_date_dt, 'Close']
                        latest_ma200 = stock_df.loc[entry_date_dt, 'MA200']
                        latest_ma50 = stock_df.loc[entry_date_dt, 'MA50']
                        
                        # 価格と移動平均の比率を計算
                        if pd.notna(latest_ma200) and latest_ma200 > 0:
                            ma200_ratio = latest_close / latest_ma200
                            ma200_ratios.append(ma200_ratio)
                        else:
                            ma200_ratios.append(1.0)
                            
                        if pd.notna(latest_ma50) and latest_ma50 > 0:
                            ma50_ratio = latest_close / latest_ma50
                            ma50_ratios.append(ma50_ratio)
                        else:
                            ma50_ratios.append(1.0)
                    else:
                        ma200_ratios.append(1.0)
                        ma50_ratios.append(1.0)
                else:
                    ma200_ratios.append(1.0)
                    ma50_ratios.append(1.0)
            except Exception as e:
                ma200_ratios.append(1.0)
                ma50_ratios.append(1.0)
        
        df['price_to_ma200'] = ma200_ratios
        df['price_to_ma50'] = ma50_ratios
        
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
    
    def _create_industry_performance_chart(self, df: pd.DataFrame) -> str:
        """業界パフォーマンス分析（Top 15）"""
        # 業界別パフォーマンス集計
        industry_perf = df.groupby('industry').agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': 'sum'
        }).round(2)
        
        industry_perf.columns = ['avg_return', 'trade_count', 'total_pnl']
        industry_perf = industry_perf[industry_perf['trade_count'] >= 1]  # 最低1取引
        industry_perf = industry_perf.sort_values('avg_return', ascending=False).head(15)
        
        # チャート作成
        colors = [self.theme['profit_color'] if x > 0 else self.theme['loss_color'] 
                 for x in industry_perf['avg_return']]
        
        fig = go.Figure(data=[
            go.Bar(
                x=industry_perf.index,
                y=industry_perf['avg_return'],
                marker_color=colors,
                text=[f"{val:.1f}%" for val in industry_perf['avg_return']],
                textposition='outside',
                hovertemplate='<b>%{x}</b><br>Avg Return: %{y:.1f}%<br>Trades: %{customdata}<extra></extra>',
                customdata=industry_perf['trade_count']
            )
        ])
        
        # 取引数を追加のトレースとして表示
        fig.add_trace(go.Scatter(
            x=industry_perf.index,
            y=industry_perf['trade_count'],
            mode='lines+markers',
            name='Trade Count',
            line=dict(color=self.theme['line_color'], width=2),
            marker=dict(size=8),
            yaxis='y2',
            hovertemplate='Trade Count: %{y}<extra></extra>'
        ))
        
        fig.update_layout(
            title=dict(
                text='Industry Performance (Top 15)',
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title='Industry',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color']),
                tickangle=-45
            ),
            yaxis=dict(
                title='Average Return (%)',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            yaxis2=dict(
                title='Trade Count',
                overlaying='y',
                side='right',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            paper_bgcolor=self.theme['bg_color'],
            plot_bgcolor=self.theme['plot_bg_color'],
            font=dict(color=self.theme['text_color']),
            height=500,
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
        
        return fig.to_html(include_plotlyjs='cdn', div_id="industry-performance-chart")
    
    def _create_gap_performance_chart(self, df: pd.DataFrame) -> str:
        """ギャップサイズ別パフォーマンス分析"""
        # ギャップサイズ別にグループ化
        df['gap_range'] = pd.cut(df['gap'], 
                               bins=[-float('inf'), 0, 2, 5, 10, float('inf')],
                               labels=['Negative', '0-2%', '2-5%', '5-10%', '10%+'])
        
        gap_perf = df.groupby('gap_range').agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': 'sum'
        }).round(2)
        
        gap_perf.columns = ['avg_return', 'trade_count', 'total_pnl']
        
        # チャート作成
        colors = [self.theme['profit_color'] if x > 0 else self.theme['loss_color'] 
                 for x in gap_perf['avg_return']]
        
        fig = go.Figure(data=[
            go.Bar(
                x=gap_perf.index,
                y=gap_perf['avg_return'],
                marker_color=colors,
                text=[f"{val:.1f}%<br>({count})" for val, count in 
                     zip(gap_perf['avg_return'], gap_perf['trade_count'])],
                textposition='outside',
                hovertemplate='<b>%{x}</b><br>Avg Return: %{y:.1f}%<br>Trades: %{customdata}<extra></extra>',
                customdata=gap_perf['trade_count']
            )
        ])
        
        fig.update_layout(
            title=dict(
                text='Performance by Gap Size',
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title='Gap Size Range',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title='Average Return (%)',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            paper_bgcolor=self.theme['bg_color'],
            plot_bgcolor=self.theme['plot_bg_color'],
            font=dict(color=self.theme['text_color'])
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="gap-performance-chart")
    
    def _create_pre_earnings_performance_chart(self, df: pd.DataFrame) -> str:
        """決算前トレンド別パフォーマンス分析"""
        # 決算前変化率でグループ化（earnings_backtest.pyと同じビン設定）
        df['pre_earnings_range'] = pd.cut(df['pre_earnings_change'], 
                                        bins=[-float('inf'), -20, -10, 0, 10, 20, float('inf')],
                                        labels=['<-20%', '-20~-10%', '-10~0%', '0~10%', '10~20%', '>20%'])
        
        pre_perf = df.groupby('pre_earnings_range').agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': 'sum'
        }).round(2)
        
        pre_perf.columns = ['avg_return', 'trade_count', 'total_pnl']
        
        # チャート作成
        colors = [self.theme['profit_color'] if x > 0 else self.theme['loss_color'] 
                 for x in pre_perf['avg_return']]
        
        fig = go.Figure(data=[
            go.Bar(
                x=pre_perf.index,
                y=pre_perf['avg_return'],
                marker_color=colors,
                text=[f"{val:.1f}%<br>({count})" for val, count in 
                     zip(pre_perf['avg_return'], pre_perf['trade_count'])],
                textposition='outside',
                hovertemplate='<b>%{x}</b><br>Avg Return: %{y:.1f}%<br>Trades: %{customdata}<extra></extra>',
                customdata=pre_perf['trade_count']
            )
        ])
        
        fig.update_layout(
            title=dict(
                text='Performance by Pre-Earnings Trend',
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title='Pre-Earnings 20-Day Change',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title='Average Return (%)',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            paper_bgcolor=self.theme['bg_color'],
            plot_bgcolor=self.theme['plot_bg_color'],
            font=dict(color=self.theme['text_color'])
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="pre-earnings-performance-chart")
    
    def _create_volume_trend_chart(self, df: pd.DataFrame) -> str:
        """出来高トレンド分析"""
        # 出来高比率でグループ化
        df['volume_range'] = pd.cut(df['volume_ratio'], 
                                  bins=[0, 1.5, 2.0, 3.0, 4.0, float('inf')],
                                  labels=['1.0-1.5x', '1.5-2.0x', '2.0-3.0x', '3.0-4.0x', '4.0x+'])
        
        vol_perf = df.groupby('volume_range').agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': 'sum'
        }).round(2)
        
        vol_perf.columns = ['avg_return', 'trade_count', 'total_pnl']
        
        # チャート作成
        colors = [self.theme['profit_color'] if x > 0 else self.theme['loss_color'] 
                 for x in vol_perf['avg_return']]
        
        fig = go.Figure(data=[
            go.Bar(
                x=vol_perf.index,
                y=vol_perf['avg_return'],
                marker_color=colors,
                text=[f"{val:.1f}%<br>({count})" for val, count in 
                     zip(vol_perf['avg_return'], vol_perf['trade_count'])],
                textposition='outside',
                hovertemplate='<b>%{x}</b><br>Avg Return: %{y:.1f}%<br>Trades: %{customdata}<extra></extra>',
                customdata=vol_perf['trade_count']
            )
        ])
        
        fig.update_layout(
            title=dict(
                text='Volume Trend Analysis',
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title='Volume Ratio vs Average',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title='Average Return (%)',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            paper_bgcolor=self.theme['bg_color'],
            plot_bgcolor=self.theme['plot_bg_color'],
            font=dict(color=self.theme['text_color'])
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="volume-trend-chart")
    
    def _create_ma200_analysis_chart(self, df: pd.DataFrame) -> str:
        """MA200分析"""
        # MA200との比率でグループ化
        df['ma200_range'] = pd.cut(df['price_to_ma200'], 
                                 bins=[0, 0.9, 1.0, 1.1, 1.2, float('inf')],
                                 labels=['<90%', '90-100%', '100-110%', '110-120%', '>120%'])
        
        ma200_perf = df.groupby('ma200_range').agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': 'sum'
        }).round(2)
        
        ma200_perf.columns = ['avg_return', 'trade_count', 'total_pnl']
        
        # チャート作成
        colors = [self.theme['profit_color'] if x > 0 else self.theme['loss_color'] 
                 for x in ma200_perf['avg_return']]
        
        fig = go.Figure(data=[
            go.Bar(
                x=ma200_perf.index,
                y=ma200_perf['avg_return'],
                marker_color=colors,
                text=[f"{val:.1f}%<br>({count})" for val, count in 
                     zip(ma200_perf['avg_return'], ma200_perf['trade_count'])],
                textposition='outside',
                hovertemplate='<b>%{x}</b><br>Avg Return: %{y:.1f}%<br>Trades: %{customdata}<extra></extra>',
                customdata=ma200_perf['trade_count']
            )
        ])
        
        fig.update_layout(
            title=dict(
                text='MA200 Analysis',
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title='Price vs MA200',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title='Average Return (%)',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            paper_bgcolor=self.theme['bg_color'],
            plot_bgcolor=self.theme['plot_bg_color'],
            font=dict(color=self.theme['text_color'])
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="ma200-analysis-chart")
    
    def _create_ma50_analysis_chart(self, df: pd.DataFrame) -> str:
        """MA50分析"""
        # MA50との比率でグループ化
        df['ma50_range'] = pd.cut(df['price_to_ma50'], 
                                bins=[0, 0.95, 1.0, 1.05, 1.1, float('inf')],
                                labels=['<95%', '95-100%', '100-105%', '105-110%', '>110%'])
        
        ma50_perf = df.groupby('ma50_range').agg({
            'pnl_rate': ['mean', 'count'],
            'pnl': 'sum'
        }).round(2)
        
        ma50_perf.columns = ['avg_return', 'trade_count', 'total_pnl']
        
        # チャート作成
        colors = [self.theme['profit_color'] if x > 0 else self.theme['loss_color'] 
                 for x in ma50_perf['avg_return']]
        
        fig = go.Figure(data=[
            go.Bar(
                x=ma50_perf.index,
                y=ma50_perf['avg_return'],
                marker_color=colors,
                text=[f"{val:.1f}%<br>({count})" for val, count in 
                     zip(ma50_perf['avg_return'], ma50_perf['trade_count'])],
                textposition='outside',
                hovertemplate='<b>%{x}</b><br>Avg Return: %{y:.1f}%<br>Trades: %{customdata}<extra></extra>',
                customdata=ma50_perf['trade_count']
            )
        ])
        
        fig.update_layout(
            title=dict(
                text='MA50 Analysis',
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title='Price vs MA50',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title='Average Return (%)',
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                title_font=dict(color=self.theme['text_color'])
            ),
            paper_bgcolor=self.theme['bg_color'],
            plot_bgcolor=self.theme['plot_bg_color'],
            font=dict(color=self.theme['text_color'])
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="ma50-analysis-chart")