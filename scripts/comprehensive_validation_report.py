#!/usr/bin/env python3
"""
Comprehensive earnings date validation report
"""

import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import defaultdict
import json

# Load environment variables
load_dotenv()

from src.news_fetcher import NewsFetcher
from src.earnings_date_validator import EarningsDateValidator
from src.data_fetcher import DataFetcher

def generate_comprehensive_report():
    """Generate comprehensive validation statistics report"""
    
    # Initialize components
    api_key = os.getenv('EODHD_API_KEY')
    data_fetcher = DataFetcher()
    news_fetcher = NewsFetcher(api_key)
    validator = EarningsDateValidator(news_fetcher)

    print('=== 決算日検証システム包括的分析レポート ===')
    print('期間: 2025年上半期 (2025-01-01 to 2025-06-30)')
    print()

    # Get earnings data for H1 2025
    print('決算データを取得中...')
    earnings_data = data_fetcher.get_earnings_data('2025-01-01', '2025-06-30')
    earnings_list = earnings_data['earnings']
    
    print(f'総決算データ数: {len(earnings_list):,}')
    
    # Filter for US stocks only and with meaningful data
    us_earnings = []
    for e in earnings_list:
        if (e.get('code', '').endswith('.US') and 
            e.get('actual') is not None and 
            e.get('estimate') is not None and
            e.get('actual') > 0):  # Positive earnings only
            us_earnings.append(e)
    
    print(f'分析対象US株決算データ数: {len(us_earnings):,}')
    
    # Expand sample size for more comprehensive analysis
    sample_size = min(100, len(us_earnings))
    sample_earnings = us_earnings[:sample_size]
    
    print(f'詳細分析サンプル: {sample_size}銘柄')
    print()
    
    # Enhanced validation statistics
    validation_stats = {
        'analyzed': 0,
        'validation_attempted': 0,
        'validation_successful': 0,
        'date_changed': 0,
        'no_change': 0,
        'validation_failed': 0,
        'high_confidence': 0,
        'medium_confidence': 0,
        'low_confidence': 0,
        'very_low_confidence': 0,
        'timing_detected': 0,
        'timing_mismatches': 0,
        'news_articles_found': 0,
        'major_date_changes': 0,  # >7 days
        'minor_date_changes': 0   # <=7 days
    }
    
    date_changes_distribution = defaultdict(int)
    timing_analysis = defaultdict(int)
    detailed_results = []
    significant_cases = []
    
    print('包括的検証を実行中...')
    for i, earning in enumerate(sample_earnings):
        try:
            symbol = earning.get('code', '').replace('.US', '')
            eodhd_date = earning.get('report_date')
            eodhd_timing = earning.get('before_after_market')
            actual_eps = earning.get('actual', 0)
            estimate_eps = earning.get('estimate', 0)
            
            validation_stats['analyzed'] += 1
            
            if not symbol or not eodhd_date:
                continue
            
            validation_stats['validation_attempted'] += 1
            print(f'  {i+1}/{sample_size}: {symbol} ({eodhd_date}) EPS: {actual_eps:.3f}')
            
            # Validate earnings date
            result = validator.validate_earnings_date(symbol, eodhd_date)
            validation_stats['validation_successful'] += 1
            
            # Count news articles
            news_count = len(result['news_evidence'])
            validation_stats['news_articles_found'] += news_count
            
            # Date change analysis
            date_changed = result['date_changed']
            if date_changed:
                validation_stats['date_changed'] += 1
                date_diff = abs((datetime.strptime(result['actual_date'], '%Y-%m-%d') - 
                               datetime.strptime(eodhd_date, '%Y-%m-%d')).days)
                
                date_changes_distribution[date_diff] += 1
                
                if date_diff > 7:
                    validation_stats['major_date_changes'] += 1
                else:
                    validation_stats['minor_date_changes'] += 1
                    
                # Store significant cases
                if date_diff > 14 or result['confidence'] > 0.8:
                    significant_cases.append({
                        'symbol': symbol,
                        'eodhd_date': eodhd_date,
                        'validated_date': result['actual_date'],
                        'date_diff': date_diff,
                        'confidence': result['confidence'],
                        'news_count': news_count,
                        'eps_surprise': ((actual_eps - estimate_eps) / estimate_eps * 100) if estimate_eps != 0 else 0
                    })
            else:
                validation_stats['no_change'] += 1
            
            # Confidence level analysis
            confidence_level = result['confidence_level']
            validation_stats[f'{confidence_level}_confidence'] += 1
            
            # Timing analysis
            timing_info = result.get('announcement_timing', {})
            detected_timing = timing_info.get('type', 'unknown')
            
            timing_analysis[detected_timing] += 1
            
            if detected_timing != 'unknown':
                validation_stats['timing_detected'] += 1
                
                # Check for timing mismatch with EODHD
                if eodhd_timing:
                    eodhd_timing_normalized = eodhd_timing.lower()
                    timing_mismatch = False
                    
                    if ((detected_timing == 'before_market' and 'after' in eodhd_timing_normalized) or
                        (detected_timing == 'after_market' and 'before' in eodhd_timing_normalized)):
                        validation_stats['timing_mismatches'] += 1
                        timing_mismatch = True
            
            # Store detailed results
            detailed_results.append({
                'symbol': symbol,
                'eodhd_date': eodhd_date,
                'validated_date': result['actual_date'],
                'date_changed': date_changed,
                'date_diff_days': date_diff if date_changed else 0,
                'confidence': result['confidence'],
                'confidence_level': confidence_level,
                'eodhd_timing': eodhd_timing,
                'detected_timing': detected_timing,
                'timing_confidence': timing_info.get('confidence', 0.0),
                'news_articles': news_count,
                'eps_actual': actual_eps,
                'eps_estimate': estimate_eps,
                'eps_surprise_pct': ((actual_eps - estimate_eps) / estimate_eps * 100) if estimate_eps != 0 else 0
            })
            
        except Exception as e:
            print(f'    エラー: {e}')
            validation_stats['validation_failed'] += 1
            continue
    
    print()
    print('=== 包括的分析結果 ===')
    print()
    
    # Generate comprehensive report
    generate_detailed_report(validation_stats, detailed_results, significant_cases, 
                           date_changes_distribution, timing_analysis, sample_size)
    
    return validation_stats, detailed_results

def generate_detailed_report(stats, results, significant_cases, date_dist, timing_dist, sample_size):
    """Generate detailed analysis report"""
    
    total_successful = stats['validation_successful']
    
    print(f'【総合統計】')
    print(f'分析対象銘柄数: {sample_size}')
    print(f'検証試行数: {stats["validation_attempted"]}')
    print(f'検証成功数: {total_successful}')
    print(f'検証失敗数: {stats["validation_failed"]}')
    print(f'検証成功率: {total_successful/stats["validation_attempted"]*100:.1f}%')
    print()
    
    if total_successful > 0:
        print(f'【EODHDデータ精度分析】')
        date_accuracy = stats['no_change'] / total_successful * 100
        print(f'日付が正確: {stats["no_change"]} ({date_accuracy:.1f}%)')
        print(f'日付修正が必要: {stats["date_changed"]} ({100-date_accuracy:.1f}%)')
        print(f'  - 軽微な修正 (≤7日): {stats["minor_date_changes"]}')
        print(f'  - 大幅な修正 (>7日): {stats["major_date_changes"]}')
        print()
        
        print(f'【信頼度分析】')
        print(f'高信頼度 (≥80%): {stats["high_confidence"]} ({stats["high_confidence"]/total_successful*100:.1f}%)')
        print(f'中信頼度 (60-80%): {stats["medium_confidence"]} ({stats["medium_confidence"]/total_successful*100:.1f}%)')
        print(f'低信頼度 (40-60%): {stats["low_confidence"]} ({stats["low_confidence"]/total_successful*100:.1f}%)')
        print(f'最低信頼度 (<40%): {stats["very_low_confidence"]} ({stats["very_low_confidence"]/total_successful*100:.1f}%)')
        print()
        
        print(f'【タイミング検証】')
        print(f'タイミング検出成功: {stats["timing_detected"]} ({stats["timing_detected"]/total_successful*100:.1f}%)')
        print(f'EODHDとのタイミング不一致: {stats["timing_mismatches"]}')
        print(f'平均ニュース記事数: {stats["news_articles_found"]/total_successful:.1f}件/銘柄')
        print()
        
        # Date change distribution
        if date_dist:
            print(f'【日付変更の分布】')
            sorted_changes = sorted(date_dist.items())
            for days, count in sorted_changes[:10]:  # Show top 10
                print(f'  {days}日差: {count}件')
            print()
        
        # Timing distribution
        print(f'【検出されたタイミング分布】')
        for timing, count in timing_dist.items():
            print(f'  {timing}: {count}件')
        print()
        
        # Significant cases
        if significant_cases:
            print(f'【注目すべき修正事例】 (大幅変更または高信頼度)')
            significant_cases.sort(key=lambda x: x['date_diff'], reverse=True)
            for case in significant_cases[:10]:
                print(f"  {case['symbol']}: {case['eodhd_date']} → {case['validated_date']}")
                print(f"    差異: {case['date_diff']}日, 信頼度: {case['confidence']:.2f}, EPS驚き: {case['eps_surprise']:.1f}%")
            print()
        
        # Key insights
        print(f'【主要な洞察】')
        accuracy_rate = date_accuracy
        high_conf_rate = stats["high_confidence"]/total_successful*100
        timing_success = stats["timing_detected"]/total_successful*100
        
        print(f'• EODHDの決算日精度: {accuracy_rate:.1f}%')
        print(f'• 約{100-accuracy_rate:.0f}%の銘柄で日付修正が必要')
        if stats["major_date_changes"] > 0:
            major_pct = stats["major_date_changes"]/stats["date_changed"]*100
            print(f'• 修正が必要な銘柄の{major_pct:.0f}%は1週間以上のズレ')
        print(f'• 高信頼度検証の達成率: {high_conf_rate:.1f}%')
        print(f'• タイミング検出成功率: {timing_success:.1f}%')
        if stats["timing_mismatches"] > 0:
            mismatch_rate = stats["timing_mismatches"]/stats["timing_detected"]*100
            print(f'• 検出されたタイミングの{mismatch_rate:.0f}%がEODHDと不一致')
        print()
        
        print(f'【推奨事項】')
        print('• ニュースベースの日付検証システムの継続使用を推奨')
        if 100-accuracy_rate > 20:
            print('• EODHDデータのみに依存することは高リスク')
        if high_conf_rate > 80:
            print('• 高い検証信頼度により、修正された日付の使用が安全')
        if timing_success > 15:
            print('• タイミング検出機能により、より精密なエントリー戦略が可能')

if __name__ == "__main__":
    generate_comprehensive_report()