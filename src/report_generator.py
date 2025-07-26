import pandas as pd
import plotly.graph_objs as go
import webbrowser
from datetime import datetime
from typing import List, Dict, Any
import os

from .config import ThemeConfig, TextConfig
from .analysis_engine import AnalysisEngine
from .data_fetcher import DataFetcher


class ReportGenerator:
    """レポート生成クラス"""
    
    def __init__(self, language: str = 'en', data_fetcher: DataFetcher = None):
        """ReportGeneratorの初期化"""
        self.language = language
        self.theme = ThemeConfig.DARK_THEME
        self.data_fetcher = data_fetcher or DataFetcher()
        self.analysis_engine = AnalysisEngine(self.data_fetcher, self.theme)
    
    def generate_html_report(self, trades: List[Dict[str, Any]], metrics: Dict[str, Any],
                           config: Dict[str, Any], daily_positions_data: Dict[str, Any] = None) -> str:
        """HTMLレポートを生成"""
        if not trades:
            print("トレードデータがないため、レポートを生成できません。")
            return ""
        
        # DataFrameに変換
        df = pd.DataFrame(trades)
        
        # レポートファイル名
        start_date = config.get('start_date', '').replace('-', '_')
        end_date = config.get('end_date', '').replace('-', '_')
        
        if not os.path.exists('reports'):
            os.makedirs('reports')
        
        filename = f"reports/earnings_backtest_report_{start_date}_{end_date}.html"
        
        # 詳細分析チャートを生成
        analysis_charts = self.analysis_engine.generate_analysis_charts(df)
        
        # 日次ポジションチャートを生成
        position_chart = ""
        if daily_positions_data:
            position_chart = self._generate_position_chart(daily_positions_data)
        
        # HTMLコンテンツを生成
        html_content = self._generate_html_content(df, metrics, config, analysis_charts, position_chart)
        
        # ファイルに書き込み
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"\nHTMLレポートを生成しました: {filename}")
        
        # ブラウザで開く
        try:
            webbrowser.open(f'file://{os.path.abspath(filename)}')
            print("ブラウザでレポートを開きました。")
        except Exception as e:
            print(f"ブラウザでの自動オープンに失敗: {e}")
        
        return filename
    
    def _generate_html_content(self, df: pd.DataFrame, metrics: Dict[str, Any],
                              config: Dict[str, Any], analysis_charts: Dict[str, str] = None,
                              position_chart: str = "") -> str:
        """HTMLコンテンツを生成"""
        # 資産曲線のグラフを生成
        equity_chart = self._create_equity_curve_chart(df, metrics)
        
        # 月次リターンのグラフを生成
        monthly_chart = self._create_monthly_returns_chart(df)
        
        # ドローダウンチャートを生成
        drawdown_chart = self._create_drawdown_chart(df, metrics)
        
        # リターン分布チャートを生成
        return_distribution_chart = self._create_return_distribution_chart(df)
        
        # トレード詳細テーブルを生成
        trade_table = self._create_trade_table(df)
        
        # パフォーマンス要約を生成
        performance_summary = self._create_performance_summary(metrics)
        
        # 詳細分析セクションを生成
        analysis_sections = self._create_analysis_sections(analysis_charts or {})
        
        # HTMLテンプレート
        html_template = f"""
<!DOCTYPE html>
<html lang="{self.language}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{TextConfig.get_text('report_title', self.language)}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            background-color: {self.theme['bg_color']};
            color: {self.theme['text_color']};
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background-color: {self.theme['plot_bg_color']};
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        .section {{
            margin-bottom: 30px;
            padding: 20px;
            background-color: {self.theme['plot_bg_color']};
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .metric-card {{
            background-color: {self.theme['bg_color']};
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            border: 1px solid {self.theme['table_border_color']};
        }}
        .metric-value {{
            font-size: 1.5em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .metric-label {{
            font-size: 0.9em;
            opacity: 0.8;
        }}
        .chart-container {{
            margin: 20px 0;
            background-color: {self.theme['plot_bg_color']};
            border-radius: 10px;
            padding: 10px;
        }}
        .trades-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background-color: {self.theme['plot_bg_color']};
            border-radius: 8px;
            border: 1px solid {self.theme['table_border_color']};
        }}
        .trades-table th, .trades-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid {self.theme['table_border_color']};
            border-right: 1px solid {self.theme['table_border_color']};
        }}
        .trades-table th:last-child, .trades-table td:last-child {{
            border-right: none;
        }}
        .trades-table th {{
            background-color: {self.theme['bg_color']};
            font-weight: bold;
            cursor: pointer;
            user-select: none;
            position: relative;
        }}
        .trades-table th:hover {{
            background-color: {self.theme['grid_color']};
        }}
        .trades-table th.sortable:after {{
            content: ' ⇅';
            color: {self.theme['text_color']};
            opacity: 0.5;
        }}
        .trades-table th.sort-asc:after {{
            content: ' ↑';
            color: {self.theme['line_color']};
            opacity: 1;
        }}
        .trades-table th.sort-desc:after {{
            content: ' ↓';
            color: {self.theme['line_color']};
            opacity: 1;
        }}
        .positive {{
            color: {self.theme['profit_color']};
        }}
        .negative {{
            color: {self.theme['loss_color']};
        }}
        .config-section {{
            font-size: 0.9em;
            opacity: 0.8;
        }}
        h1, h2, h3 {{
            color: {self.theme['line_color']};
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{TextConfig.get_text('report_title', self.language)}</h1>
            <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Period: {config.get('start_date', '')} to {config.get('end_date', '')}</p>
        </div>

        <div class="section">
            <h2>{TextConfig.get_text('performance_summary', self.language)}</h2>
            {performance_summary}
        </div>

        <div class="section">
            <h2>{TextConfig.get_text('equity_curve', self.language)}</h2>
            <div class="chart-container">
                {equity_chart}
            </div>
        </div>

        <div class="section">
            <h2>{TextConfig.get_text('monthly_returns', self.language)}</h2>
            <div class="chart-container">
                {monthly_chart}
            </div>
        </div>

        <div class="section">
            <h2>Drawdown Chart</h2>
            <div class="chart-container">
                {drawdown_chart}
            </div>
        </div>

        <div class="section">
            <h2>Return Distribution</h2>
            <div class="chart-container">
                {return_distribution_chart}
            </div>
        </div>

        {f'''
        <div class="section">
            <h2>Daily Position Tracking</h2>
            <div class="chart-container">
                {position_chart}
            </div>
        </div>
        ''' if position_chart else ""}

        {analysis_sections}

        <div class="section">
            <h2>{TextConfig.get_text('trade_details', self.language)}</h2>
            {trade_table}
        </div>

        <div class="section config-section">
            <h3>Configuration</h3>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-value">${config.get('initial_capital', 0):,.0f}</div>
                    <div class="metric-label">Initial Capital</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{config.get('position_size', 0)}%</div>
                    <div class="metric-label">Position Size</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{config.get('stop_loss', 0)}%</div>
                    <div class="metric-label">Stop Loss</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{config.get('max_holding_days', 0)} days</div>
                    <div class="metric-label">Max Holding</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // テーブルソート機能
        function sortTable(table, column, asc = true) {{
            const dirModifier = asc ? 1 : -1;
            const tBody = table.tBodies[0];
            const rows = Array.from(tBody.querySelectorAll("tr"));

            // 行をソート
            const sortedRows = rows.sort((a, b) => {{
                const aColText = a.querySelector(`td:nth-child(${{column + 1}})`).textContent.trim();
                const bColText = b.querySelector(`td:nth-child(${{column + 1}})`).textContent.trim();

                // 日付として比較を試行 (YYYY-MM-DD format)
                const dateRegex = /^\d{{4}}-\d{{2}}-\d{{2}}$/;
                if (dateRegex.test(aColText) && dateRegex.test(bColText)) {{
                    const aDate = new Date(aColText);
                    const bDate = new Date(bColText);
                    return aDate > bDate ? (1 * dirModifier) : (-1 * dirModifier);
                }}

                // 数値として比較を試行
                const aNum = parseFloat(aColText.replace(/[$,%]/g, ''));
                const bNum = parseFloat(bColText.replace(/[$,%]/g, ''));

                if (!isNaN(aNum) && !isNaN(bNum)) {{
                    return aNum > bNum ? (1 * dirModifier) : (-1 * dirModifier);
                }}

                // 文字列として比較
                return aColText > bColText ? (1 * dirModifier) : (-1 * dirModifier);
            }});

            // ソートされた行をテーブルに戻す
            while (tBody.firstChild) {{
                tBody.removeChild(tBody.firstChild);
            }}

            tBody.append(...sortedRows);

            // ヘッダーの見た目を更新
            table.querySelectorAll("th").forEach(th => th.classList.remove("sort-asc", "sort-desc"));
            table.querySelector(`th:nth-child(${{column + 1}})`).classList.toggle("sort-asc", asc);
            table.querySelector(`th:nth-child(${{column + 1}})`).classList.toggle("sort-desc", !asc);
        }}

        // テーブルヘッダーにクリックイベントを追加
        document.addEventListener("DOMContentLoaded", function() {{
            const table = document.querySelector(".trades-table");
            if (table) {{
                const headers = table.querySelectorAll("th");
                headers.forEach((header, index) => {{
                    header.classList.add("sortable");
                    let asc = true;
                    header.addEventListener("click", () => {{
                        const currentIsAscending = header.classList.contains("sort-asc");
                        sortTable(table, index, !currentIsAscending);
                    }});
                }});
            }}

            // ログスケール切り替え機能
            window.toggleYAxisScale = function() {{
                const plotDivs = document.querySelectorAll('.plotly-graph-div');
                plotDivs.forEach(plotDiv => {{
                    if (plotDiv.data && plotDiv.layout) {{
                        const currentType = plotDiv.layout.yaxis.type || 'linear';
                        const newType = currentType === 'log' ? 'linear' : 'log';
                        
                        Plotly.relayout(plotDiv, {{
                            'yaxis.type': newType
                        }});
                    }}
                }});
            }}
        }});
    </script>
</body>
</html>
        """
        
        return html_template
    
    def _create_analysis_sections(self, analysis_charts: Dict[str, str]) -> str:
        """詳細分析セクションを生成"""
        if not analysis_charts:
            return ""
        
        sections = []
        
        # 月次パフォーマンス
        if 'monthly_performance' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>Monthly Performance</h3>
            <div class="chart-container">
                {analysis_charts['monthly_performance']}
            </div>
        </div>
            """)
        
        # セクター別パフォーマンス
        if 'sector_performance' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>Sector Performance</h3>
            <div class="chart-container">
                {analysis_charts['sector_performance']}
            </div>
        </div>
            """)
        
        # 業界パフォーマンス分析（Top 15）
        if 'industry_performance' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>Industry Performance (Top 15)</h3>
            <div class="chart-container">
                {analysis_charts['industry_performance']}
            </div>
        </div>
            """)
        
        # ギャップサイズ別パフォーマンス分析
        if 'gap_performance' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>Performance by Gap Size</h3>
            <div class="chart-container">
                {analysis_charts['gap_performance']}
            </div>
        </div>
            """)
        
        # 決算前トレンド別パフォーマンス分析
        if 'pre_earnings_performance' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>Performance by Pre-Earnings Trend</h3>
            <div class="chart-container">
                {analysis_charts['pre_earnings_performance']}
            </div>
        </div>
            """)
        
        # 出来高トレンド分析
        if 'volume_trend' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>Volume Trend Analysis</h3>
            <div class="chart-container">
                {analysis_charts['volume_trend']}
            </div>
        </div>
            """)
        
        # MA200分析
        if 'ma200_analysis' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>MA200 Analysis</h3>
            <div class="chart-container">
                {analysis_charts['ma200_analysis']}
            </div>
        </div>
            """)
        
        # MA50分析
        if 'ma50_analysis' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>MA50 Analysis</h3>
            <div class="chart-container">
                {analysis_charts['ma50_analysis']}
            </div>
        </div>
            """)
        
        # 時価総額別パフォーマンス分析
        if 'market_cap_performance' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>Market Cap Performance Analysis</h3>
            <div class="chart-container">
                {analysis_charts['market_cap_performance']}
            </div>
        </div>
            """)
        
        # 価格帯別パフォーマンス分析
        if 'price_range_performance' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>Price Range Performance Analysis</h3>
            <div class="chart-container">
                {analysis_charts['price_range_performance']}
            </div>
        </div>
            """)
        
        # EPSサプライズ分析
        if 'eps_surprise' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>EPS Surprise Performance</h3>
            <div class="chart-container">
                {analysis_charts['eps_surprise']}
            </div>
        </div>
            """)
        
        # EPS成長率分析
        if 'eps_growth' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>EPS Growth Performance</h3>
            <div class="chart-container">
                {analysis_charts['eps_growth']}
            </div>
        </div>
            """)
        
        # EPS成長加速分析
        if 'eps_acceleration' in analysis_charts:
            sections.append(f"""
        <div class="section">
            <h3>EPS Growth Acceleration Performance</h3>
            <div class="chart-container">
                {analysis_charts['eps_acceleration']}
            </div>
        </div>
            """)
        
        return '\n'.join(sections)
    
    def _create_equity_curve_chart(self, df: pd.DataFrame, metrics: Dict[str, Any]) -> str:
        """資産曲線のチャートを生成"""
        # 累積損益を計算
        df['cumulative_pnl'] = df['pnl'].cumsum()
        df['equity'] = metrics['initial_capital'] + df['cumulative_pnl']
        
        # 日付でソート
        df_sorted = df.sort_values('entry_date')
        
        fig = go.Figure()
        
        # 資産曲線
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(df_sorted['entry_date']),
            y=df_sorted['equity'],
            mode='lines',
            name=TextConfig.get_text('equity_curve', self.language),
            line=dict(color=self.theme['line_color'], width=2)
        ))
        
        # 初期資本の基準線
        fig.add_hline(
            y=metrics['initial_capital'],
            line_dash="dash",
            line_color=self.theme['text_color'],
            opacity=0.5,
            annotation_text=TextConfig.get_text('initial_capital', self.language)
        )
        
        fig.update_layout(
            title=dict(
                text=TextConfig.get_text('equity_curve', self.language),
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title=dict(text="Date", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title=dict(text="Capital ($)", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            plot_bgcolor=self.theme['plot_bg_color'],
            paper_bgcolor=self.theme['bg_color'],
            font=dict(color=self.theme['text_color']),
            showlegend=True,
            legend=dict(font=dict(color=self.theme['text_color']))
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="equity-chart")
    
    def _create_monthly_returns_chart(self, df: pd.DataFrame) -> str:
        """月次リターンのチャートを生成"""
        # 月次グループ化
        df['month'] = pd.to_datetime(df['entry_date']).dt.to_period('M')
        monthly_returns = df.groupby('month')['pnl'].sum()
        
        # 色分け（プラス/マイナス）
        colors = [self.theme['profit_color'] if x > 0 else self.theme['loss_color'] 
                 for x in monthly_returns.values]
        
        fig = go.Figure(data=[
            go.Bar(
                x=[str(x) for x in monthly_returns.index],
                y=monthly_returns.values,
                marker_color=colors,
                name=TextConfig.get_text('monthly_returns', self.language)
            )
        ])
        
        fig.update_layout(
            title=dict(
                text=TextConfig.get_text('monthly_returns', self.language),
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title=dict(text="Month", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title=dict(text="P&L ($)", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            plot_bgcolor=self.theme['plot_bg_color'],
            paper_bgcolor=self.theme['bg_color'],
            font=dict(color=self.theme['text_color']),
            showlegend=False
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="monthly-chart")
    
    def _create_drawdown_chart(self, df: pd.DataFrame, metrics: Dict[str, Any]) -> str:
        """ドローダウンチャートを生成"""
        # 累積損益を計算
        df_sorted = df.sort_values('entry_date')
        df_sorted['cumulative_pnl'] = df_sorted['pnl'].cumsum()
        df_sorted['equity'] = metrics['initial_capital'] + df_sorted['cumulative_pnl']
        df_sorted['equity_pct'] = (df_sorted['equity'] / metrics['initial_capital'] - 1) * 100
        
        # ドローダウンを計算（正しい方法）
        df_sorted['running_max'] = df_sorted['equity'].cummax()
        df_sorted['drawdown_pct'] = ((df_sorted['running_max'] - df_sorted['equity']) / df_sorted['running_max'] * 100)
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(df_sorted['entry_date']),
            y=-df_sorted['drawdown_pct'],  # 負の値で表示
            mode='lines',
            name='Drawdown',
            line=dict(color=self.theme['loss_color']),
            fill='tonexty'
        ))
        
        fig.update_layout(
            title=dict(
                text="Drawdown Chart",
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title=dict(text="Date", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title=dict(text="Drawdown (%)", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            plot_bgcolor=self.theme['plot_bg_color'],
            paper_bgcolor=self.theme['bg_color'],
            font=dict(color=self.theme['text_color']),
            showlegend=True,
            legend=dict(font=dict(color=self.theme['text_color']))
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="drawdown-chart")
    
    def _create_return_distribution_chart(self, df: pd.DataFrame) -> str:
        """リターン分布チャートを生成"""
        # 正と負のリターンを分離
        positive_returns = df[df['pnl_rate'] > 0]['pnl_rate']
        negative_returns = df[df['pnl_rate'] <= 0]['pnl_rate']
        
        fig = go.Figure()
        
        # 負のリターンのヒストグラム
        if not negative_returns.empty:
            fig.add_trace(go.Histogram(
                x=negative_returns,
                name="Negative Returns",
                marker_color=self.theme['loss_color'],
                opacity=0.7,
                xbins=dict(start=-10, end=0, size=2.5),
                hovertemplate="リターン: %{x:.1f}%<br>取引数: %{y}<extra></extra>"
            ))
        
        # 正のリターンのヒストグラム
        if not positive_returns.empty:
            fig.add_trace(go.Histogram(
                x=positive_returns,
                name="Positive Returns",
                marker_color=self.theme['profit_color'],
                opacity=0.7,
                xbins=dict(start=0, end=positive_returns.max() + 5, size=2.5),
                hovertemplate="リターン: %{x:.1f}%<br>取引数: %{y}<extra></extra>"
            ))
        
        fig.update_layout(
            title=dict(
                text="Return Distribution",
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title=dict(text="Return (%)", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            yaxis=dict(
                title=dict(text="Number of Trades", font=dict(color=self.theme['text_color'])),
                gridcolor=self.theme['grid_color'],
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color'])
            ),
            plot_bgcolor=self.theme['plot_bg_color'],
            paper_bgcolor=self.theme['bg_color'],
            font=dict(color=self.theme['text_color']),
            showlegend=True,
            legend=dict(font=dict(color=self.theme['text_color'])),
            barmode='overlay'
        )
        
        return fig.to_html(include_plotlyjs='cdn', div_id="return-distribution-chart")
    
    def _generate_position_chart(self, daily_positions_data: Dict[str, Any]) -> str:
        """日次ポジション総額チャートを生成"""
        daily_positions = daily_positions_data.get('daily_positions', {})
        
        if not daily_positions:
            return ""
        
        # データをソート
        sorted_dates = sorted(daily_positions.keys())
        dates = [datetime.strptime(date, '%Y-%m-%d') for date in sorted_dates]
        total_values = [daily_positions[date]['total_value'] for date in sorted_dates]
        num_positions = [daily_positions[date]['num_positions'] for date in sorted_dates]
        
        # メインチャートの作成
        fig = go.Figure()
        
        # ポジション総額
        fig.add_trace(go.Scatter(
            x=dates,
            y=total_values,
            mode='lines+markers',
            name='Total Position Value',
            line=dict(color=self.theme['line_color'], width=2),
            marker=dict(size=4),
            hovertemplate='Date: %{x}<br>Position Value: $%{y:,.0f}<extra></extra>'
        ))
        
        # ポジション数（右軸）
        fig.add_trace(go.Scatter(
            x=dates,
            y=num_positions,
            mode='lines+markers',
            name='Number of Positions',
            line=dict(color=self.theme['profit_color'], width=2, dash='dash'),
            marker=dict(size=4),
            yaxis='y2',
            hovertemplate='Date: %{x}<br>Positions: %{y}<extra></extra>'
        ))
        
        # レイアウト設定
        fig.update_layout(
            title=dict(
                text='Daily Position Tracking',
                font=dict(color=self.theme['text_color'], size=18)
            ),
            xaxis=dict(
                title=dict(text='Date', font=dict(color=self.theme['text_color'])),
                gridcolor='rgba(255, 255, 255, 0.1)',
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                showgrid=True
            ),
            yaxis=dict(
                title=dict(text='Position Value ($)', font=dict(color=self.theme['text_color'])),
                gridcolor='rgba(255, 255, 255, 0.1)',
                tickcolor=self.theme['text_color'],
                tickfont=dict(color=self.theme['text_color']),
                side='left',
                showgrid=True
            ),
            yaxis2=dict(
                title=dict(text='Number of Positions', font=dict(color=self.theme['text_color'])),
                overlaying='y',
                side='right',
                tickfont=dict(color=self.theme['text_color']),
                showgrid=False
            ),
            plot_bgcolor=self.theme['plot_bg_color'],
            paper_bgcolor=self.theme['bg_color'],
            font=dict(color=self.theme['text_color']),
            showlegend=True,
            legend=dict(font=dict(color=self.theme['text_color'])),
            template=None  # テンプレートを無効化
        )
        
        # 最終的にグリッド色を強制的に適用
        fig.update_xaxes(gridcolor='rgba(255, 255, 255, 0.1)', showgrid=True)
        fig.update_yaxes(gridcolor='rgba(255, 255, 255, 0.1)', showgrid=True)
        
        return fig.to_html(include_plotlyjs='cdn', div_id="position-chart", config={'responsive': True})
    
    def _create_performance_summary(self, metrics: Dict[str, Any]) -> str:
        """パフォーマンス要約を生成"""
        summary_metrics = [
            ('total_trades', TextConfig.get_text('total_trades', self.language), 
             f"{metrics.get('number_of_trades', 0)}"),
            ('win_rate', TextConfig.get_text('win_rate', self.language), 
             f"{metrics.get('win_rate', 0):.1f}%"),
            ('avg_return', TextConfig.get_text('avg_return', self.language), 
             f"{metrics.get('avg_win_loss_rate', 0):.2f}%"),
            ('total_return', TextConfig.get_text('total_return', self.language), 
             f"{metrics.get('total_return_pct', 0):.2f}%"),
            ('max_drawdown', TextConfig.get_text('max_drawdown', self.language), 
             f"{metrics.get('max_drawdown_pct', 0):.2f}%"),
            ('profit_factor', TextConfig.get_text('profit_factor', self.language), 
             f"{metrics.get('profit_factor', 0):.2f}"),
            ('sharpe_ratio', TextConfig.get_text('sharpe_ratio', self.language), 
             f"{metrics.get('sharpe_ratio', 0):.2f}"),
            ('avg_holding_days', TextConfig.get_text('avg_holding_days', self.language), 
             f"{metrics.get('avg_holding_period', 0):.1f}")
        ]
        
        html = '<div class="metrics-grid">'
        for key, label, value in summary_metrics:
            color_class = ""
            if key in ['total_return', 'win_rate', 'profit_factor', 'sharpe_ratio']:
                try:
                    num_value = float(value.replace('%', ''))
                    color_class = "positive" if num_value > 0 else "negative"
                except:
                    pass
            elif key == 'max_drawdown':
                color_class = "negative"
            
            html += f'''
            <div class="metric-card">
                <div class="metric-value {color_class}">{value}</div>
                <div class="metric-label">{label}</div>
            </div>
            '''
        
        html += '</div>'
        return html
    
    def _create_trade_table(self, df: pd.DataFrame) -> str:
        """トレード詳細テーブルを生成"""
        # 必要な列のみを選択し、表示用にフォーマット
        display_df = df.copy()
        
        # 列名を多言語対応
        column_mapping = {
            'entry_date': TextConfig.get_text('entry_date', self.language),
            'exit_date': TextConfig.get_text('exit_date', self.language),
            'ticker': TextConfig.get_text('symbol', self.language),
            'entry_price': TextConfig.get_text('entry_price', self.language),
            'exit_price': TextConfig.get_text('exit_price', self.language),
            'pnl': TextConfig.get_text('return', self.language),
            'pnl_rate': 'Return %',
            'exit_reason': TextConfig.get_text('exit_reason', self.language),
            'holding_period': TextConfig.get_text('holdings_days', self.language)
        }
        
        # 表示する列を選択
        columns_to_show = ['entry_date', 'exit_date', 'ticker', 'entry_price', 
                          'exit_price', 'pnl', 'pnl_rate', 'exit_reason', 'holding_period']
        
        display_df = display_df[columns_to_show]
        display_df = display_df.rename(columns=column_mapping)
        
        # 数値のフォーマット
        if TextConfig.get_text('entry_price', self.language) in display_df.columns:
            display_df[TextConfig.get_text('entry_price', self.language)] = \
                display_df[TextConfig.get_text('entry_price', self.language)].apply(lambda x: f"${x:.2f}")
        if TextConfig.get_text('exit_price', self.language) in display_df.columns:
            display_df[TextConfig.get_text('exit_price', self.language)] = \
                display_df[TextConfig.get_text('exit_price', self.language)].apply(lambda x: f"${x:.2f}")
        if TextConfig.get_text('return', self.language) in display_df.columns:
            display_df[TextConfig.get_text('return', self.language)] = \
                display_df[TextConfig.get_text('return', self.language)].apply(lambda x: f"${x:.2f}")
        if 'Return %' in display_df.columns:
            display_df['Return %'] = display_df['Return %'].apply(lambda x: f"{x:.2f}%")
        
        # HTMLテーブルに変換
        html = display_df.to_html(classes='trades-table', escape=False, index=False)
        
        # 色分けを追加
        html = html.replace('<td>', '<td class="trade-cell">')
        
        # プラス/マイナスの値に色を適用
        import re
        html = re.sub(r'(\$-[\d,]+\.[\d]+)', r'<span class="negative">\1</span>', html)
        html = re.sub(r'(-[\d,]+\.[\d]+%)', r'<span class="negative">\1</span>', html)
        html = re.sub(r'(\$[\d,]+\.[\d]+)(?!</span>)', r'<span class="positive">\1</span>', html)
        html = re.sub(r'([\d,]+\.[\d]+%)(?!</span>)', r'<span class="positive">\1</span>', html)
        
        return html
    
    def generate_csv_report(self, trades: List[Dict[str, Any]], config: Dict[str, Any]) -> str:
        """CSVレポートを生成"""
        if not trades:
            print("トレードデータがないため、CSVレポートを生成できません。")
            return ""
        
        df = pd.DataFrame(trades)
        
        # レポートファイル名
        start_date = config.get('start_date', '').replace('-', '_')
        end_date = config.get('end_date', '').replace('-', '_')
        
        if not os.path.exists('reports'):
            os.makedirs('reports')
        
        filename = f"reports/earnings_backtest_{start_date}_{end_date}.csv"
        
        # CSVに保存
        df.to_csv(filename, index=False)
        
        print(f"CSVレポートを生成しました: {filename}")
        return filename