"""
動的ポジションサイズ調整用の設定クラス
既存のBacktestConfigを継承して拡張
"""

import sys
import os
from dataclasses import dataclass
from typing import Optional, Set, Union

# 既存のsrcモジュールをインポート
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# BacktestConfigの基本属性を定義
@dataclass
class BaseBacktestConfig:
    """BacktestConfigの基本属性"""
    start_date: str
    end_date: str
    stop_loss: float = 6
    trail_stop_ma: int = 21
    max_holding_days: int = 90
    initial_capital: float = 100000
    position_size: float = 10
    slippage: float = 0.3
    risk_limit: float = 6
    partial_profit: bool = True
    sp500_only: bool = False
    mid_small_only: bool = False
    language: str = 'en'
    pre_earnings_change: float = 0
    margin_ratio: float = 1.5
    target_symbols: Optional[Set[str]] = None
    enable_earnings_date_validation: bool = False
    use_fmp_data: bool = True
    max_gap_percent: float = 10.0
    max_ps_ratio: Optional[float] = None
    max_pe_ratio: Optional[float] = None
    min_profit_margin: Optional[float] = None
    screener_price_min: float = 10.0
    screener_volume_min: int = 200_000
    min_market_cap: float = 1e9
    max_market_cap: float = 50e9


@dataclass
class DynamicPositionSizeConfig(BaseBacktestConfig):
    """動的ポジションサイズ調整用の拡張設定クラス"""
    
    # CSVファイル設定
    breadth_csv_path: str = "data/market_breadth_data_20250817_ma8.csv"
    
    # 調整パターン選択 (4パターン)
    position_pattern: str = "breadth_8ma"  # "breadth_8ma" | "advanced_5stage" | "bearish_signal" | "bottom_3stage"
    
    # Pattern 1: 基本3段階設定
    stress_position_size: float = 8.0      # breadth_8ma < 0.4
    normal_position_size: float = 15.0     # 0.4 <= breadth_8ma < 0.7
    bullish_position_size: float = 20.0    # breadth_8ma >= 0.7
    
    # Pattern 2: 細分化5段階設定
    extreme_stress_position: float = 6.0   # < 0.3
    stress_position: float = 10.0          # 0.3-0.4
    normal_position: float = 15.0          # 0.4-0.7
    bullish_position: float = 20.0         # 0.7-0.8
    extreme_bullish_position: float = 25.0 # >= 0.8
    
    # Pattern 3: Bearish Signal設定
    bearish_reduction_multiplier: float = 0.6  # Bearish時の削減率
    
    # Pattern 4: ボトム検出3段階設定
    bearish_stage_multiplier: float = 0.7      # Stage1: Bearish時削減
    bottom_8ma_multiplier: float = 1.3         # Stage2: 8MA底検出時増加
    bottom_200ma_multiplier: float = 1.6       # Stage3: 200MA底検出時増加
    bottom_continuation_multiplier: float = 1.2 # Stage2継続効果
    bottom_continuation_threshold: float = 0.5  # 継続効果の閾値
    bottom_reset_threshold: float = 0.6        # 効果リセットの閾値
    
    # 共通制限設定
    min_position_size: float = 5.0
    max_position_size: float = 25.0
    default_position_size: float = 15.0    # データ欠損時のデフォルト
    
    # ログ・デバッグ設定
    enable_logging: bool = True            # 詳細ログ
    enable_state_tracking: bool = True     # Pattern 4用の状態追跡
    log_position_changes: bool = True      # ポジションサイズ変更のログ
    
    def __post_init__(self):
        """設定の検証とデフォルト値の調整"""
        super().__post_init__() if hasattr(super(), '__post_init__') else None
        
        # パターンの妥当性チェック
        valid_patterns = ["breadth_8ma", "advanced_5stage", "bearish_signal", "bottom_3stage"]
        if self.position_pattern not in valid_patterns:
            raise ValueError(f"Invalid position_pattern: {self.position_pattern}. "
                           f"Must be one of {valid_patterns}")
        
        # ポジションサイズの妥当性チェック
        position_sizes = [
            self.stress_position_size, self.normal_position_size, self.bullish_position_size,
            self.extreme_stress_position, self.stress_position, self.normal_position,
            self.bullish_position, self.extreme_bullish_position, self.default_position_size
        ]
        
        for size in position_sizes:
            if not (0 < size <= 100):
                raise ValueError(f"Position size must be between 0 and 100, got {size}")
        
        # 制限値の妥当性チェック
        if self.min_position_size >= self.max_position_size:
            raise ValueError("min_position_size must be less than max_position_size")
        
        # 倍率の妥当性チェック
        multipliers = [
            self.bearish_reduction_multiplier, self.bearish_stage_multiplier,
            self.bottom_8ma_multiplier, self.bottom_200ma_multiplier,
            self.bottom_continuation_multiplier
        ]
        
        for mult in multipliers:
            if not (0.1 <= mult <= 3.0):
                raise ValueError(f"Multiplier must be between 0.1 and 3.0, got {mult}")
        
        # 閾値の妥当性チェック
        thresholds = [self.bottom_continuation_threshold, self.bottom_reset_threshold]
        for thresh in thresholds:
            if not (0.0 <= thresh <= 1.0):
                raise ValueError(f"Threshold must be between 0.0 and 1.0, got {thresh}")
        
        # CSVファイルパスの調整（相対パス → 絶対パス）
        if not os.path.isabs(self.breadth_csv_path):
            # スクリプトの場所から相対的にパスを解決
            script_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            self.breadth_csv_path = os.path.join(script_dir, self.breadth_csv_path)
    
    def get_pattern_description(self) -> str:
        """選択されたパターンの説明を取得"""
        descriptions = {
            "breadth_8ma": "シンプル3段階: Breadth Index 8MAのみで調整",
            "advanced_5stage": "細分化5段階: より精密な市場状況対応",
            "bearish_signal": "Bearish Signal連動: リスク管理重視",
            "bottom_3stage": "ボトム検出3段階: 市場転換点を狙った最高度戦略"
        }
        return descriptions.get(self.position_pattern, "Unknown pattern")
    
    def get_position_size_ranges(self) -> dict:
        """各パターンでのポジションサイズ範囲を取得"""
        if self.position_pattern == "breadth_8ma":
            return {
                "stress": self.stress_position_size,
                "normal": self.normal_position_size,
                "bullish": self.bullish_position_size
            }
        elif self.position_pattern == "advanced_5stage":
            return {
                "extreme_stress": self.extreme_stress_position,
                "stress": self.stress_position,
                "normal": self.normal_position,
                "bullish": self.bullish_position,
                "extreme_bullish": self.extreme_bullish_position
            }
        elif self.position_pattern == "bearish_signal":
            base_ranges = self.get_position_size_ranges()
            return {
                "base_stress": self.stress_position_size,
                "base_normal": self.normal_position_size,
                "base_bullish": self.bullish_position_size,
                "bearish_stress": self.stress_position_size * self.bearish_reduction_multiplier,
                "bearish_normal": self.normal_position_size * self.bearish_reduction_multiplier,
                "bearish_bullish": self.bullish_position_size * self.bearish_reduction_multiplier
            }
        elif self.position_pattern == "bottom_3stage":
            base_size = self.normal_position_size
            return {
                "bearish_stage": base_size * self.bearish_stage_multiplier,
                "normal": base_size,
                "8ma_bottom": base_size * self.bottom_8ma_multiplier,
                "200ma_bottom": base_size * self.bottom_200ma_multiplier,
                "continuation": base_size * self.bottom_continuation_multiplier
            }
        else:
            return {"default": self.default_position_size}
    
    def validate_csv_file(self) -> bool:
        """CSVファイルの存在確認"""
        return os.path.exists(self.breadth_csv_path)
    
    def copy_with_pattern(self, new_pattern: str):
        """パターンのみを変更した新しい設定を作成"""
        import copy
        new_config = copy.deepcopy(self)
        new_config.position_pattern = new_pattern
        return new_config
    
    def to_dict(self) -> dict:
        """設定を辞書形式で出力（レポート用）"""
        return {
            'pattern': self.position_pattern,
            'pattern_description': self.get_pattern_description(),
            'csv_path': self.breadth_csv_path,
            'position_ranges': self.get_position_size_ranges(),
            'limits': {
                'min': self.min_position_size,
                'max': self.max_position_size,
                'default': self.default_position_size
            },
            'logging_enabled': self.enable_logging,
            'state_tracking_enabled': self.enable_state_tracking
        }