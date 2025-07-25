#!/usr/bin/env python3
"""
Enhanced timing detection test script
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.news_fetcher import NewsFetcher
from src.earnings_date_validator import EarningsDateValidator
from src.data_fetcher import DataFetcher

def test_timing_detection():
    """Test the enhanced timing detection system"""
    
    # Initialize components
    api_key = os.getenv('EODHD_API_KEY')
    data_fetcher = DataFetcher()
    news_fetcher = NewsFetcher(api_key)
    validator = EarningsDateValidator(news_fetcher)

    # Get earnings data for the period
    earnings_data = data_fetcher.get_earnings_data('2025-07-20', '2025-07-25')
    earnings_list = earnings_data['earnings']

    # Test symbols from Finviz screenshot
    symbols = ['MLI', 'RLI', 'TRST', 'ZION']

    print('=== Enhanced Timing Detection Test ===')
    print('Based on your Finviz screenshot + EODHD data:')
    print('- MLI: Jul 23 | EODHD: BeforeMarket')
    print('- RLI: Jul 22 | EODHD: BeforeMarket') 
    print('- TRST: Jul 22 | EODHD: AfterMarket')
    print('- ZION: Jul 22 | EODHD: AfterMarket')
    print()

    for symbol in symbols:
        try:
            # Find this symbol's earnings (look for .US suffix)
            symbol_earnings = [e for e in earnings_list if e.get('code') == f'{symbol}.US']
            
            if symbol_earnings:
                earning = symbol_earnings[0]
                eodhd_date = earning.get('report_date')
                eodhd_timing = earning.get('before_after_market', 'Unknown')
                
                print(f'{symbol}:')
                print(f'  EODHD Report Date: {eodhd_date}')
                print(f'  EODHD Timing: {eodhd_timing}')
                
                # Validate with enhanced news analysis
                if eodhd_date:
                    result = validator.validate_earnings_date(symbol, eodhd_date)
                    print(f'  Validated Date: {result["actual_date"]}')
                    print(f'  Date Confidence: {result["confidence"]:.2f} ({result["confidence_level"]})')
                    
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
                    
                    print(f'  News Articles: {len(result["news_evidence"])}')
                    
                    # Show sample timing evidence from articles
                    evidence_with_timing = [e for e in result["news_evidence"] if e.get('timing_info', {}).get('type') != 'unknown']
                    if evidence_with_timing:
                        print(f'  Sample Timing Evidence:')
                        for i, evidence in enumerate(evidence_with_timing[:2]):  # Show first 2
                            timing_info = evidence.get('timing_info', {})
                            print(f'    {i+1}. "{evidence["title"][:50]}..."')
                            print(f'       Timing: {timing_info.get("type", "unknown")} (conf: {timing_info.get("confidence", 0.0):.2f})')
                            print(f'       Phrases: {timing_info.get("matched_phrases", [])}')
                
                print()
            else:
                print(f'{symbol}: No earnings data found in EODHD')
                print()
                
        except Exception as e:
            print(f'{symbol}: Error - {e}')
            print()
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_timing_detection()