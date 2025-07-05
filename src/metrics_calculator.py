import pandas as pd
from typing import List, Dict, Any, Optional


class MetricsCalculator:
    """パフォーマンス指標計算クラス"""
    
    def __init__(self, initial_capital: float = 10000):
        """MetricsCalculatorの初期化"""
        self.initial_capital = initial_capital
    
    def calculate_metrics(self, trades: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """パフォーマンス指標の計算"""
        if not trades:
            return self._get_empty_metrics()
        
        # トレードをDataFrameに変換
        df = pd.DataFrame(trades)
        
        # 基本指標の計算
        basic_metrics = self._calculate_basic_metrics(df)
        
        # 資産推移の計算
        equity_metrics = self._calculate_equity_metrics(df)
        
        # 年間パフォーマンスの計算
        yearly_metrics = self._calculate_yearly_performance(df)
        
        # 高度な指標の計算
        advanced_metrics = self._calculate_advanced_metrics(df, equity_metrics)
        
        # 全ての指標をまとめる
        metrics = {
            **basic_metrics,
            **equity_metrics,
            **yearly_metrics,
            **advanced_metrics
        }
        
        # 結果を表示
        self._print_results(metrics)
        
        return metrics
    
    def _get_empty_metrics(self) -> Dict[str, Any]:
        """トレードがない場合の空のメトリクス"""
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'avg_return': 0,
            'total_return': 0,
            'max_drawdown': 0,
            'sharpe_ratio': 0,
            'profit_factor': 0,
            'avg_holding_days': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'initial_capital': self.initial_capital,
            'final_capital': self.initial_capital
        }
    
    def _calculate_basic_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """基本的な指標を計算"""
        total_trades = len(df)
        winning_trades = len(df[df['pnl_rate'] > 0])
        losing_trades = len(df[df['pnl_rate'] <= 0])
        
        # 勝率
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 平均損益率
        avg_win_loss_rate = df['pnl_rate'].mean()
        
        # 平均保有期間
        avg_holding_period = df['holding_period'].mean()
        
        # プロフィットファクター
        total_profit = df[df['pnl'] > 0]['pnl'].sum()
        total_loss = abs(df[df['pnl'] <= 0]['pnl'].sum())
        profit_factor = total_profit / total_loss if total_loss != 0 else float('inf')
        
        # 最高・最悪トレード
        best_trade = df['pnl_rate'].max()
        worst_trade = df['pnl_rate'].min()
        
        # 終了理由の集計
        exit_reasons = df['exit_reason'].value_counts()
        
        return {
            'number_of_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': round(win_rate, 2),
            'avg_win_loss_rate': round(avg_win_loss_rate, 2),
            'avg_holding_period': round(avg_holding_period, 2),
            'profit_factor': round(profit_factor, 2),
            'best_trade': round(best_trade, 2),
            'worst_trade': round(worst_trade, 2),
            'exit_reasons': exit_reasons.to_dict()
        }
    
    def _calculate_equity_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """資産推移に関する指標を計算"""
        # 資産推移の計算
        df['equity'] = self.initial_capital + df['pnl'].cumsum()
        
        # 最大ドローダウンの計算（資産額ベース）
        df['running_max'] = df['equity'].cummax()
        df['drawdown'] = (df['running_max'] - df['equity']) / df['running_max'] * 100
        max_drawdown_pct = df['drawdown'].max()
        
        # 最終資本
        final_capital = self.initial_capital + df['pnl'].sum()
        
        # 総リターン率
        total_return_pct = (final_capital - self.initial_capital) / self.initial_capital * 100
        
        return {
            'max_drawdown_pct': round(max_drawdown_pct, 2),
            'initial_capital': self.initial_capital,
            'final_capital': round(final_capital, 2),
            'total_return_pct': round(total_return_pct, 2),
            'equity_curve': df[['equity']].copy()
        }
    
    def _calculate_yearly_performance(self, df: pd.DataFrame) -> Dict[str, Any]:
        """年間パフォーマンスを計算"""
        # 年間パフォーマンスの計算
        df['year'] = pd.to_datetime(df['entry_date']).dt.strftime('%Y')
        
        # 年ごとの損益を計算
        yearly_pnl = df.groupby('year')['pnl'].sum().reset_index()
        
        # 各年の開始時点の資産を計算
        yearly_returns = []
        current_capital = self.initial_capital
        
        for year in yearly_pnl['year'].values:
            year_pnl = yearly_pnl[yearly_pnl['year'] == year]['pnl'].values[0]
            return_pct = (year_pnl / current_capital) * 100
            
            yearly_returns.append({
                'year': year,
                'pnl': year_pnl,
                'return_pct': return_pct,
                'start_capital': current_capital,
                'end_capital': current_capital + year_pnl
            })
            
            # 次年の開始資産を更新
            current_capital += year_pnl
        
        # CAGRの計算
        start_date = pd.to_datetime(df['entry_date'].min())
        end_date = pd.to_datetime(df['exit_date'].max())
        years = (end_date - start_date).days / 365.25
        final_capital = self.initial_capital + df['pnl'].sum()
        
        if years > 0:
            cagr = ((final_capital / self.initial_capital) ** (1/years) - 1) * 100
        else:
            cagr = 0
        
        return {
            'yearly_returns': yearly_returns,
            'cagr': round(cagr, 2)
        }
    
    def _calculate_advanced_metrics(self, df: pd.DataFrame, equity_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """高度な指標を計算"""
        total_trades = len(df)
        winning_trades = len(df[df['pnl_rate'] > 0])
        
        # Expected Value (期待値)の計算
        avg_win = df[df['pnl_rate'] > 0]['pnl_rate'].mean() if winning_trades > 0 else 0
        avg_loss = df[df['pnl_rate'] < 0]['pnl_rate'].mean() if total_trades > winning_trades else 0
        win_rate_decimal = winning_trades / total_trades if total_trades > 0 else 0
        expected_value_pct = (win_rate_decimal * avg_win) + ((1 - win_rate_decimal) * avg_loss)
        
        # Calmar Ratioの計算
        max_drawdown_pct = equity_metrics['max_drawdown_pct']
        cagr = equity_metrics.get('cagr', 0)
        calmar_ratio = abs(cagr / max_drawdown_pct) if max_drawdown_pct != 0 else float('inf')
        
        # Pareto Ratio (80/20の法則に基づく指標)の計算
        sorted_profits = df[df['pnl'] > 0]['pnl'].sort_values(ascending=False)
        if not sorted_profits.empty:
            top_20_percent = sorted_profits.head(int(len(sorted_profits) * 0.2))
            pareto_ratio = (top_20_percent.sum() / sorted_profits.sum() * 100)
        else:
            pareto_ratio = 0
        
        # Sharpe Ratioの簡易計算（日次リターンベース）
        if len(df) > 1:
            daily_returns = df['pnl_rate']
            sharpe_ratio = daily_returns.mean() / daily_returns.std() if daily_returns.std() != 0 else 0
        else:
            sharpe_ratio = 0
        
        return {
            'expected_value_pct': round(expected_value_pct, 2),
            'calmar_ratio': round(calmar_ratio, 2),
            'pareto_ratio': round(pareto_ratio, 1),
            'sharpe_ratio': round(sharpe_ratio, 2)
        }
    
    def _print_results(self, metrics: Dict[str, Any]) -> None:
        """結果を表示"""
        print("\nバックテスト結果:")
        print(f"Number of trades: {metrics['number_of_trades']}")
        print(f"Ave win/loss rate: {metrics['avg_win_loss_rate']:.2f}%")
        print(f"Ave holding period: {metrics['avg_holding_period']} days")
        print(f"Win rate: {metrics['win_rate']:.1f}%")
        print(f"Profit factor: {metrics['profit_factor']}")
        print(f"Max drawdown: {metrics['max_drawdown_pct']:.2f}%")
        print(f"\n終了理由の内訳:")
        for reason, count in metrics['exit_reasons'].items():
            print(f"- {reason}: {count}")
        print(f"\n資産推移:")
        print(f"Initial capital: ${metrics['initial_capital']:,.2f}")
        print(f"Final capital: ${metrics['final_capital']:,.2f}")
        print(f"Total return: {metrics['total_return_pct']:.2f}%")
        print(f"Expected Value: {metrics['expected_value_pct']:.2f}%")
        print(f"Calmar Ratio: {metrics['calmar_ratio']:.2f}")
        print(f"Pareto Ratio: {metrics['pareto_ratio']:.1f}%")
    
    def calculate_daily_positions(self, trades: List[Dict[str, Any]]) -> pd.DataFrame:
        """日次ポジション価値を計算"""
        if not trades:
            return pd.DataFrame()
        
        df = pd.DataFrame(trades)
        
        # 日付範囲を作成
        start_date = pd.to_datetime(df['entry_date'].min())
        end_date = pd.to_datetime(df['exit_date'].max())
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        
        # 各日のポジション価値を計算
        daily_positions = []
        
        for date in date_range:
            date_str = date.strftime('%Y-%m-%d')
            
            # その日にアクティブなポジションを計算
            active_trades = df[
                (pd.to_datetime(df['entry_date']) <= date) & 
                (pd.to_datetime(df['exit_date']) >= date)
            ]
            
            if not active_trades.empty:
                total_value = (active_trades['shares'] * active_trades['entry_price']).sum()
            else:
                total_value = 0
            
            daily_positions.append({
                'date': date_str,
                'total_value': total_value,
                'num_positions': len(active_trades)
            })
        
        return pd.DataFrame(daily_positions)