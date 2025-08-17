"""
動的ポジションサイズ計算クラス
4つのパターンに対応
"""

import logging
from datetime import datetime
from typing import Dict, Any, Tuple


class PositionCalculator:
    """4つのパターンでポジションサイズを動的計算するクラス"""
    
    def __init__(self, config):
        """
        Args:
            config: DynamicPositionSizeConfig instance
        """
        self.config = config
        self.state = {}  # Pattern 4用の状態管理
        
    def calculate_position_size(self, market_data: Dict[str, Any], 
                              date: datetime) -> Tuple[float, str]:
        """
        選択されたパターンでポジションサイズを計算
        
        Args:
            market_data: MarketBreadthManagerから取得した市場データ
            date: エントリー日付
            
        Returns:
            Tuple[float, str]: (ポジションサイズ, 計算根拠)
        """
        
        if market_data is None:
            # データが見つからない場合はデフォルト値
            size = self.config.default_position_size
            reason = "no_market_data"
            
        elif self.config.position_pattern == "breadth_8ma":
            size, reason = self._pattern_1_breadth_8ma(market_data)
            
        elif self.config.position_pattern == "advanced_5stage":
            size, reason = self._pattern_2_advanced_5stage(market_data)
            
        elif self.config.position_pattern == "bearish_signal":
            size, reason = self._pattern_3_bearish_signal(market_data)
            
        elif self.config.position_pattern == "bottom_3stage":
            size, reason = self._pattern_4_bottom_3stage(market_data, date)
            
        else:
            size = self.config.default_position_size
            reason = "unknown_pattern"
        
        # 制限適用
        size = min(max(size, self.config.min_position_size), 
                  self.config.max_position_size)
        
        # ログ出力
        if self.config.enable_logging:
            self._log_calculation(date, market_data, size, reason)
        
        return size, reason
    
    def _pattern_1_breadth_8ma(self, market_data: Dict[str, Any]) -> Tuple[float, str]:
        """
        Pattern 1: Market Breadth 8MA基準のシンプル3段階
        """
        breadth_8ma = market_data['breadth_8ma']
        
        if breadth_8ma < 0.4:
            size = self.config.stress_position_size
            reason = f"stress_8ma_{breadth_8ma:.3f}"
        elif breadth_8ma >= 0.7:
            size = self.config.bullish_position_size
            reason = f"bullish_8ma_{breadth_8ma:.3f}"
        else:
            size = self.config.normal_position_size
            reason = f"normal_8ma_{breadth_8ma:.3f}"
        
        return size, reason
    
    def _pattern_2_advanced_5stage(self, market_data: Dict[str, Any]) -> Tuple[float, str]:
        """
        Pattern 2: 細分化5段階
        """
        breadth_8ma = market_data['breadth_8ma']
        
        if breadth_8ma < 0.3:
            size = self.config.extreme_stress_position
            reason = f"extreme_stress_{breadth_8ma:.3f}"
        elif breadth_8ma < 0.4:
            size = self.config.stress_position
            reason = f"stress_{breadth_8ma:.3f}"
        elif breadth_8ma < 0.7:
            size = self.config.normal_position
            reason = f"normal_{breadth_8ma:.3f}"
        elif breadth_8ma < 0.8:
            size = self.config.bullish_position
            reason = f"bullish_{breadth_8ma:.3f}"
        else:
            size = self.config.extreme_bullish_position
            reason = f"extreme_bullish_{breadth_8ma:.3f}"
        
        return size, reason
    
    def _pattern_3_bearish_signal(self, market_data: Dict[str, Any]) -> Tuple[float, str]:
        """
        Pattern 3: Bearish Signal連動
        """
        # 基本サイズをPattern 1で計算
        base_size, base_reason = self._pattern_1_breadth_8ma(market_data)
        
        bearish_signal = market_data['bearish_signal']
        
        if bearish_signal:
            size = base_size * self.config.bearish_reduction_multiplier
            reason = f"bearish_reduction_{base_reason}"
        else:
            size = base_size
            reason = base_reason
        
        return size, reason
    
    def _pattern_4_bottom_3stage(self, market_data: Dict[str, Any], 
                               date: datetime) -> Tuple[float, str]:
        """
        Pattern 4: ボトム検出3段階戦略（最高度）
        
        Stage 1: Bearish Signal → サイズ縮小
        Stage 2: 8MA底検出 → サイズ1段階拡大  
        Stage 3: 200MA底検出 → サイズ更に拡大
        """
        
        breadth_8ma = market_data['breadth_8ma']
        bearish_signal = market_data['bearish_signal']
        is_trough = market_data['is_trough']
        is_trough_8ma_below_04 = market_data['is_trough_8ma_below_04']
        
        # 基本サイズの設定（Pattern 1ベース）
        if breadth_8ma < 0.4:
            base_size = self.config.stress_position_size
        elif breadth_8ma >= 0.7:
            base_size = self.config.bullish_position_size
        else:
            base_size = self.config.normal_position_size
        
        # 日付キーで状態管理
        date_key = date.strftime('%Y-%m-%d')
        
        # Stage 1: Bearish Signal 検出
        if bearish_signal:
            current_size = base_size * self.config.bearish_stage_multiplier
            stage = "stage1_bearish_reduction"
            self.state[date_key] = {'bearish_detected': True}
            
        # Stage 2: 8MA底検出 (Is_Trough_8MA_Below_04)
        elif is_trough_8ma_below_04:
            current_size = base_size * self.config.bottom_8ma_multiplier
            stage = "stage2_8ma_bottom_boost"
            # 8MA底検出の状態を記録
            self.state[date_key] = {
                '8ma_bottom_detected': True,
                '8ma_bottom_date': date_key
            }
            
        # Stage 3: 通常のトラフ検出（200MA関連）+ 8MA底後の条件
        elif is_trough and self._check_8ma_bottom_history(date_key):
            current_size = base_size * self.config.bottom_200ma_multiplier
            stage = "stage3_200ma_bottom_boost"
            
        # Stage 2の効果継続（8MA底検出後の数日間）
        elif (self._check_8ma_bottom_history(date_key) and 
              breadth_8ma < self.config.bottom_continuation_threshold):
            current_size = base_size * self.config.bottom_continuation_multiplier
            stage = "stage2_continuation"
            
        else:
            current_size = base_size
            stage = "normal"
            # 市場回復時の状態リセット
            if breadth_8ma > self.config.bottom_reset_threshold:
                self._reset_bottom_states(date_key)
        
        # 状態のクリーンアップ（古い状態を削除）
        self._cleanup_old_states(date)
        
        return current_size, f"{stage}_8ma_{breadth_8ma:.3f}"
    
    def _check_8ma_bottom_history(self, current_date_key: str) -> bool:
        """過去数日間に8MA底検出があったかチェック"""
        for state_date, state_data in self.state.items():
            if state_data.get('8ma_bottom_detected', False):
                # 過去10日以内なら有効とする
                try:
                    state_dt = datetime.strptime(state_date, '%Y-%m-%d')
                    current_dt = datetime.strptime(current_date_key, '%Y-%m-%d')
                    days_diff = (current_dt - state_dt).days
                    if 0 <= days_diff <= 10:
                        return True
                except:
                    continue
        return False
    
    def _reset_bottom_states(self, current_date_key: str):
        """8MA底検出状態をリセット"""
        keys_to_reset = []
        for date_key, state_data in self.state.items():
            if state_data.get('8ma_bottom_detected', False):
                keys_to_reset.append(date_key)
        
        for key in keys_to_reset:
            if key in self.state:
                self.state[key]['8ma_bottom_detected'] = False
    
    def _cleanup_old_states(self, current_date: datetime):
        """30日以上古い状態データを削除"""
        cutoff_date = current_date.replace(day=1)  # 月初めより前を削除
        keys_to_delete = []
        
        for date_key in self.state.keys():
            try:
                state_date = datetime.strptime(date_key, '%Y-%m-%d')
                if state_date < cutoff_date:
                    keys_to_delete.append(date_key)
            except:
                # 不正な日付キーは削除
                keys_to_delete.append(date_key)
        
        for key in keys_to_delete:
            del self.state[key]
    
    def _log_calculation(self, date: datetime, market_data: Dict[str, Any], 
                        size: float, reason: str):
        """ポジションサイズ計算のログ出力"""
        if market_data:
            breadth_8ma = market_data.get('breadth_8ma', 0)
            bearish_signal = market_data.get('bearish_signal', False)
            is_trough = market_data.get('is_trough', False)
            
            logging.info(
                f"Position Size Calculation - "
                f"Date: {date.strftime('%Y-%m-%d')}, "
                f"Pattern: {self.config.position_pattern}, "
                f"Size: {size:.1f}%, "
                f"Reason: {reason}, "
                f"Breadth8MA: {breadth_8ma:.3f}, "
                f"Bearish: {bearish_signal}, "
                f"Trough: {is_trough}"
            )
        else:
            logging.warning(
                f"Position Size Calculation - "
                f"Date: {date.strftime('%Y-%m-%d')}, "
                f"Size: {size:.1f}%, "
                f"Reason: {reason} (No market data)"
            )
    
    def get_state_summary(self) -> Dict[str, Any]:
        """現在の状態の要約を取得（デバッグ用）"""
        return {
            'pattern': self.config.position_pattern,
            'state_entries': len(self.state),
            'active_8ma_bottoms': sum(1 for state in self.state.values() 
                                    if state.get('8ma_bottom_detected', False)),
            'recent_states': dict(list(self.state.items())[-5:])  # 最新5件
        }
    
    def reset_state(self):
        """状態をリセット（新しいバックテスト開始時）"""
        self.state.clear()
        logging.info(f"Position Calculator state reset for pattern: {self.config.position_pattern}")