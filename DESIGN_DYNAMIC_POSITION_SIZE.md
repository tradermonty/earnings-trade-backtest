# Market Breadth Index連動 動的ポジションサイズ調整システム 設計書

## 1. 設計方針

### 1.1 基本原則
- **既存コードへの非侵襲**: `main.py`, `src/`以下のコアファイルには一切変更を加えない
- **プラグイン型設計**: 新機能は独立したモジュールとして実装
- **後方互換性**: 既存の機能を完全に保持
- **段階的導入**: 簡単な設定から高度な設定まで選択可能

### 1.2 実装アプローチ
- **ラッパー方式**: 既存の`EarningsBacktest`クラスをラップする新クラスを作成
- **設定拡張**: `BacktestConfig`を継承した新設定クラス
- **CSV連携**: Market Breadth IndexデータをCSVファイルから読み込み

## 2. Market Breadth Index CSVファイル仕様

### 2.1 ファイル形式
```csv
date,breadth_8ma,breadth_200ma,market_condition
2020-01-01,0.65,0.72,normal
2020-02-15,0.35,0.68,stress
2020-03-20,0.25,0.60,extreme_stress
2020-04-30,0.45,0.65,recovery
...
```

### 2.2 列の定義
- `date`: 日付 (YYYY-MM-DD形式)
- `breadth_8ma`: S&P 500 Breadth Index 8日移動平均 (0.0-1.0)
- `breadth_200ma`: S&P 500 Breadth Index 200日移動平均 (0.0-1.0)
- `market_condition`: 市場状況 (オプション、参考用)

## 3. システム設計

### 3.1 アーキテクチャ図
```
[User] -> [DynamicPositionSizeBacktest] -> [Market Breadth Manager] -> [Original EarningsBacktest]
                                      |
                                      v
                               [CSV Data Loader]
```

### 3.2 新規作成ファイル構成
```
scripts/
├── dynamic_position_size/
│   ├── __init__.py
│   ├── breadth_manager.py           # Market Breadth データ管理
│   ├── position_calculator.py      # ポジションサイズ計算ロジック
│   ├── dynamic_backtest.py         # メインラッパークラス
│   └── config.py                   # 拡張設定クラス
├── data/
│   └── market_breadth_index.csv    # サンプルデータ
└── run_dynamic_backtest.py         # 実行スクリプト
```

## 4. 詳細設計

### 4.1 DynamicPositionSizeConfig クラス
```python
@dataclass
class DynamicPositionSizeConfig(BacktestConfig):
    # Market Breadth連動設定
    breadth_csv_path: str = "data/market_breadth_index.csv"
    dynamic_position_mode: str = "simple"  # "simple" | "advanced"
    
    # シンプル3段階設定
    stress_position_size: float = 8.0      # breadth_8ma < 0.4
    normal_position_size: float = 15.0     # 0.4 <= breadth_8ma <= 0.7
    bullish_position_size: float = 20.0    # breadth_8ma > 0.7
    
    # 細分化5段階設定 (advanced mode)
    extreme_stress_position: float = 6.0   # breadth_8ma < 0.3
    stress_position: float = 10.0          # 0.3 <= breadth_8ma < 0.4
    normal_position: float = 15.0          # 0.4 <= breadth_8ma <= 0.7
    bullish_position: float = 20.0         # 0.7 < breadth_8ma <= 0.8
    extreme_bullish_position: float = 25.0 # breadth_8ma > 0.8
    
    # フォールバック設定
    default_position_size: float = 15.0    # データが見つからない場合
    enable_logging: bool = True            # ポジションサイズ変更ログ
```

### 4.2 MarketBreadthManager クラス
```python
class MarketBreadthManager:
    def __init__(self, csv_path: str):
        self.breadth_data = self._load_csv(csv_path)
    
    def get_breadth_value(self, date: datetime) -> Optional[float]:
        """指定日のBreadth Index 8MA値を取得"""
        
    def get_market_condition(self, breadth_8ma: float) -> str:
        """Breadth値から市場状況を判定"""
        
    def _load_csv(self, csv_path: str) -> pd.DataFrame:
        """CSVファイルを読み込み、日付でインデックス化"""
```

### 4.3 PositionCalculator クラス
```python
class PositionCalculator:
    def __init__(self, config: DynamicPositionSizeConfig):
        self.config = config
    
    def calculate_position_size(self, breadth_8ma: float, date: datetime) -> float:
        """Breadth値に基づいてポジションサイズを計算"""
        
    def _simple_calculation(self, breadth_8ma: float) -> float:
        """シンプル3段階計算"""
        
    def _advanced_calculation(self, breadth_8ma: float) -> float:
        """細分化5段階計算"""
```

### 4.4 DynamicPositionSizeBacktest クラス (メインラッパー)
```python
class DynamicPositionSizeBacktest:
    def __init__(self, config: DynamicPositionSizeConfig):
        self.config = config
        self.breadth_manager = MarketBreadthManager(config.breadth_csv_path)
        self.position_calculator = PositionCalculator(config)
        self.backtest = None  # 遅延初期化
        
    def run_backtest(self) -> Dict[str, Any]:
        """動的ポジションサイズでバックテストを実行"""
        
    def _create_modified_config(self, entry_date: datetime) -> BacktestConfig:
        """エントリー日に基づいて設定を動的に変更"""
        
    def _log_position_change(self, date: datetime, breadth_value: float, 
                           position_size: float, condition: str):
        """ポジションサイズ変更をログ出力"""
```

## 5. 実装計画

### 5.1 Phase 1: 基本実装 (1-2日)
1. CSV読み込み機能の実装
2. シンプル3段階ポジションサイズ計算
3. 基本的なラッパークラス作成
4. 動作確認用の最小限のテストケース

### 5.2 Phase 2: 拡張機能 (1日)
1. 細分化5段階計算の実装
2. ログ機能の追加
3. エラーハンドリングの強化
4. パフォーマンス比較レポート機能

### 5.3 Phase 3: 最適化と検証 (1日)
1. 既存バックテストとの結果比較検証
2. パフォーマンス測定と最適化
3. ドキュメント作成
4. サンプルデータの作成

## 6. 使用方法

### 6.1 基本的な使用例
```python
# シンプル3段階モード
config = DynamicPositionSizeConfig(
    start_date="2020-09-01",
    end_date="2025-06-30",
    breadth_csv_path="data/market_breadth_index.csv",
    dynamic_position_mode="simple",
    stop_loss=10.0
)

backtest = DynamicPositionSizeBacktest(config)
results = backtest.run_backtest()
```

### 6.2 細分化モード
```python
# 細分化5段階モード
config = DynamicPositionSizeConfig(
    start_date="2020-09-01",
    end_date="2025-06-30",
    dynamic_position_mode="advanced",
    extreme_stress_position=6.0,
    stress_position=10.0,
    normal_position=15.0,
    bullish_position=20.0,
    extreme_bullish_position=25.0
)
```

### 6.3 コマンドライン実行
```bash
# シンプルモード
python scripts/run_dynamic_backtest.py --mode simple --breadth_csv data/market_breadth_index.csv

# アドバンスモード
python scripts/run_dynamic_backtest.py --mode advanced --breadth_csv data/market_breadth_index.csv
```

## 7. テスト戦略

### 7.1 単体テスト
- CSV読み込み機能
- ポジションサイズ計算ロジック
- 日付マッチング機能

### 7.2 統合テスト
- 既存バックテストとの結果一致確認（固定ポジションサイズ時）
- Market Breadthデータが欠損している期間の動作確認
- パフォーマンス向上の定量確認

### 7.3 回帰テスト
- 既存コマンドライン引数での動作確認
- 既存レポート生成機能の動作確認

## 8. リスク管理

### 8.1 技術的リスク
- **データ品質**: Market Breadth CSVデータの品質確保
- **日付ミスマッチ**: 営業日とCSVデータの日付不整合
- **パフォーマンス**: 大量データ処理時の性能劣化

### 8.2 対策
- **フォールバック機能**: データが見つからない場合のデフォルト値
- **データ補間**: 欠損データの線形補間機能
- **キャッシュ機能**: CSVデータの効率的な読み込み

## 9. 拡張計画

### 9.1 将来的な機能拡張
- リアルタイムBreadth Index API連携
- 複数指標の組み合わせ (VIX, Fear & Greed Index等)
- 機械学習ベースの動的調整
- バックテスト結果の詳細分析ダッシュボード

### 9.2 設定の柔軟性
- カスタム閾値設定機能
- 業界別・時価総額別の異なる設定
- 季節性を考慮した動的調整

## 10. 承認ポイント

この設計で以下の点について確認をお願いします：

1. **CSV形式**: 提案したCSV形式は適切か？
2. **3段階vs5段階**: どちらを優先して実装すべきか？
3. **ファイル配置**: `scripts/dynamic_position_size/`配下で良いか？
4. **設定方法**: 設定クラスの拡張方針は適切か？
5. **実行方法**: コマンドライン実行の方法は使いやすいか？

承認いただければ、Phase 1から実装を開始いたします。