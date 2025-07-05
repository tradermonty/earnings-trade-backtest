from datetime import datetime, timedelta
from typing import List, Dict, Any


class RiskManager:
    """リスク管理クラス"""
    
    def __init__(self, risk_limit: float = 6):
        """RiskManagerの初期化"""
        self.risk_limit = risk_limit
    
    def check_risk_management(self, current_date: str, current_capital: float, 
                             trades: List[Dict[str, Any]]) -> bool:
        """
        過去1ヶ月間の損益が総資産の-risk_limit%を下回っているかチェック
        
        Args:
            current_date: 現在の日付
            current_capital: 現在の資本
            trades: トレード履歴
            
        Returns:
            bool: 新規トレードが可能かどうか
        """
        if not trades:
            return True  # トレード履歴がない場合は制限なし
        
        # 現在の日付から1ヶ月前の日付を計算
        one_month_ago = (datetime.strptime(current_date, "%Y-%m-%d") - 
                        timedelta(days=30)).strftime("%Y-%m-%d")
        
        # 過去1ヶ月間の確定したトレードを抽出
        recent_trades = [
            trade for trade in trades
            if trade['exit_date'] >= one_month_ago and trade['exit_date'] <= current_date
        ]
        
        if not recent_trades:
            return True  # 過去1ヶ月間に確定したトレードがない場合は制限なし
        
        # 過去1ヶ月間の損益合計を計算
        total_pnl = sum(trade['pnl'] for trade in recent_trades)
        
        # 損益率を計算（現在の総資産に対する割合）
        pnl_ratio = (total_pnl / current_capital) * 100

        print(f"\nリスク管理チェック ({current_date}):")
        print(f"- 過去1ヶ月間の損益: ${total_pnl:,.2f}")
        print(f"- 現在の総資産: ${current_capital:,.2f}")
        print(f"- 損益率: {pnl_ratio:.2f}%")
        
        # -risk_limit%を下回っている場合はFalseを返す
        if pnl_ratio < -self.risk_limit:
            print(f"※ 損益率が-{self.risk_limit}%を下回っているため、新規トレードを制限します")
            return False
        
        return True
    
    def calculate_position_size(self, capital: float, position_size_percent: float, 
                               entry_price: float, slippage: float = 0.3) -> Dict[str, float]:
        """
        ポジションサイズを計算
        
        Args:
            capital: 現在の資本
            position_size_percent: ポジションサイズの割合（%）
            entry_price: エントリー価格
            slippage: スリッページ（%）
            
        Returns:
            Dict: shares（株数）とposition_value（ポジション価値）を含む辞書
        """
        # スリッページを考慮したエントリー価格
        adjusted_entry_price = entry_price * (1 + slippage / 100)
        
        # ポジション価値を計算
        position_value = capital * (position_size_percent / 100)
        
        # 株数を計算（端数切り捨て）
        shares = int(position_value / adjusted_entry_price)
        
        # 実際のポジション価値を再計算
        actual_position_value = shares * adjusted_entry_price
        
        return {
            'shares': shares,
            'position_value': actual_position_value,
            'adjusted_entry_price': adjusted_entry_price
        }
    
    def check_stop_loss(self, current_price: float, entry_price: float, 
                       stop_loss_percent: float) -> bool:
        """
        ストップロス条件をチェック
        
        Args:
            current_price: 現在価格
            entry_price: エントリー価格
            stop_loss_percent: ストップロス割合（%）
            
        Returns:
            bool: ストップロスに達したかどうか
        """
        if entry_price == 0:
            return False  # ゼロ除算を回避
        
        loss_percent = ((current_price - entry_price) / entry_price) * 100
        return loss_percent <= -stop_loss_percent
    
    def check_trailing_stop(self, current_price: float, moving_average: float) -> bool:
        """
        トレーリングストップ条件をチェック
        
        Args:
            current_price: 現在価格
            moving_average: 移動平均価格
            
        Returns:
            bool: トレーリングストップに達したかどうか
        """
        return current_price < moving_average
    
    def calculate_partial_profit_target(self, entry_price: float, 
                                      target_percent: float = 8) -> float:
        """
        部分利確のターゲット価格を計算
        
        Args:
            entry_price: エントリー価格
            target_percent: ターゲット利益率（%）
            
        Returns:
            float: ターゲット価格
        """
        return entry_price * (1 + target_percent / 100)
    
    def should_partial_profit(self, current_price: float, entry_price: float,
                             target_percent: float = 8) -> bool:
        """
        部分利確すべきかどうかをチェック
        
        Args:
            current_price: 現在価格
            entry_price: エントリー価格
            target_percent: ターゲット利益率（%）
            
        Returns:
            bool: 部分利確すべきかどうか
        """
        target_price = self.calculate_partial_profit_target(entry_price, target_percent)
        return current_price >= target_price