from dataclasses import dataclass
from typing import Optional, Set


@dataclass
class BacktestConfig:
    """バックテスト設定クラス"""
    start_date: str
    end_date: str
    stop_loss: float = 6
    trail_stop_ma: int = 21
    max_holding_days: int = 90
    initial_capital: float = 10000
    position_size: float = 6
    slippage: float = 0.3
    risk_limit: float = 6
    partial_profit: bool = True
    sp500_only: bool = False
    mid_small_only: bool = False
    language: str = 'en'
    pre_earnings_change: float = -10
    target_symbols: Optional[Set[str]] = None


class ThemeConfig:
    """ダークモードの色設定"""
    DARK_THEME = {
        'bg_color': '#1e293b',
        'plot_bg_color': '#1e293b',
        'grid_color': '#475569',  # グリッド線をさらに暗く調整
        'text_color': '#f1f5f9',  # より明るい白でテキストを見やすく
        'line_color': '#60a5fa',
        'profit_color': '#22c55e',
        'loss_color': '#ef4444',
        'table_border_color': '#475569'  # テーブル枠線用の色を追加
    }


class TextConfig:
    """多言語対応テキスト設定"""
    
    TEXTS = {
        'en': {
            'report_title': 'Earnings-Based Swing Trading Backtest Report',
            'total_trades': 'Total Trades',
            'winning_trades': 'Winning Trades',
            'losing_trades': 'Losing Trades',
            'win_rate': 'Win Rate',
            'avg_return': 'Average Return',
            'total_return': 'Total Return',
            'max_drawdown': 'Max Drawdown',
            'sharpe_ratio': 'Sharpe Ratio',
            'profit_factor': 'Profit Factor',
            'avg_holding_days': 'Avg Holding Days',
            'best_trade': 'Best Trade',
            'worst_trade': 'Worst Trade',
            'initial_capital': 'Initial Capital',
            'final_capital': 'Final Capital',
            'equity_curve': 'Equity Curve',
            'monthly_returns': 'Monthly Returns',
            'performance_summary': 'Performance Summary',
            'trade_details': 'Trade Details',
            'entry_date': 'Entry Date',
            'exit_date': 'Exit Date',
            'symbol': 'Symbol',
            'entry_price': 'Entry Price',
            'exit_price': 'Exit Price',
            'return': 'Return',
            'exit_reason': 'Exit Reason',
            'holdings_days': 'Holdings Days',
            'actual_eps': 'Actual EPS',
            'estimate_eps': 'Estimate EPS',
            'surprise_percent': 'Surprise %',
            'sector': 'Sector',
            'market_cap': 'Market Cap',
            'volume_20d_avg': 'Volume 20D Avg'
        },
        'ja': {
            'report_title': '決算ベース・スイングトレード・バックテストレポート',
            'total_trades': '総トレード数',
            'winning_trades': '勝利トレード数',
            'losing_trades': '敗北トレード数',
            'win_rate': '勝率',
            'avg_return': '平均リターン',
            'total_return': '総リターン',
            'max_drawdown': '最大ドローダウン',
            'sharpe_ratio': 'シャープレシオ',
            'profit_factor': 'プロフィットファクター',
            'avg_holding_days': '平均保有日数',
            'best_trade': '最高トレード',
            'worst_trade': '最悪トレード',
            'initial_capital': '初期資本',
            'final_capital': '最終資本',
            'equity_curve': '資産曲線',
            'monthly_returns': '月次リターン',
            'performance_summary': 'パフォーマンス要約',
            'trade_details': 'トレード詳細',
            'entry_date': 'エントリー日',
            'exit_date': 'エグジット日',
            'symbol': 'シンボル',
            'entry_price': 'エントリー価格',
            'exit_price': 'エグジット価格',
            'return': 'リターン',
            'exit_reason': 'エグジット理由',
            'holdings_days': '保有日数',
            'actual_eps': '実際EPS',
            'estimate_eps': '予想EPS',
            'surprise_percent': 'サプライズ%',
            'sector': 'セクター',
            'market_cap': '時価総額',
            'volume_20d_avg': '20日平均出来高'
        }
    }
    
    @classmethod
    def get_text(cls, key: str, language: str = 'en') -> str:
        """指定された言語のテキストを取得"""
        return cls.TEXTS.get(language, cls.TEXTS['en']).get(key, key)