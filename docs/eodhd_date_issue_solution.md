# EODHD決算日のずれ問題と解決策

## 問題の概要
EODHDの決算データで提供される決算日（report_date）が実際の決算発表日と1日ずれているケースがある。

例：MANHの場合
- EODHDのデータ: 2025-07-21
- 実際の決算発表日: 2025-07-22

この結果、システムが決算発表前にエントリーし、ギャップアップの利益を不正に獲得してしまう。

## 問題の影響
1. バックテスト結果が非現実的に良くなる
2. 実際には取引できないタイミングでエントリーしている
3. リスクとリターンの評価が不正確になる

## 解決策の提案

### 1. 短期的な解決策：before_after_marketフィールドの活用強化
```python
# data_filter.pyのdetermine_trade_date関数を改善
def determine_trade_date(self, report_date: str, market_timing: str) -> str:
    """決算発表タイミングに基づいてトレード日を決定"""
    base_date = datetime.strptime(report_date, '%Y-%m-%d')
    
    # market_timingが不明な場合は、保守的に翌営業日にトレード
    if not market_timing or market_timing == 'Unknown':
        # 翌営業日を計算（週末を考慮）
        trade_date = base_date + timedelta(days=1)
        while trade_date.weekday() >= 5:  # 土日の場合
            trade_date += timedelta(days=1)
        return trade_date.strftime('%Y-%m-%d')
    
    if 'Before' in market_timing:
        # 開始前なら当日にトレード
        return base_date.strftime('%Y-%m-%d')
    else:
        # 終了後の場合は翌営業日にトレード
        trade_date = base_date + timedelta(days=1)
        while trade_date.weekday() >= 5:  # 土日の場合
            trade_date += timedelta(days=1)
        return trade_date.strftime('%Y-%m-%d')
```

### 2. 中期的な解決策：ギャップ検証の追加
```python
def validate_gap_timing(self, stock_data, report_date, trade_date):
    """ギャップが決算後に発生しているか検証"""
    # 決算日前後の出来高を比較
    # 通常、決算発表時は出来高が急増する
    report_idx = stock_data.index.get_loc(report_date)
    if report_idx > 0:
        prev_volume = stock_data.iloc[report_idx - 1]['Volume']
        report_volume = stock_data.iloc[report_idx]['Volume']
        
        # 出来高が2倍以上になっていない場合は警告
        if report_volume < prev_volume * 2:
            print(f"警告: 決算日の出来高増加が少ない可能性があります")
            return False
    return True
```

### 3. 長期的な解決策：複数データソースの照合
- 別のAPIやWebスクレイピングで実際の決算発表日を確認
- EODHDのデータと照合して差異を検出
- 差異がある場合は保守的なアプローチを採用

### 4. 実装提案：データ検証機能の追加
```python
class DataValidator:
    """データの妥当性を検証するクラス"""
    
    def validate_earnings_date(self, earnings_data, stock_data):
        """決算日の妥当性を検証"""
        # 1. 出来高の急増をチェック
        # 2. 価格の大きな変動をチェック
        # 3. before_after_marketフィールドとの整合性をチェック
        pass
    
    def suggest_trade_date(self, report_date, validation_result):
        """検証結果に基づいて適切なトレード日を提案"""
        if not validation_result['is_valid']:
            # 疑わしい場合は1日遅らせる
            return self._next_business_day(report_date)
        return report_date
```

## 推奨される対応
1. **即座に実装**: before_after_marketフィールドが不明な場合は翌営業日にトレード
2. **テスト追加**: 決算日のずれを検出するテストケースを追加
3. **ログ強化**: 疑わしいケースをログに記録して後で分析
4. **パラメータ追加**: 「保守的モード」を追加し、常に翌営業日にトレードするオプションを提供

これにより、より現実的で信頼性の高いバックテスト結果を得ることができます。