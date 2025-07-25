#!/usr/bin/env python3
"""
MANH enhanced validation test
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.news_fetcher import NewsFetcher
from src.earnings_date_validator import EarningsDateValidator
from src.data_fetcher import DataFetcher

def test_manh_validation():
    """Test MANH with enhanced validation system"""
    
    # Initialize components
    api_key = os.getenv('EODHD_API_KEY')
    data_fetcher = DataFetcher()
    news_fetcher = NewsFetcher(api_key)
    validator = EarningsDateValidator(news_fetcher)

    # Get earnings data for MANH period
    earnings_data = data_fetcher.get_earnings_data('2025-07-20', '2025-07-25')
    earnings_list = earnings_data['earnings']

    print('=== MANH Enhanced Validation Results ===')

    # Find MANH earnings
    manh_earnings = [e for e in earnings_list if e.get('code') == 'MANH.US']

    if manh_earnings:
        earning = manh_earnings[0]
        eodhd_date = earning.get('report_date')
        eodhd_timing = earning.get('before_after_market', 'Unknown')
        actual_eps = earning.get('actual')
        estimate_eps = earning.get('estimate')
        
        print(f'MANH:')
        print(f'  EODHD Report Date: {eodhd_date}')
        print(f'  EODHD Timing: {eodhd_timing}')
        print(f'  Actual EPS: {actual_eps}')
        print(f'  Estimate EPS: {estimate_eps}')
        if actual_eps and estimate_eps:
            surprise_pct = ((actual_eps - estimate_eps) / estimate_eps * 100)
            print(f'  EPS Surprise: {surprise_pct:.1f}%')
        else:
            print(f'  EPS Surprise: N/A')
        print()
        
        # Enhanced validation with timing detection
        if eodhd_date:
            result = validator.validate_earnings_date('MANH', eodhd_date)
            print(f'  Validated Date: {result["actual_date"]}')
            print(f'  Date Confidence: {result["confidence"]:.2f} ({result["confidence_level"]})')
            print(f'  Date Changed: {result["date_changed"]}')
            print()
            
            # Display timing information
            timing = result.get('announcement_timing', {})
            if timing.get('type') != 'unknown':
                timing_type = timing['type'].replace('_', ' ').title()
                timing_confidence = timing.get('confidence', 0.0)
                print(f'  Detected Timing: {timing_type} (confidence: {timing_confidence:.2f})')
                
                # Show evidence for timing
                all_timings = timing.get('all_timings', {})
                if all_timings:
                    print(f'  Timing Evidence: {dict(all_timings)}')
            else:
                print(f'  Detected Timing: Unknown')
            print()
            
            print(f'  News Articles Found: {len(result["news_evidence"])}')
            
            # Show sample timing evidence from articles
            evidence_with_timing = [e for e in result["news_evidence"] if e.get('timing_info', {}).get('type') != 'unknown']
            if evidence_with_timing:
                print(f'  Sample Timing Evidence:')
                for i, evidence in enumerate(evidence_with_timing[:3]):  # Show first 3
                    timing_info = evidence.get('timing_info', {})
                    print(f'    {i+1}. "{evidence["title"][:60]}..."')
                    print(f'       Date: {evidence["date"][:10]}')
                    print(f'       Timing: {timing_info.get("type", "unknown")} (conf: {timing_info.get("confidence", 0.0):.2f})')
                    phrases = timing_info.get("matched_phrases", [])
                    if phrases:
                        print(f'       Phrases: {phrases[:3]}')  # Show first 3 phrases
                    print()
            
            # Show general earnings evidence
            print(f'  Sample Earnings Articles:')
            for i, evidence in enumerate(result["news_evidence"][:3]):
                print(f'    {i+1}. "{evidence["title"][:60]}..."')
                print(f'       Date: {evidence["date"][:10]}')
                print(f'       Score: {evidence["earnings_score"]:.2f}')
                extracted_dates = evidence.get("extracted_dates", [])
                if extracted_dates:
                    dates = [d["date"] for d in extracted_dates if d.get("date")]
                    print(f'       Extracted Dates: {dates[:3]}')
                print()
            
    else:
        print('MANH: No earnings data found in EODHD for this period')

if __name__ == "__main__":
    test_manh_validation()