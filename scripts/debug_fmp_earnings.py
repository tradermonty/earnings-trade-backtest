#!/usr/bin/env python3
"""
Debug FMP earnings data to understand filtering issues
"""

import os
from dotenv import load_dotenv
load_dotenv()

from src.fmp_data_fetcher import FMPDataFetcher

def debug_fmp_earnings():
    fmp = FMPDataFetcher()
    earnings_data = fmp.get_earnings_calendar('2025-07-21', '2025-07-24')
    
    print('Retrieved earnings data:')
    for i, record in enumerate(earnings_data):
        actual = record.get('epsActual')
        estimate = record.get('epsEstimate')
        surprise_pct = 0
        
        if actual is not None and estimate is not None and estimate != 0:
            surprise_pct = ((actual - estimate) / abs(estimate)) * 100
        
        print(f'{i+1}. {record["symbol"]} - {record["date"]}')
        print(f'   EPS: {actual} vs {estimate} (surprise: {surprise_pct:.1f}%)')
        print(f'   Passes 5% surprise: {surprise_pct >= 5}')
        print(f'   Positive actual: {actual is not None and actual > 0}')
        print()

if __name__ == "__main__":
    debug_fmp_earnings()