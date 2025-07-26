#!/usr/bin/env python3
"""
FMP vs Finviz Earnings Date Accuracy Comparison
FMPとFinvizの決算日精度比較分析スクリプト
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import csv
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fmp_data_fetcher import FMPDataFetcher


class EarningsDateAccuracyAnalyzer:
    """決算日精度分析クラス"""
    
    def __init__(self):
        self.finviz_data = []
        self.fmp_data = []
        self.comparison_results = []
        
        # FMP Data Fetcherの初期化
        api_key = os.getenv('FMP_API_KEY')
        if not api_key:
            raise ValueError("FMP API key is required. Set FMP_API_KEY environment variable.")
        
        self.fmp_fetcher = FMPDataFetcher(api_key=api_key)
        print("FMP Data Fetcher initialized successfully")

    def load_finviz_data(self, csv_file_path: str):
        """Finvizデータの読み込み"""
        print(f"Loading Finviz data from: {csv_file_path}")
        
        try:
            df = pd.read_csv(csv_file_path)
            print(f"Loaded {len(df)} records from Finviz")
            
            # データの前処理
            processed_data = []
            for _, row in df.iterrows():
                # 決算日の解析
                earnings_date_raw = row.get('Earnings Date', '')
                if pd.isna(earnings_date_raw):
                    continue
                    
                earnings_date_str = str(earnings_date_raw).strip()
                if not earnings_date_str or earnings_date_str == '' or earnings_date_str == 'nan':
                    continue
                
                try:
                    # 日付フォーマットの解析 (例: "7/1/25 8:30" -> "2025-07-01")
                    if ' ' in earnings_date_str:
                        date_part = earnings_date_str.split(' ')[0]
                    else:
                        date_part = earnings_date_str
                    
                    # MM/DD/YY フォーマットを想定
                    if '/' in date_part:
                        parts = date_part.split('/')
                        if len(parts) == 3:
                            month, day, year = parts
                            # 2桁年を4桁に変換
                            if len(year) == 2:
                                year = '20' + year
                            
                            earnings_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                            
                            # シンボルと会社名も安全に処理
                            ticker_raw = row.get('Ticker', '')
                            company_raw = row.get('Company', '')
                            
                            symbol = str(ticker_raw).strip() if not pd.isna(ticker_raw) else ''
                            company = str(company_raw).strip() if not pd.isna(company_raw) else ''
                            
                            processed_record = {
                                'symbol': symbol,
                                'company': company,
                                'finviz_date': earnings_date,
                                'raw_date_str': earnings_date_str
                            }
                            
                            if processed_record['symbol']:
                                processed_data.append(processed_record)
                
                except Exception as e:
                    print(f"Warning: Could not parse date '{earnings_date_str}' for {row.get('Ticker', 'Unknown')}: {e}")
                    continue
            
            self.finviz_data = processed_data
            print(f"Successfully processed {len(self.finviz_data)} Finviz earnings records")
            
            # 日付範囲の確認
            dates = [record['finviz_date'] for record in self.finviz_data]
            print(f"Date range: {min(dates)} to {max(dates)}")
            
        except Exception as e:
            print(f"Error loading Finviz data: {e}")
            raise

    def fetch_fmp_data(self, start_date: str, end_date: str):
        """FMPデータの取得"""
        print(f"Fetching FMP earnings data from {start_date} to {end_date}")
        
        try:
            # FMP決算カレンダーデータを取得
            fmp_earnings = self.fmp_fetcher.get_earnings_calendar(
                start_date, end_date, us_only=True
            )
            
            print(f"Retrieved {len(fmp_earnings)} FMP earnings records")
            
            # データの前処理
            processed_fmp_data = []
            for earning in fmp_earnings:
                processed_record = {
                    'symbol': earning.get('symbol', '').strip(),
                    'fmp_date': earning.get('date', ''),
                    'eps_actual': earning.get('epsActual'),
                    'eps_estimate': earning.get('epsEstimate'),
                    'time': earning.get('time', '')
                }
                
                if processed_record['symbol'] and processed_record['fmp_date']:
                    processed_fmp_data.append(processed_record)
            
            self.fmp_data = processed_fmp_data
            print(f"Successfully processed {len(self.fmp_data)} FMP earnings records")
            
        except Exception as e:
            print(f"Error fetching FMP data: {e}")
            raise

    def compare_dates(self):
        """Finviz vs FMP 決算日比較"""
        print("\nComparing earnings dates between Finviz and FMP...")
        
        # FMPデータをsymbolでインデックス化
        fmp_dict = {}
        for record in self.fmp_data:
            symbol = record['symbol']
            if symbol not in fmp_dict:
                fmp_dict[symbol] = []
            fmp_dict[symbol].append(record)
        
        comparison_results = []
        
        for finviz_record in self.finviz_data:
            symbol = finviz_record['symbol']
            finviz_date = finviz_record['finviz_date']
            
            result = {
                'symbol': symbol,
                'company': finviz_record['company'],
                'finviz_date': finviz_date,
                'finviz_raw': finviz_record['raw_date_str'],
                'fmp_date': None,
                'fmp_time': None,
                'date_match': False,
                'date_diff_days': None,
                'status': 'NO_FMP_DATA'
            }
            
            if symbol in fmp_dict:
                # 同じ銘柄のFMPデータを検索
                fmp_records = fmp_dict[symbol]
                
                # 最も近い日付を探す
                best_match = None
                min_diff = float('inf')
                
                for fmp_record in fmp_records:
                    fmp_date = fmp_record['fmp_date']
                    
                    try:
                        finviz_dt = datetime.strptime(finviz_date, '%Y-%m-%d')
                        fmp_dt = datetime.strptime(fmp_date, '%Y-%m-%d')
                        
                        diff_days = abs((finviz_dt - fmp_dt).days)
                        
                        if diff_days < min_diff:
                            min_diff = diff_days
                            best_match = fmp_record
                    
                    except ValueError as e:
                        print(f"Date parsing error for {symbol}: {e}")
                        continue
                
                if best_match:
                    result['fmp_date'] = best_match['fmp_date']
                    result['fmp_time'] = best_match['time']
                    result['date_diff_days'] = min_diff
                    result['date_match'] = (min_diff == 0)
                    
                    if min_diff == 0:
                        result['status'] = 'EXACT_MATCH'
                    elif min_diff <= 1:
                        result['status'] = 'CLOSE_MATCH'
                    elif min_diff <= 3:
                        result['status'] = 'MODERATE_DIFF'
                    else:
                        result['status'] = 'LARGE_DIFF'
            
            comparison_results.append(result)
        
        self.comparison_results = comparison_results
        print(f"Completed comparison for {len(comparison_results)} records")

    def generate_accuracy_report(self):
        """精度分析レポートの生成"""
        print("\n" + "="*80)
        print("FMP vs FINVIZ EARNINGS DATE ACCURACY ANALYSIS REPORT")
        print("="*80)
        
        if not self.comparison_results:
            print("No comparison data available")
            return
        
        # 統計計算
        total_comparisons = len(self.comparison_results)
        has_fmp_data = [r for r in self.comparison_results if r['status'] != 'NO_FMP_DATA']
        no_fmp_data = [r for r in self.comparison_results if r['status'] == 'NO_FMP_DATA']
        
        exact_matches = [r for r in self.comparison_results if r['status'] == 'EXACT_MATCH']
        close_matches = [r for r in self.comparison_results if r['status'] == 'CLOSE_MATCH']
        moderate_diffs = [r for r in self.comparison_results if r['status'] == 'MODERATE_DIFF']
        large_diffs = [r for r in self.comparison_results if r['status'] == 'LARGE_DIFF']
        
        print(f"\n📊 SUMMARY STATISTICS")
        print(f"{'─'*50}")
        print(f"Total Finviz records analyzed: {total_comparisons}")
        print(f"Records with FMP data: {len(has_fmp_data)} ({len(has_fmp_data)/total_comparisons*100:.1f}%)")
        print(f"Records without FMP data: {len(no_fmp_data)} ({len(no_fmp_data)/total_comparisons*100:.1f}%)")
        
        if has_fmp_data:
            print(f"\n🎯 ACCURACY ANALYSIS (Among records with FMP data)")
            print(f"{'─'*50}")
            print(f"Exact matches (same date): {len(exact_matches)} ({len(exact_matches)/len(has_fmp_data)*100:.1f}%)")
            print(f"Close matches (±1 day): {len(close_matches)} ({len(close_matches)/len(has_fmp_data)*100:.1f}%)")
            print(f"Moderate differences (2-3 days): {len(moderate_diffs)} ({len(moderate_diffs)/len(has_fmp_data)*100:.1f}%)")
            print(f"Large differences (>3 days): {len(large_diffs)} ({len(large_diffs)/len(has_fmp_data)*100:.1f}%)")
            
            # 総合精度（±1日以内）
            accurate_matches = len(exact_matches) + len(close_matches)
            overall_accuracy = accurate_matches / len(has_fmp_data) * 100
            print(f"\n🏆 OVERALL ACCURACY (±1 day): {overall_accuracy:.1f}%")
            
            # 平均誤差日数
            valid_diffs = [r['date_diff_days'] for r in has_fmp_data if r['date_diff_days'] is not None]
            if valid_diffs:
                avg_diff = np.mean(valid_diffs)
                median_diff = np.median(valid_diffs)
                print(f"Average date difference: {avg_diff:.1f} days")
                print(f"Median date difference: {median_diff:.1f} days")
        
        # 詳細な例を表示
        print(f"\n📋 SAMPLE COMPARISONS")
        print(f"{'─'*80}")
        print(f"{'Symbol':<8} {'Finviz Date':<12} {'FMP Date':<12} {'Diff':<6} {'Status':<15}")
        print(f"{'─'*80}")
        
        # 各カテゴリから例を表示
        sample_examples = []
        if exact_matches:
            sample_examples.extend(exact_matches[:3])
        if close_matches:
            sample_examples.extend(close_matches[:3])
        if moderate_diffs:
            sample_examples.extend(moderate_diffs[:2])
        if large_diffs:
            sample_examples.extend(large_diffs[:2])
        if no_fmp_data:
            sample_examples.extend(no_fmp_data[:2])
        
        for result in sample_examples[:15]:  # 最大15例
            fmp_date = result['fmp_date'] or 'N/A'
            diff_str = str(result['date_diff_days']) + 'd' if result['date_diff_days'] is not None else 'N/A'
            print(f"{result['symbol']:<8} {result['finviz_date']:<12} {fmp_date:<12} {diff_str:<6} {result['status']:<15}")
        
        # CSVファイルに詳細結果を保存
        csv_filename = f"fmp_finviz_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv_path = os.path.join('reports', csv_filename)
        
        # reportsディレクトリが存在しない場合は作成
        os.makedirs('reports', exist_ok=True)
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['symbol', 'company', 'finviz_date', 'finviz_raw', 'fmp_date', 
                         'fmp_time', 'date_match', 'date_diff_days', 'status']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for result in self.comparison_results:
                writer.writerow(result)
        
        print(f"\n💾 Detailed results saved to: {csv_path}")
        
        # 結論
        print(f"\n🔍 CONCLUSION")
        print(f"{'─'*50}")
        if has_fmp_data and overall_accuracy >= 90:
            print(f"✅ FMP shows EXCELLENT accuracy ({overall_accuracy:.1f}%) for earnings dates")
        elif has_fmp_data and overall_accuracy >= 80:
            print(f"✅ FMP shows GOOD accuracy ({overall_accuracy:.1f}%) for earnings dates")  
        elif has_fmp_data and overall_accuracy >= 70:
            print(f"⚠️  FMP shows MODERATE accuracy ({overall_accuracy:.1f}%) for earnings dates")
        elif has_fmp_data:
            print(f"❌ FMP shows LOW accuracy ({overall_accuracy:.1f}%) for earnings dates")
        
        coverage = len(has_fmp_data) / total_comparisons * 100
        if coverage >= 90:
            print(f"✅ FMP shows EXCELLENT coverage ({coverage:.1f}%) of earnings events")
        elif coverage >= 80:
            print(f"✅ FMP shows GOOD coverage ({coverage:.1f}%) of earnings events")
        else:
            print(f"⚠️  FMP shows LIMITED coverage ({coverage:.1f}%) of earnings events")
        
        print(f"{'─'*80}")


def main():
    """メイン実行関数"""
    print("FMP vs Finviz Earnings Date Accuracy Analysis")
    print("=" * 60)
    
    try:
        # 分析クラスの初期化
        analyzer = EarningsDateAccuracyAnalyzer()
        
        # Finvizデータの読み込み
        finviz_file = 'tests/finviz_202507.csv'
        if not os.path.exists(finviz_file):
            print(f"Error: Finviz data file not found: {finviz_file}")
            return
        
        analyzer.load_finviz_data(finviz_file)
        
        # FMPデータの取得（2025年7月1日-25日）
        analyzer.fetch_fmp_data('2025-07-01', '2025-07-25')
        
        # 比較分析の実行
        analyzer.compare_dates()
        
        # 精度レポートの生成
        analyzer.generate_accuracy_report()
        
    except Exception as e:
        print(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()