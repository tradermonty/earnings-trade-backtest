"""
動的ポジションサイズ計算クラス
4つのパターンでポジションサイズを動的調整
"""

from typing import Dict, Any, Tuple
from datetime import datetime


class PositionCalculator:
    """4パターンの動的ポジションサイズ計算"""
    
    def __init__(self, config):
        """
        Args:
            config: BacktestConfig オブジェクト
        """
        self.config = config
        self.state = {}  # Pattern 4用の状態管理
        
        # デフォルト設定値
        self.stress_position_size = 8.0
        self.normal_position_size = 15.0
        self.bullish_position_size = 20.0
        self.extreme_stress_position = 6.0
        self.stress_position = 10.0
        self.normal_position = 15.0
        self.bullish_position = 20.0
        self.extreme_bullish_position = 25.0
        self.bearish_reduction_multiplier = 0.6
        self.bearish_stage_multiplier = 0.7
        self.bottom_8ma_multiplier = 1.3
        self.bottom_200ma_multiplier = 1.6
        self.min_position_size = 5.0
        self.max_position_size = 25.0
    
    def calculate_position_size(self, market_data: Dict[str, Any], date: datetime) -> Tuple[float, str]:
        """
        選択されたパターンでポジションサイズを計算
        
        Args:
            market_data: Market Breadthデータ
            date: 対象日
            
        Returns:
            (ポジションサイズ, 理由)
        """
        if not market_data:
            return self.config.position_size, "no_market_data"
        
        pattern = self.config.dynamic_position_pattern
        
        if pattern == "breadth_8ma":
            size, reason = self._pattern_1_breadth_8ma(market_data)
        elif pattern == "advanced_5stage":
            size, reason = self._pattern_2_advanced_5stage(market_data)
        elif pattern == "bearish_signal":
            size, reason = self._pattern_3_bearish_signal(market_data)
        elif pattern == "bottom_3stage":
            size, reason = self._pattern_4_bottom_3stage(market_data, date)
        else:
            size, reason = self.config.position_size, "default"
        
        # 制限適用
        size = max(self.min_position_size, min(size, self.max_position_size))
        
        return size, reason
    
    def _pattern_1_breadth_8ma(self, market_data: Dict[str, Any]) -> Tuple[float, str]:
        """
        Pattern 1: Market Breadth Index 8MA基準 (基本3段階)
        """
        breadth_8ma = market_data['breadth_8ma']
        
        if breadth_8ma < 0.4:
            size = self.stress_position_size
            reason = f"stress_8ma_{breadth_8ma:.3f}"
        elif breadth_8ma >= 0.7:
            size = self.bullish_position_size
            reason = f"bullish_8ma_{breadth_8ma:.3f}"
        else:
            size = self.normal_position_size
            reason = f"normal_8ma_{breadth_8ma:.3f}"
        
        return size, reason
    
    def _pattern_2_advanced_5stage(self, market_data: Dict[str, Any]) -> Tuple[float, str]:
        """
        Pattern 2: 細分化5段階調整
        """
        breadth_8ma = market_data['breadth_8ma']
        
        if breadth_8ma < 0.3:
            size = self.extreme_stress_position
            reason = f"extreme_stress_{breadth_8ma:.3f}"
        elif breadth_8ma < 0.4:
            size = self.stress_position
            reason = f"stress_{breadth_8ma:.3f}"
        elif breadth_8ma < 0.7:
            size = self.normal_position
            reason = f"normal_{breadth_8ma:.3f}"
        elif breadth_8ma < 0.8:
            size = self.bullish_position
            reason = f"bullish_{breadth_8ma:.3f}"
        else:
            size = self.extreme_bullish_position
            reason = f"extreme_bullish_{breadth_8ma:.3f}"
        
        return size, reason
    
    def _pattern_3_bearish_signal(self, market_data: Dict[str, Any]) -> Tuple[float, str]:
        """
        Pattern 3: Bearish Signal連動調整
        """
        breadth_8ma = market_data['breadth_8ma']
        bearish_signal = market_data['bearish_signal']
        
        # 基本サイズ
        base_size = self.normal_position_size
        
        if bearish_signal:
            size = base_size * self.bearish_reduction_multiplier
            reason = f"bearish_reduction_{breadth_8ma:.3f}"
        else:
            size = base_size
            reason = f"normal_{breadth_8ma:.3f}"
        
        return size, reason
    
    def _pattern_4_bottom_3stage(self, market_data: Dict[str, Any], date: datetime) -> Tuple[float, str]:
        """
        Pattern 4: ボトム検出3段階戦略
        Stage 1: Bearish Signal → サイズ縮小
        Stage 2: 8MA底検出 → サイズ1段階拡大  
        Stage 3: 200MA底検出 → サイズ更に拡大
        """
        breadth_8ma = market_data['breadth_8ma']
        bearish_signal = market_data['bearish_signal']
        is_trough = market_data['is_trough']
        is_trough_8ma_below_04 = market_data['is_trough_8ma_below_04']
        
        # 基本サイズの設定
        base_size = self.normal_position_size
        
        # 日付をキーとして状態管理
        date_key = date.strftime('%Y-%m-%d')
        
        # Stage 1: Bearish Signal 検出
        if bearish_signal:
            current_size = base_size * self.bearish_stage_multiplier
            stage = "stage1_bearish"
            
        # Stage 2: 8MA底検出 (Is_Trough_8MA_Below_04)
        elif is_trough_8ma_below_04:
            current_size = base_size * self.bottom_8ma_multiplier
            stage = "stage2_8ma_bottom"
            self.state['8ma_bottom_detected'] = True
            self.state['8ma_bottom_date'] = date_key
            
        # Stage 3: 通常のトラフ検出（200MA関連）+ 8MA底検出履歴あり
        elif is_trough and self._check_8ma_bottom_history(date_key):
            current_size = base_size * self.bottom_200ma_multiplier
            stage = "stage3_200ma_bottom"
            
        # Stage 2の効果継続（8MA底検出後の数日間）
        elif self._check_8ma_bottom_history(date_key) and breadth_8ma < 0.5:
            current_size = base_size * 1.2  # 継続効果
            stage = "stage2_continuation"
            
        else:
            current_size = base_size
            stage = "normal"
            # 8MA底効果のリセット（市場が回復したら）
            if breadth_8ma > 0.6:
                self.state.pop('8ma_bottom_detected', None)
                self.state.pop('8ma_bottom_date', None)
        
        reason = f"{stage}_{breadth_8ma:.3f}"
        return current_size, reason
    
    def _check_8ma_bottom_history(self, current_date_key: str) -> bool:
        """8MA底検出の履歴をチェック（過去30日以内）"""
        if not self.state.get('8ma_bottom_detected', False):
            return False
        
        bottom_date_str = self.state.get('8ma_bottom_date')
        if not bottom_date_str:
            return False
        
        try:
            bottom_date = datetime.strptime(bottom_date_str, '%Y-%m-%d')
            current_date = datetime.strptime(current_date_key, '%Y-%m-%d')
            days_diff = (current_date - bottom_date).days
            
            # 30日以内なら有効
            return 0 <= days_diff <= 30
        except:
            return False