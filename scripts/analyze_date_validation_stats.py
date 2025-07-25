#!/usr/bin/env python3
"""
Earnings date validation statistics analysis
"""

import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd

# Load environment variables
load_dotenv()

from src.news_fetcher import NewsFetcher
from src.earnings_date_validator import EarningsDateValidator
from src.data_fetcher import DataFetcher

def analyze_date_validation_stats():
    """Analyze earnings date validation statistics for H1 2025"""
    
    # Initialize components
    api_key = os.getenv('EODHD_API_KEY')
    data_fetcher = DataFetcher()
    news_fetcher = NewsFetcher(api_key)
    validator = EarningsDateValidator(news_fetcher)

    print('=== 決算日検証統計分析 (2025年上半期) ===')
    print()

    # Get earnings data for H1 2025
    print('決算データを取得中...')
    earnings_data = data_fetcher.get_earnings_data('2025-01-01', '2025-06-30')
    earnings_list = earnings_data['earnings']
    
    print(f'総決算データ数: {len(earnings_list)}')
    
    # Filter for US stocks only
    us_earnings = [e for e in earnings_list if e.get('code', '').endswith('.US')]
    print(f'US株決算データ数: {len(us_earnings)}')
    
    # Sample analysis with first 50 US stocks for performance
    sample_size = min(50, len(us_earnings))
    sample_earnings = us_earnings[:sample_size]
    
    print(f'サンプル分析対象: {sample_size}銘柄')
    print()
    
    # Validation statistics
    validation_stats = {
        'total_validated': 0,
        'date_changed': 0,
        'no_change': 0,
        'validation_failed': 0,
        'high_confidence': 0,
        'medium_confidence': 0,
        'low_confidence': 0,
        'very_low_confidence': 0,
        'timing_detected': 0,
        'timing_mismatches': 0
    }
    
    detailed_results = []
    
    print('検証を実行中...')
    for i, earning in enumerate(sample_earnings):
        try:
            symbol = earning.get('code', '').replace('.US', '')
            eodhd_date = earning.get('report_date')
            eodhd_timing = earning.get('before_after_market')
            
            if not symbol or not eodhd_date:
                continue
            
            print(f'  {i+1}/{sample_size}: {symbol} ({eodhd_date})')
            
            # Validate earnings date
            result = validator.validate_earnings_date(symbol, eodhd_date)
            
            validation_stats['total_validated'] += 1
            
            # Date change analysis
            if result['date_changed']:
                validation_stats['date_changed'] += 1
                date_diff = abs((datetime.strptime(result['actual_date'], '%Y-%m-%d') - 
                               datetime.strptime(eodhd_date, '%Y-%m-%d')).days)
            else:
                validation_stats['no_change'] += 1
                date_diff = 0
            
            # Confidence level analysis
            confidence_level = result['confidence_level']
            if confidence_level == 'high':
                validation_stats['high_confidence'] += 1
            elif confidence_level == 'medium':
                validation_stats['medium_confidence'] += 1
            elif confidence_level == 'low':
                validation_stats['low_confidence'] += 1
            else:
                validation_stats['very_low_confidence'] += 1
            
            # Timing analysis
            timing_info = result.get('announcement_timing', {})
            detected_timing = timing_info.get('type', 'unknown')
            
            if detected_timing != 'unknown':
                validation_stats['timing_detected'] += 1
                
                # Check for timing mismatch with EODHD
                if eodhd_timing:
                    eodhd_timing_normalized = eodhd_timing.lower()
                    if ((detected_timing == 'before_market' and 'after' in eodhd_timing_normalized) or
                        (detected_timing == 'after_market' and 'before' in eodhd_timing_normalized)):
                        validation_stats['timing_mismatches'] += 1
            
            # Store detailed results
            detailed_results.append({
                'symbol': symbol,
                'eodhd_date': eodhd_date,
                'validated_date': result['actual_date'],
                'date_changed': result['date_changed'],
                'date_diff_days': date_diff,
                'confidence': result['confidence'],
                'confidence_level': confidence_level,
                'eodhd_timing': eodhd_timing,
                'detected_timing': detected_timing,
                'timing_confidence': timing_info.get('confidence', 0.0),
                'news_articles': len(result['news_evidence'])
            })
            
        except Exception as e:
            print(f'    エラー: {e}')
            validation_stats['validation_failed'] += 1
            continue
    
    print()
    print('=== 分析結果 ===')
    print()
    
    # Overall statistics
    total = validation_stats['total_validated']
    if total > 0:
        print(f'【決算日検証統計】')
        print(f'総検証銘柄数: {total}')
        print(f'日付変更あり: {validation_stats["date_changed"]} ({validation_stats["date_changed"]/total*100:.1f}%)')
        print(f'日付変更なし: {validation_stats["no_change"]} ({validation_stats["no_change"]/total*100:.1f}%)')
        print(f'検証失敗: {validation_stats["validation_failed"]}')
        print()
        
        print(f'【信頼度分布】')
        print(f'高信頼度: {validation_stats["high_confidence"]} ({validation_stats["high_confidence"]/total*100:.1f}%)')
        print(f'中信頼度: {validation_stats["medium_confidence"]} ({validation_stats["medium_confidence"]/total*100:.1f}%)')
        print(f'低信頼度: {validation_stats["low_confidence"]} ({validation_stats["low_confidence"]/total*100:.1f}%)')
        print(f'最低信頼度: {validation_stats["very_low_confidence"]} ({validation_stats["very_low_confidence"]/total*100:.1f}%)')
        print()
        
        print(f'【タイミング検証】')
        print(f'タイミング検出成功: {validation_stats["timing_detected"]} ({validation_stats["timing_detected"]/total*100:.1f}%)')
        print(f'EODHDとのタイミング不一致: {validation_stats["timing_mismatches"]}')
        print()
    
    # Date change analysis
    date_changes = [r for r in detailed_results if r['date_changed']]
    if date_changes:
        print(f'【日付変更の詳細】')
        print(f'平均変更日数: {sum(r["date_diff_days"] for r in date_changes)/len(date_changes):.1f}日')
        
        # Show examples of significant date changes
        significant_changes = [r for r in date_changes if r['date_diff_days'] > 7]
        if significant_changes:
            print(f'大幅変更 (>7日): {len(significant_changes)}件')
            print('例:')
            for r in significant_changes[:5]:
                print(f'  {r["symbol"]}: {r["eodhd_date"]} → {r["validated_date"]} ({r["date_diff_days"]}日差)')
        print()
    
    # Timing mismatch examples
    timing_mismatches = [r for r in detailed_results if r['detected_timing'] != 'unknown' and 
                        r['eodhd_timing'] and
                        ((r['detected_timing'] == 'before_market' and 'After' in r['eodhd_timing']) or
                         (r['detected_timing'] == 'after_market' and 'Before' in r['eodhd_timing']))]
    
    if timing_mismatches:
        print(f'【タイミング不一致の例】')
        for r in timing_mismatches[:5]:
            print(f'  {r["symbol"]}: EODHD={r["eodhd_timing"]} vs 検出={r["detected_timing"]} (信頼度:{r["timing_confidence"]:.2f})')
        print()
    
    # Summary
    print('【サマリー】')
    if total > 0:
        accuracy_rate = validation_stats["date_changed"] / total * 100
        print(f'• EODHDの決算日精度: {100-accuracy_rate:.1f}% (推定)')
        print(f'• 日付修正が必要な割合: {accuracy_rate:.1f}%')
        print(f'• 高精度検証の割合: {validation_stats["high_confidence"]/total*100:.1f}%')
        print(f'• タイミング検出成功率: {validation_stats["timing_detected"]/total*100:.1f}%')
    
    return validation_stats, detailed_results

if __name__ == "__main__":
    stats, results = analyze_date_validation_stats()