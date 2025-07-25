#!/usr/bin/env python3
"""
MANH entry timing analysis
"""

import os
from dotenv import load_dotenv
import pandas as pd

# Load environment variables
load_dotenv()

from src.data_fetcher import DataFetcher

def analyze_manh_entry():
    """Analyze MANH entry timing based on validation results"""
    
    # Get MANH price data around earnings period
    data_fetcher = DataFetcher()

    print('=== MANH エントリータイミング分析 ===')
    print()

    # Get MANH historical price data
    print('MANHの価格データを取得中...')
    manh_data = data_fetcher.get_historical_data('MANH.US', '2025-07-21', '2025-07-25')

    if manh_data is not None and not manh_data.empty:
        print('日付別価格データ:')
        prev_close = None
        
        for date, row in manh_data.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            gap = 0
            if prev_close is not None:
                gap = ((row['open'] - prev_close) / prev_close) * 100
            intraday_change = ((row['close'] - row['open']) / row['open']) * 100
            
            print(f'{date_str}:')
            print(f'  Open: ${row["open"]:.2f}')
            print(f'  High: ${row["high"]:.2f}')
            print(f'  Low: ${row["low"]:.2f}')
            print(f'  Close: ${row["close"]:.2f}')
            print(f'  Volume: {row["volume"]:,}')
            if gap != 0:
                print(f'  Gap from Previous Close: {gap:.2f}%')
            print(f'  Intraday Change: {intraday_change:.2f}%')
            print()
            
            prev_close = row['close']
        
        # Analyze based on validation results
        print('=== エントリー判断分析 ===')
        print()
        print('検証結果に基づく分析:')
        print('• 実際の決算日: 2025-07-23 (火曜日)')
        print('• 発表タイミング: After Market (引け後) - 67% confidence')
        print('• EPS サプライズ: +15.9% (ポジティブ)')
        print()
        
        # Check specific dates
        july_22_data = None
        july_23_data = None
        july_24_data = None
        
        for date, row in manh_data.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            if date_str == '2025-07-22':
                july_22_data = row
            elif date_str == '2025-07-23':
                july_23_data = row
            elif date_str == '2025-07-24':
                july_24_data = row
        
        print('【各シナリオの分析】:')
        print()
        
        # Scenario 1: Entry on 7/22 (EODHD original date + 1)
        if july_22_data is not None and july_21_data is not None:
            print('1. 7/22エントリー (EODHDベース):')
            print('   × 実際の決算日ではない')
            print('   × 決算発表前のエントリー')
            print('   → 推奨しない')
            print()
        
        # Scenario 2: Entry on 7/23 (validated actual earnings date)
        if july_23_data is not None:
            print('2. 7/23エントリー (実際の決算日):')
            print('   × 決算発表は引け後')
            print('   × 当日の朝の時点では決算結果が不明')
            print('   × 7/23日中に大幅下落(-30%以上)')
            print('   → 推奨しない (高リスク)')
            print()
        
        # Scenario 3: Entry on 7/24 (day after earnings)
        if july_23_data is not None and july_24_data is not None:
            gap_24 = ((july_24_data['open'] - july_23_data['close']) / july_23_data['close']) * 100
            print('3. 7/24エントリー (決算発表翌日):')
            print(f'   • 7/24朝のギャップ: {gap_24:.2f}%')
            
            if gap_24 > 0:
                print('   ✓ ポジティブギャップアップを確認')
                print('   ✓ 決算結果 (+15.9% EPS surprise) を反映')
                print('   ✓ After Market発表後の市場反応')
                print(f'   • エントリー価格: ${july_24_data["open"]:.2f}')
                
                # Check stop loss risk
                intraday_decline = ((july_24_data['low'] - july_24_data['open']) / july_24_data['open']) * 100
                print(f'   • 日中最大下落: {intraday_decline:.2f}%')
                
                if intraday_decline < -6:
                    print('   ⚠ 6%ストップロスに抵触')
                    print('   → エントリー可能だが即日ストップアウト')
                else:
                    print('   ✓ ストップロス範囲内')
                    print('   → 推奨エントリータイミング')
            else:
                print('   × ギャップアップなし')
                print('   → エントリー条件不適合')
            print()
        
        print('=== 最終推奨 ===')
        if july_23_data is not None and july_24_data is not None:
            gap_24 = ((july_24_data['open'] - july_23_data['close']) / july_23_data['close']) * 100
            if gap_24 > 0:
                print('【推奨エントリー】:')
                print('• 日付: 2025-07-24 (水曜日)')
                print('• タイミング: 寄り付き')
                print(f'• エントリー価格: ${july_24_data["open"]:.2f}')
                print('• 根拠: ニュース検証による正確な決算日特定 + ポジティブギャップアップ')
                print()
                print('【注意点】:')
                print('• 日中のストップロス執行に注意')
                print('• 決算発表翌日のボラティリティが高い')
            else:
                print('【エントリー非推奨】:')
                print('• ギャップアップが確認できない')
                print('• エントリー条件を満たさない')
        
    else:
        print('MANHの価格データを取得できませんでした')

if __name__ == "__main__":
    analyze_manh_entry()