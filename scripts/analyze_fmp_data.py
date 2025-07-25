#!/usr/bin/env python3
"""
FMP決算データの詳細分析
"""

import os
from dotenv import load_dotenv
load_dotenv()

from src.fmp_data_fetcher import FMPDataFetcher
from datetime import datetime
import pandas as pd

print('=== 決算データの詳細分析 ===')
fmp = FMPDataFetcher()

# データ取得
calendar_data = fmp._make_request('earnings-calendar', {})
print(f'\n総データ数: {len(calendar_data)}')

# 最初の1000件を詳細分析
sample_data = calendar_data[:1000]
print(f'\n分析対象: {len(sample_data)}件')

# 日付分布を確認
dates = [item.get('date', '') for item in sample_data]
date_counts = pd.Series(dates).value_counts().sort_index()
print('\n日付別データ数:')
for date, count in date_counts.head(10).items():
    print(f'  {date}: {count}件')

# 実績値の有無を確認
has_actual = sum(1 for item in sample_data if item.get('epsActual') is not None)
has_estimate = sum(1 for item in sample_data if item.get('epsEstimated') is not None)

print(f'\n実績値（epsActual）あり: {has_actual}件 ({has_actual/len(sample_data)*100:.1f}%)')
print(f'予想値（epsEstimated）あり: {has_estimate}件 ({has_estimate/len(sample_data)*100:.1f}%)')

# 実績値がある銘柄のサンプル
print('\n実績値がある銘柄の例:')
count = 0
for item in sample_data:
    if item.get('epsActual') is not None and item.get('epsEstimated') is not None:
        actual = item.get('epsActual')
        estimated = item.get('epsEstimated')
        if estimated != 0:
            surprise = ((actual - estimated) / abs(estimated)) * 100
            print(f'  {item.get("symbol")}: {item.get("date")} - Actual: {actual}, Est: {estimated}, Surprise: {surprise:.1f}%')
            count += 1
            if count >= 5:
                break

# 今日の日付
today = datetime.now().strftime('%Y-%m-%d')
print(f'\n今日の日付: {today}')

# 過去のデータ（実績値がある可能性が高い）を確認
past_data = [item for item in sample_data if item.get('date', '') < today]
future_data = [item for item in sample_data if item.get('date', '') >= today]

print(f'\n過去の決算: {len(past_data)}件')
print(f'将来の決算: {len(future_data)}件')

# 過去データの実績値有無
if past_data:
    past_has_actual = sum(1 for item in past_data if item.get('epsActual') is not None)
    print(f'過去データで実績値あり: {past_has_actual}件 ({past_has_actual/len(past_data)*100:.1f}%)')

# lastUpdated日付を確認
print('\n最終更新日の分布:')
last_updated_dates = [item.get('lastUpdated', '') for item in sample_data[:100]]
update_counts = pd.Series(last_updated_dates).value_counts().head(5)
for date, count in update_counts.items():
    print(f'  {date}: {count}件')