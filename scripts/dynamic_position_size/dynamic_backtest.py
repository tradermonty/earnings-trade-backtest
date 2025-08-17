"""
動的ポジションサイズ調整メインクラス
既存のEarningsBacktestをラップして機能拡張
"""

import sys
import os
import logging
import importlib.util
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd

# 既存のsrcモジュールをインポート - 別プロセスで実行する方式に変更
# import問題を回避するため、subprocessで既存システムを呼び出す
import subprocess

from .config import DynamicPositionSizeConfig
from .breadth_manager import MarketBreadthManager
from .position_calculator import PositionCalculator


class DynamicPositionSizeBacktest:
    """動的ポジションサイズ調整でバックテストを実行するメインクラス"""
    
    def __init__(self, config: DynamicPositionSizeConfig):
        """
        Args:
            config: 動的ポジションサイズ設定
        """
        self.config = config
        self.breadth_manager = None
        self.position_calculator = None
        self.backtest = None
        
        # ログ設定
        if config.enable_logging:
            self._setup_logging()
        
        # 初期化
        self._initialize_components()
        
        # 結果格納用
        self.results = {}
        self.position_history = []
    
    def _setup_logging(self):
        """ログ設定"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            force=True
        )
        
        # 既存ログレベルを調整（冗長なログを抑制）
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    def _initialize_components(self):
        """各コンポーネントの初期化"""
        try:
            # Market Breadth Manager初期化
            if not self.config.validate_csv_file():
                raise FileNotFoundError(f"Market Breadth CSV not found: {self.config.breadth_csv_path}")
            
            self.breadth_manager = MarketBreadthManager(self.config.breadth_csv_path)
            
            # データカバレッジ検証
            coverage = self.breadth_manager.validate_backtest_coverage(
                self.config.start_date, self.config.end_date
            )
            
            if not coverage['covered']:
                raise ValueError(f"Market Breadth data does not cover backtest period: {coverage}")
            
            # Position Calculator初期化
            self.position_calculator = PositionCalculator(self.config)
            
            logging.info(f"Dynamic Position Size System initialized:")
            logging.info(f"  Pattern: {self.config.position_pattern}")
            logging.info(f"  Description: {self.config.get_pattern_description()}")
            logging.info(f"  Data Period: {coverage['available_period']}")
            logging.info(f"  Backtest Period: {coverage['requested_period']}")
            
        except Exception as e:
            logging.error(f"Failed to initialize Dynamic Position Size System: {e}")
            raise
    
    def run_backtest(self) -> Dict[str, Any]:
        """
        動的ポジションサイズでバックテストを実行
        
        Returns:
            バックテスト結果の辞書
        """
        logging.info("="*60)
        logging.info("Starting Dynamic Position Size Backtest")
        logging.info("="*60)
        
        try:
            # 既存のバックテストシステムを利用
            # ただし、ポジションサイズは動的に調整
            original_position_size = self.config.position_size
            
            # 基本設定で既存バックテストを初期化
            base_config = self._create_base_config()
            self.backtest = EarningsBacktest(base_config)
            
            # 動的調整を適用してバックテスト実行
            results = self._run_dynamic_backtest()
            
            # 結果の後処理
            results = self._post_process_results(results)
            
            # ポジションサイズを元に戻す
            self.config.position_size = original_position_size
            
            logging.info("Dynamic Position Size Backtest completed successfully")
            return results
            
        except Exception as e:
            logging.error(f"Dynamic Position Size Backtest failed: {e}")
            raise
    
    def _create_base_config(self) -> BacktestConfig:
        """既存システム用の基本設定を作成"""
        # DynamicPositionSizeConfigから基本設定を抽出
        base_config = BacktestConfig(
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            stop_loss=self.config.stop_loss,
            trail_stop_ma=self.config.trail_stop_ma,
            max_holding_days=self.config.max_holding_days,
            initial_capital=self.config.initial_capital,
            position_size=self.config.default_position_size,  # 後で動的に変更
            slippage=self.config.slippage,
            risk_limit=self.config.risk_limit,
            partial_profit=self.config.partial_profit,
            sp500_only=self.config.sp500_only,
            mid_small_only=self.config.mid_small_only,
            language=self.config.language,
            pre_earnings_change=self.config.pre_earnings_change,
            margin_ratio=self.config.margin_ratio,
            target_symbols=self.config.target_symbols,
            enable_earnings_date_validation=self.config.enable_earnings_date_validation,
            use_fmp_data=self.config.use_fmp_data,
            max_gap_percent=self.config.max_gap_percent,
            max_ps_ratio=self.config.max_ps_ratio,
            max_pe_ratio=self.config.max_pe_ratio,
            min_profit_margin=self.config.min_profit_margin,
            screener_price_min=self.config.screener_price_min,
            screener_volume_min=self.config.screener_volume_min,
            min_market_cap=self.config.min_market_cap,
            max_market_cap=self.config.max_market_cap
        )
        
        return base_config
    
    def _run_dynamic_backtest(self) -> Dict[str, Any]:
        """
        動的ポジションサイズ調整を適用したバックテスト実行
        
        注意: 既存システムの制約上、この実装では各トレードでのポジションサイズ調整は
              シミュレーション的に後処理で適用します。
        """
        # 1. 既存システムでバックテストを実行（標準ポジションサイズ）
        logging.info("Executing base backtest with standard position sizing...")
        
        # 既存システムの実行
        self.backtest.run_backtest()
        base_results = {
            'trades': self.backtest.trades,
            'metrics': self.backtest.metrics
        }
        
        # 2. 各トレードに動的ポジションサイズを適用
        logging.info("Applying dynamic position sizing to trades...")
        adjusted_trades = self._apply_dynamic_position_sizing(base_results['trades'])
        
        # 3. 調整後のメトリクスを再計算
        adjusted_metrics = self._recalculate_metrics(adjusted_trades)
        
        return {
            'trades': adjusted_trades,
            'metrics': adjusted_metrics,
            'base_trades': base_results['trades'],
            'base_metrics': base_results['metrics'],
            'position_history': self.position_history
        }
    
    def _apply_dynamic_position_sizing(self, base_trades: List[Dict]) -> List[Dict]:
        """各トレードに動的ポジションサイズを適用"""
        adjusted_trades = []
        
        # Position Calculatorの状態をリセット
        self.position_calculator.reset_state()
        
        logging.info(f"Applying dynamic position sizing to {len(base_trades)} trades...")
        
        for i, trade in enumerate(base_trades):
            entry_date = pd.to_datetime(trade['entry_date'])
            
            # その日の市場データを取得
            market_data = self.breadth_manager.get_market_data(entry_date)
            
            # 動的ポジションサイズを計算
            new_position_size, reason = self.position_calculator.calculate_position_size(
                market_data, entry_date
            )
            
            # 元のポジションサイズ（15%想定）から調整
            original_position_size = self.config.default_position_size
            position_multiplier = new_position_size / original_position_size
            
            # トレード結果を調整
            adjusted_trade = trade.copy()
            
            # shares, pnl, pnl_rateを調整
            adjusted_trade['shares'] = trade['shares'] * position_multiplier
            adjusted_trade['pnl'] = trade['pnl'] * position_multiplier
            # pnl_rateは変更なし（％リターンは同じ）
            
            # 動的調整情報を追加
            adjusted_trade['original_position_size'] = original_position_size
            adjusted_trade['dynamic_position_size'] = new_position_size
            adjusted_trade['position_multiplier'] = position_multiplier
            adjusted_trade['position_reason'] = reason
            
            if market_data:
                adjusted_trade['breadth_8ma'] = market_data['breadth_8ma']
                adjusted_trade['bearish_signal'] = market_data['bearish_signal']
                adjusted_trade['market_condition'] = self.breadth_manager.get_market_condition(
                    market_data['breadth_8ma']
                )
            else:
                adjusted_trade['breadth_8ma'] = None
                adjusted_trade['bearish_signal'] = None
                adjusted_trade['market_condition'] = 'unknown'
            
            adjusted_trades.append(adjusted_trade)
            
            # ポジション履歴を記録
            self.position_history.append({
                'date': entry_date,
                'ticker': trade['ticker'],
                'original_size': original_position_size,
                'dynamic_size': new_position_size,
                'multiplier': position_multiplier,
                'reason': reason,
                'breadth_8ma': market_data['breadth_8ma'] if market_data else None,
                'market_condition': adjusted_trade['market_condition']
            })
            
            # 進捗ログ
            if (i + 1) % 50 == 0 or i == len(base_trades) - 1:
                logging.info(f"  Processed {i + 1}/{len(base_trades)} trades")
        
        return adjusted_trades
    
    def _recalculate_metrics(self, adjusted_trades: List[Dict]) -> Dict[str, Any]:
        """調整後のトレードでメトリクスを再計算"""
        if not adjusted_trades:
            return {}
        
        trades_df = pd.DataFrame(adjusted_trades)
        
        # 基本メトリクス
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['pnl'] > 0])
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        total_pnl = trades_df['pnl'].sum()
        avg_return = trades_df['pnl_rate'].mean() * 100
        
        # 初期資本を考慮した総リターン
        total_return = (total_pnl / self.config.initial_capital) * 100
        
        # その他のメトリクス
        if winning_trades > 0:
            avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean()
            best_trade = trades_df['pnl'].max()
        else:
            avg_win = 0
            best_trade = 0
        
        if losing_trades > 0:
            avg_loss = trades_df[trades_df['pnl'] <= 0]['pnl'].mean()
            worst_trade = trades_df['pnl'].min()
        else:
            avg_loss = 0
            worst_trade = 0
        
        # 動的調整特有のメトリクス
        position_stats = self._calculate_position_statistics(trades_df)
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'total_return': total_return,
            'avg_return': avg_return,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_holding_days': trades_df['holding_period'].mean(),
            **position_stats
        }
    
    def _calculate_position_statistics(self, trades_df: pd.DataFrame) -> Dict[str, Any]:
        """動的ポジションサイズの統計を計算"""
        position_sizes = trades_df['dynamic_position_size']
        multipliers = trades_df['position_multiplier']
        
        # ポジションサイズ分布
        size_distribution = {}
        for condition in ['extreme_stress', 'stress', 'normal', 'bullish', 'extreme_bullish']:
            count = len(trades_df[trades_df['market_condition'] == condition])
            size_distribution[condition] = count
        
        # パターン別統計
        pattern_stats = trades_df.groupby('position_reason').agg({
            'dynamic_position_size': ['count', 'mean'],
            'pnl': ['sum', 'mean'],
            'pnl_rate': 'mean'
        }).round(2)
        
        return {
            'position_size_stats': {
                'min': float(position_sizes.min()),
                'max': float(position_sizes.max()),
                'mean': float(position_sizes.mean()),
                'std': float(position_sizes.std())
            },
            'position_multiplier_stats': {
                'min': float(multipliers.min()),
                'max': float(multipliers.max()),
                'mean': float(multipliers.mean()),
                'std': float(multipliers.std())
            },
            'market_condition_distribution': size_distribution,
            'trades_above_default': int((position_sizes > self.config.default_position_size).sum()),
            'trades_below_default': int((position_sizes < self.config.default_position_size).sum()),
            'pattern_statistics': pattern_stats.to_dict() if not pattern_stats.empty else {}
        }
    
    def _post_process_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """結果の後処理とレポート情報の追加"""
        
        # 設定情報を追加
        results['config_info'] = self.config.to_dict()
        
        # Market Breadth統計を追加
        results['market_breadth_stats'] = self.breadth_manager.get_statistics()
        
        # Position Calculator状態を追加
        results['position_calculator_state'] = self.position_calculator.get_state_summary()
        
        # 比較メトリクス（ベース vs 動的調整）
        if 'base_metrics' in results and 'metrics' in results:
            base_return = results['base_metrics'].get('total_return', 0)
            dynamic_return = results['metrics'].get('total_return', 0)
            improvement = dynamic_return - base_return
            improvement_pct = (improvement / abs(base_return)) * 100 if base_return != 0 else 0
            
            results['comparison'] = {
                'base_total_return': base_return,
                'dynamic_total_return': dynamic_return,
                'improvement_absolute': improvement,
                'improvement_percentage': improvement_pct,
                'base_trades': results['base_metrics'].get('total_trades', 0),
                'dynamic_trades': results['metrics'].get('total_trades', 0)
            }
        
        # 実行情報
        results['execution_info'] = {
            'pattern_used': self.config.position_pattern,
            'csv_file': self.config.breadth_csv_path,
            'execution_time': datetime.now().isoformat(),
            'total_position_adjustments': len(self.position_history)
        }
        
        return results
    
    def generate_report(self, results: Dict[str, Any], output_path: str = None) -> str:
        """結果レポートを生成"""
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"dynamic_position_backtest_report_{self.config.position_pattern}_{timestamp}.html"
        
        # 簡単なHTMLレポートを生成
        # (実際の実装では既存のレポート生成システムを拡張)
        html_content = self._generate_html_report(results)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logging.info(f"Dynamic Position Size Report generated: {output_path}")
        return output_path
    
    def _generate_html_report(self, results: Dict[str, Any]) -> str:
        """HTMLレポートの生成"""
        # 簡易版レポート
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dynamic Position Size Backtest Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .metric {{ margin: 10px 0; }}
                .comparison {{ background-color: #f0f8ff; padding: 10px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>Dynamic Position Size Backtest Report</h1>
            <h2>Configuration</h2>
            <div class="metric">Pattern: {self.config.position_pattern}</div>
            <div class="metric">Description: {self.config.get_pattern_description()}</div>
            <div class="metric">Period: {self.config.start_date} to {self.config.end_date}</div>
            
            <h2>Results</h2>
            <div class="metric">Total Trades: {results['metrics'].get('total_trades', 0)}</div>
            <div class="metric">Win Rate: {results['metrics'].get('win_rate', 0)*100:.1f}%</div>
            <div class="metric">Total Return: {results['metrics'].get('total_return', 0):.2f}%</div>
            
            <h2>Position Size Statistics</h2>
            <div class="metric">Average Position Size: {results['metrics']['position_size_stats']['mean']:.1f}%</div>
            <div class="metric">Position Size Range: {results['metrics']['position_size_stats']['min']:.1f}% - {results['metrics']['position_size_stats']['max']:.1f}%</div>
            
            <div class="comparison">
                <h2>Improvement vs Base Strategy</h2>
                <div class="metric">Base Return: {results['comparison']['base_total_return']:.2f}%</div>
                <div class="metric">Dynamic Return: {results['comparison']['dynamic_total_return']:.2f}%</div>
                <div class="metric">Improvement: {results['comparison']['improvement_absolute']:.2f}% ({results['comparison']['improvement_percentage']:+.1f}%)</div>
            </div>
        </body>
        </html>
        """
        return html