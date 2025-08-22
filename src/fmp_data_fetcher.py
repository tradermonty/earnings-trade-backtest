#!/usr/bin/env python3
"""
Financial Modeling Prep API Data Fetcher
高精度な決算データを提供するFMP APIクライアント
"""

import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
import time
import json

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FMPDataFetcher:
    """Financial Modeling Prep API クライアント"""
    
    def __init__(self, api_key: str = None):
        """
        FMPDataFetcherの初期化
        
        Args:
            api_key: FMP API キー
        """
        self.api_key = api_key or os.getenv('FMP_API_KEY')
        if not self.api_key:
            raise ValueError("FMP API key is required. Set FMP_API_KEY environment variable.")
        
        # Use v3 as the primary API endpoint (stable endpoints have limited availability)
        self.base_url = "https://financialmodelingprep.com/api/v3"
        self.alt_base_url = "https://financialmodelingprep.com/api/v4"
        self.session = requests.Session()
        
        # Maximum performance rate limiting - 750 calls/minフル活用
        # Starter: 300 calls/min, Premium: 750 calls/min, Ultimate: 3000 calls/min  
        self.rate_limiting_active = False  # 動的制御フラグ
        self.calls_per_minute = 750  # Premium planの最大値（限界まで使用）
        self.calls_per_second = 12.5  # 750/60 = 12.5 calls/sec
        self.call_timestamps = []
        self.last_request_time = datetime(1970, 1, 1)
        self.min_request_interval = 0.08  # 1/12.5 = 0.08秒間隔（理論値）
        self.rate_limit_cooldown_until = datetime(1970, 1, 1)  # 制限解除時刻
        
        # パフォーマンス最適化フラグ
        self.max_performance_mode = True  # 429発生まで制限なし
        
        logger.info("FMP Data Fetcher initialized successfully")
    
    def _rate_limit_check(self):
        """最大パフォーマンス制限チェック - 429発生まで制限を最小限に"""
        now = datetime.now()
        
        # クールダウン期間後の制限解除チェック
        if self.rate_limiting_active and now > self.rate_limit_cooldown_until:
            self.rate_limiting_active = False
            self.max_performance_mode = True
            logger.info("Rate limiting deactivated - returning to maximum performance")
        
        # 429エラー発生時のみ厳格な制限を適用
        if self.rate_limiting_active:
            self.max_performance_mode = False
            # 保守的な制限を適用
            time_since_last = (now - self.last_request_time).total_seconds()
            if time_since_last < 0.2:  # 429発生時は0.2秒間隔
                sleep_time = 0.2 - time_since_last
                logger.warning(f"Conservative rate limiting: sleeping {sleep_time:.3f}s")
                time.sleep(sleep_time)
                now = datetime.now()
                
            # 1分以内のコール履歴をフィルター
            self.call_timestamps = [
                ts for ts in self.call_timestamps 
                if (now - ts).total_seconds() < 60
            ]
            
            # 保守的な1分間制限（300 calls/min）
            if len(self.call_timestamps) >= 300:
                sleep_time = 60 - (now - self.call_timestamps[0]).total_seconds() + 1
                logger.warning(f"Conservative per-minute limit: sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)
                now = datetime.now()
        elif self.max_performance_mode:
            # 最大パフォーマンスモード：429発生まで制限を完全に無効化
            # ネットワーク遅延による自然なレート制限のみ
            pass
        else:
            # 通常モード：理論値まで使用
            time_since_last = (now - self.last_request_time).total_seconds()
            if time_since_last < self.min_request_interval:
                sleep_time = self.min_request_interval - time_since_last
                time.sleep(sleep_time)
                now = datetime.now()
        
        # コール履歴の記録（429エラー時のみ）
        if self.rate_limiting_active:
            self.call_timestamps.append(now)
        
        self.last_request_time = now
    
    def _activate_rate_limiting(self, duration_minutes: int = 5):
        """429エラー発生時にレート制限を有効化"""
        self.rate_limiting_active = True
        self.max_performance_mode = False
        self.rate_limit_cooldown_until = datetime.now() + timedelta(minutes=duration_minutes)
        logger.warning(f"Rate limiting activated for {duration_minutes} minutes due to 429 error")
    
    def _make_request(self, endpoint: str, params: Dict = None, max_retries: int = 3) -> Optional[Dict]:
        """
        FMP APIへのリクエスト実行（リトライと指数バックオフ付き）
        
        Args:
            endpoint: APIエンドポイント
            params: リクエストパラメータ
            max_retries: 最大リトライ回数
        
        Returns:
            APIレスポンス
        """
        if params is None:
            params = {}
        
        params['apikey'] = self.api_key
        url = f"{self.base_url}/{endpoint}"
        
        for attempt in range(max_retries + 1):
            # レート制限チェック（軽微または429エラー後の厳格制限）
            self._rate_limit_check()
            
            try:
                response = self.session.get(url, params=params, timeout=30)
                
                # Handle different HTTP status codes
                if response.status_code == 404:
                    logger.debug(f"Endpoint not found (404): {endpoint}")
                    return None
                elif response.status_code == 403:
                    logger.warning(f"Access forbidden (403) for {endpoint} - check API plan limits")
                    return None
                elif response.status_code == 429:
                    # 429エラー発生時：動的レート制限を有効化
                    self._activate_rate_limiting(duration_minutes=5)
                    
                    if attempt < max_retries:
                        # 指数バックオフ: 2^attempt * 5秒 + ランダムジッター
                        base_delay = 5 * (2 ** attempt)
                        jitter = base_delay * 0.1 * (0.5 - time.time() % 1)  # ±10%のジッター
                        delay = base_delay + jitter
                        
                        logger.warning(f"Rate limit exceeded (429) for {endpoint}. "
                                     f"Activating rate limiting for 5 minutes. "
                                     f"Attempt {attempt + 1}/{max_retries + 1}. "
                                     f"Retrying in {delay:.1f} seconds...")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"Rate limit exceeded (429) for {endpoint}. Max retries exceeded.")
                        return None
                
                response.raise_for_status()
                
                data = response.json()
                
                # Check for empty or invalid responses
                if data is None:
                    logger.debug(f"Empty response from {endpoint}")
                    return None
                elif isinstance(data, dict) and data.get('Error Message'):
                    logger.debug(f"API error for {endpoint}: {data.get('Error Message')}")
                    return None
                elif isinstance(data, list) and len(data) == 0:
                    logger.debug(f"Empty data array from {endpoint}")
                    return None
                
                logger.debug(f"Successfully fetched data from {endpoint}")
                return data
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    delay = 2 ** attempt  # 指数バックオフ
                    logger.warning(f"Request failed for {endpoint}: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                else:
                    logger.debug(f"Request failed for {endpoint} after {max_retries} retries: {e}")
                    return None
            except json.JSONDecodeError as e:
                logger.debug(f"JSON decode error for {endpoint}: {e}")
                return None
        
        return None
    
    def _get_earnings_for_specific_symbols(self, symbols: List[str], from_date: str, to_date: str) -> List[Dict]:
        """
        特定銘柄の決算データを効率的に取得
        
        Args:
            symbols: 銘柄リスト
            from_date: 開始日
            to_date: 終了日
        
        Returns:
            決算データリスト
        """
        all_earnings = []
        
        for symbol in symbols:
            logger.info(f"Fetching earnings for {symbol}")
            
            # まず earnings-surprises エンドポイントを試す
            norm_symbol = self._normalize_symbol(symbol)
            endpoint = f'earnings-surprises/{norm_symbol}'
            params = {'limit': 80}  # 四半期ごとなので80件で約20年分
            
            data = self._make_request(endpoint, params)
            
            if not data:
                # フォールバック1: historical/earning_calendar を試す（v3エンドポイント）
                logger.debug(f"earnings-surprises failed for {symbol}, trying historical/earning_calendar")
                # v3 APIを使用（self.base_urlがv3、self.alt_base_urlがv4）
                original_base = self.base_url
                # Note: base_url is already v3, so no need to change
                endpoint = f'historical/earning_calendar/{norm_symbol}'
                data = self._make_request(endpoint, params)
                # base_url unchanged since we're already on v3
            
            if not data:
                # フォールバック2: v3 earnings APIを試す
                logger.debug(f"historical/earning_calendar failed for {symbol}, trying v3 earnings API")
                # v3 APIを使用（base_urlは既にv3）
                original_base = self.base_url
                # Note: base_url is already v3, so no need to change
                endpoint = f'earnings/{norm_symbol}'
                params = {'limit': 80}
                data = self._make_request(endpoint, params)
                # base_url unchanged since we're already on v3
            
            if data:
                # dataがリストでない場合の処理
                if isinstance(data, dict):
                    data = [data]
                
                # 日付範囲でフィルタリング
                filtered_data = []
                start_dt = datetime.strptime(from_date, '%Y-%m-%d')
                end_dt = datetime.strptime(to_date, '%Y-%m-%d')
                
                for item in data:
                    if 'date' in item:
                        try:
                            item_date = datetime.strptime(item['date'], '%Y-%m-%d')
                            if start_dt <= item_date <= end_dt:
                                # earnings-calendar 形式に変換
                                earnings_item = {
                                    'date': item['date'],
                                    'symbol': symbol,
                                    'epsActual': item.get('actualEarningResult', item.get('eps', item.get('epsActual'))),
                                    'epsEstimate': item.get('estimatedEarning', item.get('epsEstimated', item.get('epsEstimate'))),
                                    'revenue': item.get('revenue'),
                                    'revenueEstimated': item.get('revenueEstimated'),
                                    'time': item.get('time', 'N/A'),
                                    'updatedFromDate': item.get('updatedFromDate', item['date']),
                                    'fiscalDateEnding': item.get('fiscalDateEnding', item['date'])
                                }
                                filtered_data.append(earnings_item)
                        except ValueError as e:
                            logger.debug(f"Date parsing error for {symbol}: {e}")
                
                logger.info(f"Found {len(filtered_data)} earnings records for {symbol} in date range")
                all_earnings.extend(filtered_data)
            else:
                # 最終フォールバック: キャッシュされた決算カレンダーを使用
                logger.warning(f"No direct earnings data found for {symbol}, will use bulk calendar as fallback")
        
        return all_earnings
    
    def get_earnings_surprises(self, symbol: str, limit: int = 80) -> Optional[List[Dict]]:
        """
        特定銘柄の決算サプライズデータを取得
        
        Args:
            symbol: 銘柄シンボル
            limit: 取得件数上限（デフォルト: 80件、約20年分）
        
        Returns:
            決算サプライズデータのリスト、またはNone
        """
        logger.info(f"Fetching earnings surprises for {symbol}")
        
        endpoint = f'earnings-surprises/{self._normalize_symbol(symbol)}'
        params = {'limit': limit}
        
        data = self._make_request(endpoint, params)
        
        if data:
            # データの形式を確認してリストに統一
            if isinstance(data, dict):
                data = [data]
            
            logger.info(f"Retrieved {len(data)} earnings surprise records for {symbol}")
            return data
        else:
            logger.warning(f"No earnings surprise data found for {symbol}")
            return None
    
    def get_earnings_calendar(self, from_date: str, to_date: str, target_symbols: List[str] = None, us_only: bool = True) -> List[Dict]:
        """
        決算カレンダーをBulk取得 (Premium+ plan required)
        90日を超える期間は自動的に分割
        
        Args:
            from_date: 開始日 (YYYY-MM-DD)
            to_date: 終了日 (YYYY-MM-DD)
            target_symbols: 対象銘柄リスト（省略時は全銘柄）
            us_only: アメリカ市場のみに限定するか（デフォルト: True）
        
        Returns:
            決算データリスト
        """
        # 特定銘柄のみの場合は、個別銘柄APIを使用（効率的）
        # 注意: 個別APIは実績値(eps)を返さないため、現在は無効化
        # バルクAPIを常に使用してv3とv4のデータを統合
        if False and target_symbols and len(target_symbols) <= 10:
            logger.info(f"Using individual symbol API for {len(target_symbols)} symbols")
            specific_earnings = self._get_earnings_for_specific_symbols(target_symbols, from_date, to_date)
            
            # 個別APIで取得できなかった銘柄を確認
            found_symbols = set(item['symbol'] for item in specific_earnings)
            missing_symbols = set(target_symbols) - found_symbols
            
            if missing_symbols:
                logger.warning(f"Could not find earnings data for {missing_symbols} via individual API, falling back to bulk calendar")
                # バルクカレンダーにフォールバック（ただし、特定銘柄でフィルタリング）
                # このまま続行して通常のバルク取得を実行
            else:
                # すべての銘柄のデータが取得できた場合は返す
                return specific_earnings
        
        logger.info(f"Fetching earnings calendar from {from_date} to {to_date}")
        
        # 日付をdatetimeオブジェクトに変換
        start_dt = datetime.strptime(from_date, '%Y-%m-%d')
        end_dt = datetime.strptime(to_date, '%Y-%m-%d')
        
        # FMP Premium planの制限チェック（2020年8月以前はデータなし）
        fmp_limit_date = datetime(2020, 8, 1)
        if start_dt < fmp_limit_date:
            error_msg = (
                f"\n{'='*60}\n"
                f"FMP データソース制限エラー\n"
                f"{'='*60}\n"
                f"開始日: {from_date}\n"
                f"FMP Premium plan制限: 2020年8月1日以降のデータのみ利用可能\n\n"
                f"解決策:\n"
                f"1. 開始日を2020-08-01以降に変更\n"
                f"   python main.py --start_date 2020-08-01\n\n"
                f"2. EODHDデータソースを使用（2015年以降対応）\n"
                f"   python main.py --start_date {from_date} --end_date {to_date}\n"
                f"   （--use_fmpオプションを外してEODHDを使用）\n\n"
                f"注意: EODHDは決算日精度が低い（44%）ですが、長期間の分析が可能です\n"
                f"{'='*60}"
            )
            logger.error(error_msg)
            raise ValueError(f"FMP Premium plan does not support data before 2020-08-01. Requested start date: {from_date}")
        
        # 開始日が制限日以降でも、一部が制限範囲に入る場合の警告
        if start_dt < datetime(2020, 9, 1):
            logger.warning(f"Warning: FMP data coverage may be limited for dates close to August 2020. "
                         f"For comprehensive historical analysis, consider using alternative data source.")
        
        # 期間が90日を超える場合は分割
        max_days = 30  # 30日ごとに分割（安全マージン）
        all_data = []
        
        current_start = start_dt
        while current_start < end_dt:
            current_end = min(current_start + timedelta(days=max_days), end_dt)
            
            params = {
                'from': current_start.strftime('%Y-%m-%d'),
                'to': current_end.strftime('%Y-%m-%d')
            }
            
            logger.info(f"Fetching chunk: {params['from']} to {params['to']}")
            
            # v3とv4の両方からデータを取得して統合
            # v3: time フィールドを取得
            # v4: 実績値(eps, revenue)を取得
            
            # v3 API呼び出し（base_urlは既にv3）
            logger.debug(f"Calling v3 API: earning_calendar with params {params}")
            v3_data = self._make_request('earning_calendar', params)  # v3では earning_calendar (単数形)
            logger.debug(f"v3 API response: {len(v3_data) if v3_data else 0} records")
            if v3_data and len(v3_data) > 0:
                logger.debug(f"v3 sample data (first 3): {v3_data[:3]}")
            
            # v4 API呼び出し（実績値取得用）
            original_base = self.base_url
            self.base_url = self.alt_base_url  # v4に切り替え
            logger.debug(f"Calling v4 API: earnings-calendar with params {params}")
            v4_data = self._make_request('earnings-calendar', params)  # v4では earnings-calendar (複数形)
            logger.debug(f"v4 API response: {len(v4_data) if v4_data else 0} records")
            if v4_data and len(v4_data) > 0:
                logger.debug(f"v4 sample data (first 3): {v4_data[:3]}")
            self.base_url = original_base  # v3に戻す
            
            # データ統合: v3をベースにv4のデータで補完
            logger.debug(f"Merging v3 ({len(v3_data) if v3_data else 0}) and v4 ({len(v4_data) if v4_data else 0}) data")
            chunk_data = self._merge_earnings_data(v3_data, v4_data)
            logger.debug(f"Merged result: {len(chunk_data) if chunk_data else 0} records")
            if chunk_data and len(chunk_data) > 0:
                logger.debug(f"Merged sample data (first 3): {chunk_data[:3]}")
            
            
            if chunk_data is None:
                logger.warning(f"Failed to fetch data for {params['from']} to {params['to']}")
            elif len(chunk_data) == 0:
                logger.info(f"No data for {params['from']} to {params['to']}")
            else:
                all_data.extend(chunk_data)
                logger.info(f"Retrieved {len(chunk_data)} records for this chunk")
            
            # 次の期間へ
            current_start = current_end + timedelta(days=1)
            
            # レート制限は_rate_limit_check()で動的に管理
            # チャンク間の固定待機は削除し、最大スピードを確保
        
        if len(all_data) == 0:
            logger.warning("earnings-calendar endpoint returned no data, trying alternative method")
            return self._get_earnings_calendar_alternative(from_date, to_date, target_symbols, us_only)
        
        # 特定銘柄のみ要求されている場合はフィルタリング
        if target_symbols:
            filtered_data = []
            target_set = set(target_symbols)  # 高速検索のためセットに変換
            for item in all_data:
                if item.get('symbol', '') in target_set:
                    filtered_data.append(item)
            
            logger.info(f"Filtered to {len(filtered_data)} records for target symbols: {target_symbols}")
            return filtered_data
        
        # アメリカ市場のみにフィルタリング
        if us_only:
            us_data = []
            for item in all_data:
                symbol = item.get('symbol', '')
                # US市場の銘柄を識別（通常はexchangeShortNameで判定）
                exchange = item.get('exchangeShortName', '').upper()
                if exchange in ['NASDAQ', 'NYSE', 'AMEX', 'NYSE AMERICAN']:
                    us_data.append(item)
                # exchangeShortName情報がない場合は、通常のUS銘柄パターンで判定
                elif exchange == '' and symbol and not any(x in symbol for x in ['.TO', '.L', '.PA', '.AX', '.DE', '.HK']):
                    us_data.append(item)
            
            logger.info(f"Filtered to {len(us_data)} US market earnings records (from {len(all_data)} total)")
            return us_data
        
        logger.info(f"Retrieved total {len(all_data)} earnings records")
        return all_data
    
    def _get_earnings_calendar_alternative(self, from_date: str, to_date: str, 
                                           target_symbols: List[str] = None, us_only: bool = True) -> List[Dict]:
        """
        代替決算カレンダー取得
        個別銘柄のearnings-surprises APIを使用
        
        Args:
            from_date: 開始日
            to_date: 終了日
            target_symbols: 対象銘柄リスト（Noneの場合はデフォルトリスト使用）
        """
        logger.info("Using alternative earnings data collection method")
        
        # Premiumプラン対応：拡張銘柄リスト（主要S&P 500銘柄）
        major_symbols = [
            # Technology
            'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'TSLA', 'NVDA', 'ORCL', 
            'CRM', 'ADBE', 'NFLX', 'INTC', 'AMD', 'AVGO', 'QCOM', 'TXN', 'CSCO',
            
            # Financial
            'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'AXP', 'USB', 'PNC',
            'TFC', 'COF', 'SCHW', 'CB', 'MMC', 'AON', 'SPGI', 'ICE',
            
            # Healthcare
            'JNJ', 'PFE', 'ABT', 'MRK', 'TMO', 'DHR', 'BMY', 'ABBV', 'LLY', 'UNH',
            'CVS', 'AMGN', 'GILD', 'MDLZ', 'BSX', 'SYK', 'ZTS', 'ISRG',
            
            # Consumer Discretionary
            'TSLA', 'AMZN', 'HD', 'MCD', 'NKE', 'SBUX', 'TGT', 'LOW', 'TJX', 'BKNG',
            'CMG', 'ORLY', 'AZO', 'RCL', 'MAR', 'HLT', 'MGM', 'WYNN',
            
            # Consumer Staples
            'KO', 'PEP', 'WMT', 'COST', 'PG', 'CL', 'KMB', 'GIS', 'K', 'SJM',
            'HSY', 'CPB', 'CAG', 'HRL', 'MKC', 'LW', 'CHD',
            
            # Industrial
            'BA', 'CAT', 'GE', 'MMM', 'HON', 'UPS', 'LMT', 'RTX', 'DE', 'FDX',
            'NOC', 'EMR', 'ETN', 'ITW', 'PH', 'CMI', 'OTIS', 'CARR',
            
            # Energy
            'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'PXD', 'OXY', 'VLO', 'MPC', 'PSX',
            'KMI', 'WMB', 'OKE', 'BKR', 'HAL', 'DVN', 'FANG', 'MRO',
            
            # Materials
            'LIN', 'SHW', 'APD', 'ECL', 'FCX', 'NEM', 'DOW', 'DD', 'PPG', 'IFF',
            'ALB', 'CE', 'VMC', 'MLM', 'PKG', 'BALL', 'AMCR',
            
            # Real Estate
            'AMT', 'PLD', 'CCI', 'EQIX', 'PSA', 'WELL', 'DLR', 'O', 'SBAC', 'EQR',
            'AVB', 'VTR', 'ESS', 'MAA', 'EXR', 'UDR', 'CPT',
            
            # Utilities
            'NEE', 'SO', 'DUK', 'AEP', 'SRE', 'D', 'EXC', 'XEL', 'WEC', 'AWK',
            'PPL', 'ES', 'FE', 'ETR', 'AES', 'LNT', 'NI',
            
            # Communication Services
            'META', 'GOOGL', 'GOOG', 'NFLX', 'DIS', 'CMCSA', 'VZ', 'T', 'TMUS',
            'CHTR', 'ATVI', 'EA', 'TTWO', 'NWSA', 'NWS', 'FOXA', 'FOX',
            
            # Mid/Small Cap (includes MANH)
            'MANH', 'POOL', 'ODFL', 'WST', 'MPWR', 'ENPH', 'ALGN', 'MKTX', 'CDAY',
            'PAYC', 'FTNT', 'ANSS', 'CDNS', 'SNPS', 'KLAC', 'LRCX', 'AMAT', 'MCHP'
        ]
        
        earnings_data = []
        start_dt = datetime.strptime(from_date, '%Y-%m-%d')
        end_dt = datetime.strptime(to_date, '%Y-%m-%d')
        
        for symbol in major_symbols:
            try:
                # Earnings surprises API (available in Starter)
                symbol_data = self._make_request(f'earnings-surprises/{symbol}')
                
                if symbol_data and isinstance(symbol_data, list):
                    for earning in symbol_data:
                        try:
                            earning_date = datetime.strptime(earning.get('date', ''), '%Y-%m-%d')
                            if start_dt <= earning_date <= end_dt:
                                # Convert to earnings-calendar format
                                converted = {
                                    'symbol': symbol,
                                    'date': earning.get('date'),
                                    'epsActual': earning.get('actualEarningResult'),
                                    'epsEstimated': earning.get('estimatedEarning'),  # Fixed: use 'epsEstimated' instead of 'epsEstimate'
                                    'time': None,  # Not available in Starter
                                    'revenueActual': None,  # Not available in earnings-surprises
                                    'revenueEstimate': None,  # Not available in earnings-surprises
                                    'fiscalDateEnding': earning.get('date'),
                                    'updatedFromDate': earning.get('date')
                                }
                                earnings_data.append(converted)
                                logger.debug(f"Added {symbol} earnings for {earning.get('date')}")
                        except (ValueError, TypeError) as e:
                            logger.debug(f"Date parsing error for {symbol}: {e}")
                            continue
                            
            except Exception as e:
                logger.warning(f"Failed to get earnings for {symbol}: {e}")
                continue
        
        # アメリカ市場のみにフィルタリング（代替メソッド用）
        if us_only:
            us_earnings = []
            for earning in earnings_data:
                symbol = earning.get('symbol', '')
                # アメリカ市場の銘柄（S&P銘柄等）のみを対象
                if symbol and not any(x in symbol for x in ['.TO', '.L', '.PA', '.AX', '.DE', '.HK']):
                    us_earnings.append(earning)
            earnings_data = us_earnings
            logger.info(f"Filtered to {len(earnings_data)} US market earnings records using alternative method")
        
        # Sort by date
        earnings_data.sort(key=lambda x: x.get('date', ''))
        logger.info(f"Retrieved {len(earnings_data)} earnings records using alternative method")
        
        return earnings_data
    
    
    
    def get_company_profile(self, symbol: str) -> Optional[Dict]:
        """
        企業プロファイル取得
        
        Args:
            symbol: 銘柄コード
        
        Returns:
            企業情報
        """
        logger.debug(f"Fetching company profile for {symbol}")
        
        # Try different endpoints - profile data is only available on v3 API
        norm_symbol = self._normalize_symbol(symbol)
        endpoints_to_try = [
            ('v3', f'profile/{norm_symbol}'),      # v3 endpoint (primary)
            ('v4', f'profile/{norm_symbol}'),      # v4 endpoint (backup)
        ]
        
        data = None
        for api_version, endpoint in endpoints_to_try:
            base_url = self.base_url if api_version == 'v3' else self.alt_base_url
            logger.debug(f"Trying {api_version} endpoint for profile: {endpoint}")
            
            # Temporarily override base URL for this request
            original_base_url = self.base_url
            self.base_url = base_url
            
            data = self._make_request(endpoint)
            
            # Restore original base URL
            self.base_url = original_base_url
            
            if data is not None:
                logger.debug(f"Successfully fetched profile using: {api_version}/{endpoint}")
                break
            else:
                logger.debug(f"Profile endpoint failed: {api_version}/{endpoint}")
        
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]
        
        logger.warning(f"Failed to fetch company profile for {symbol} using all available endpoints")
        return None
    
    def process_earnings_data(self, earnings_data: List[Dict]) -> pd.DataFrame:
        """
        FMP決算データを標準形式に変換
        
        Args:
            earnings_data: FMP決算データ
        
        Returns:
            標準化されたDataFrame
        """
        if not earnings_data:
            return pd.DataFrame()
        
        logger.debug(f"process_earnings_data called with {len(earnings_data)} records")
        if earnings_data:
            logger.debug(f"First 3 raw earnings data: {earnings_data[:3]}")
        
        processed_data = []
        
        for i, earning in enumerate(earnings_data):
            try:
                if i < 5:  # 最初の5件をデバッグ出力
                    logger.debug(f"Processing earning {i}: {earning}")
                
                # FMPデータ構造に基づく処理
                processed_earning = {
                    'code': earning.get('symbol', '') + '.US',  # .US suffix for compatibility
                    'report_date': earning.get('date', ''),
                    'date': earning.get('date', ''),  # 実際の決算日
                    'before_after_market': self._parse_timing(earning.get('time', '')),
                    'currency': 'USD',  # FMPは主にUSDデータ
                    'actual': self._safe_float(earning.get('eps')),  # 修正: epsActual → eps
                    'estimate': self._safe_float(earning.get('epsEstimated')),  # FMP uses 'epsEstimated'
                    'difference': 0,  # 後で計算
                    'percent': 0,     # 後で計算
                    'revenue_actual': self._safe_float(earning.get('revenue')),  # 修正: revenueActual → revenue
                    'revenue_estimate': self._safe_float(earning.get('revenueEstimated')),
                    'updated_from_date': earning.get('updatedFromDate', ''),
                    'fiscal_date_ending': earning.get('fiscalDateEnding', ''),
                    'data_source': 'FMP'
                }
                
                if i < 5:
                    logger.debug(f"Processed earning {i} - actual: {processed_earning['actual']}, estimate: {processed_earning['estimate']}")
                
                # サプライズ率計算
                if processed_earning['actual'] is not None and processed_earning['estimate'] is not None:
                    if processed_earning['estimate'] != 0:
                        processed_earning['difference'] = processed_earning['actual'] - processed_earning['estimate']
                        processed_earning['percent'] = (processed_earning['difference'] / abs(processed_earning['estimate'])) * 100
                        if i < 5:
                            logger.debug(f"Calculated percent for {i}: {processed_earning['percent']}%")
                else:
                    if i < 5:
                        logger.debug(f"Could not calculate percent for {i} - actual: {processed_earning['actual']}, estimate: {processed_earning['estimate']}")
                
                processed_data.append(processed_earning)
                
            except Exception as e:
                logger.warning(f"Error processing earning data {i}: {e}")
                continue
        
        df = pd.DataFrame(processed_data)
        
        if not df.empty:
            # 日付でソート
            df = df.sort_values('report_date')
            logger.debug(f"Final processed DataFrame: {len(df)} records")
            logger.debug(f"Sample processed data: {df.head(3).to_dict('records')}")
        
        return df
    
    def _merge_earnings_data(self, v3_data: Optional[List[Dict]], v4_data: Optional[List[Dict]]) -> Optional[List[Dict]]:
        """
        v3とv4のデータを統合
        v3: timeフィールドを持つ
        v4: 実績値を持つ場合がある
        
        Args:
            v3_data: v3 APIのデータ
            v4_data: v4 APIのデータ
            
        Returns:
            統合されたデータ
        """
        logger.debug(f"_merge_earnings_data called with v3_data={len(v3_data) if v3_data else 0}, v4_data={len(v4_data) if v4_data else 0}")
        
        # v3データがない場合はv4を返す
        if not v3_data:
            logger.debug("v3 API returned no data, using v4 data only")
            if v4_data:
                logger.debug(f"Returning v4 data sample: {v4_data[:2]}")
            return v4_data
        
        # v4データがない場合はv3を返す
        if not v4_data:
            logger.debug("v4 API returned no data, using v3 data only")
            if v3_data:
                logger.debug(f"Returning v3 data sample: {v3_data[:2]}")
            return v3_data
        
        # v4データを辞書に変換（高速検索用）
        v4_dict = {}
        for i, item in enumerate(v4_data):
            key = (item.get('symbol', ''), item.get('date', ''))
            v4_dict[key] = item
            if i < 3:  # 最初の3件をデバッグ出力
                logger.debug(f"v4_dict key={key}, item fields: {list(item.keys())}")
        
        # v3データをベースに、v4のデータで補完
        merged_data = []
        for i, v3_item in enumerate(v3_data):
            symbol = v3_item.get('symbol', '')
            date = v3_item.get('date', '')
            key = (symbol, date)
            
            # v3データをコピー
            merged_item = v3_item.copy()
            
            if i < 3:  # 最初の3件をデバッグ出力
                logger.debug(f"Processing v3 item {i}: symbol={symbol}, date={date}, fields: {list(v3_item.keys())}")
                logger.debug(f"v3 item values: {v3_item}")
            
            # v4データが存在する場合、実績値を上書き
            if key in v4_dict:
                v4_item = v4_dict[key]
                if i < 3:
                    logger.debug(f"Found matching v4 data for {key}: {v4_item}")
                
                # v4の実績値でv3を更新（v4にある場合のみ）
                if v4_item.get('eps') is not None:
                    merged_item['eps'] = v4_item['eps']
                    if i < 3:
                        logger.debug(f"Updated eps from v4: {v4_item['eps']}")
                if v4_item.get('revenue') is not None:
                    merged_item['revenue'] = v4_item['revenue']
                    if i < 3:
                        logger.debug(f"Updated revenue from v4: {v4_item['revenue']}")
                # その他の有用なフィールドも更新
                if v4_item.get('epsActual') is not None:
                    merged_item['epsActual'] = v4_item['epsActual']
                    if i < 3:
                        logger.debug(f"Updated epsActual from v4: {v4_item['epsActual']}")
                if v4_item.get('revenueActual') is not None:
                    merged_item['revenueActual'] = v4_item['revenueActual']
                    if i < 3:
                        logger.debug(f"Updated revenueActual from v4: {v4_item['revenueActual']}")
            else:
                if i < 3:
                    logger.debug(f"No matching v4 data found for {key}")
            
            if i < 3:
                logger.debug(f"Final merged item {i}: {merged_item}")
            
            merged_data.append(merged_item)
        
        logger.debug(f"Merged {len(merged_data)} records (v3: {len(v3_data)}, v4: {len(v4_data)})")
        return merged_data
    
    def _parse_timing(self, time_str: str) -> str:
        """
        FMPの時間情報をBefore/AfterMarket形式に変換
        
        Args:
            time_str: FMP時間文字列
        
        Returns:
            Before/AfterMarket
        """
        if not time_str:
            return None
        
        time_lower = time_str.lower()
        
        if any(keyword in time_lower for keyword in ['before', 'pre', 'bmo']):
            return 'BeforeMarket'
        elif any(keyword in time_lower for keyword in ['after', 'post', 'amc']):
            return 'AfterMarket'
        else:
            return None
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """
        安全なfloat変換
        
        Args:
            value: 変換対象値
        
        Returns:
            float値またはNone
        """
        if value is None or value == '':
            return None
        
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    # --- 追加: シンボル正規化ユーティリティ ------------------------------
    def _normalize_symbol(self, symbol: str) -> str:
        """API が要求する形式にシンボルを正規化する

        例: "BRK.B" → "BRK-B"

        Args:
            symbol: 元のシンボル文字列

        Returns:
            正規化済みシンボル
        """
        if symbol is None:
            return symbol
        # FMP では複数株式クラスをハイフン区切りで表記するため
        return symbol.replace('.', '-')
    
    def get_historical_price_data(self, symbol: str, from_date: str, to_date: str) -> Optional[List[Dict]]:
        """
        FMPから株価履歴データを取得
        
        Args:
            symbol: 銘柄コード（例: "AAPL"）
            from_date: 開始日 (YYYY-MM-DD)
            to_date: 終了日 (YYYY-MM-DD)
        
        Returns:
            株価データリスト
        """
        logger.debug(f"Fetching historical price data for {symbol} from {from_date} to {to_date}")
        
        # Try different endpoint formats and base URLs for FMP
        normalized_symbol = self._normalize_symbol(symbol)
        endpoints_to_try = [
            # API v3 endpoints (correct endpoints for historical data)
            ('v3', f'historical-price-full/{normalized_symbol}'),
            ('v3', f'historical-chart/1day/{normalized_symbol}'),
            ('v3', f'historical-daily-prices/{normalized_symbol}'),
        ]
        
        params = {
            'from': from_date,
            'to': to_date
        }
        
        data = None
        successful_endpoint = None
        
        for api_version, endpoint in endpoints_to_try:
            base_url = self.base_url if api_version == 'v3' else self.alt_base_url
            logger.debug(f"Trying {api_version} endpoint: {endpoint}")
            
            # Temporarily override base URL for this request
            original_base_url = self.base_url
            self.base_url = base_url
            
            # 最大パフォーマンスで実行
            data = self._make_request(endpoint, params, max_retries=3)
            
            # Restore original base URL
            self.base_url = original_base_url
            
            if data is not None:
                successful_endpoint = f"{api_version}/{endpoint}"
                logger.debug(f"Successfully fetched data using: {successful_endpoint}")
                break
            else:
                logger.debug(f"Endpoint failed: {api_version}/{endpoint}")
                # エンドポイント間の固定待機を削除（動的制限で管理）
        
        if data is None:
            logger.warning(f"Failed to fetch historical price data for {symbol} using all available endpoints")
            return None
        
        # Handle different response formats
        if isinstance(data, dict):
            # Standard format with 'historical' field
            if 'historical' in data:
                return data['historical']
            # Alternative format with direct data
            elif 'results' in data:
                return data['results']
            # Chart format
            elif isinstance(data, dict) and 'date' in str(data):
                return [data]
        elif isinstance(data, list):
            # Direct list format
            return data
        
        logger.warning(f"Unexpected data format for {symbol}: {type(data)}")
        return None
    
    def get_sp500_constituents(self) -> List[str]:
        """
        S&P 500構成銘柄を取得
        
        Returns:
            銘柄コードリスト
        """
        logger.debug("Fetching S&P 500 constituents")
        
        data = self._make_request('sp500_constituent')
        
        if data is None:
            logger.warning("Failed to fetch S&P 500 constituents")
            return []
        
        # Extract symbols from constituent data
        symbols = []
        if isinstance(data, list):
            symbols = [item.get('symbol', '') for item in data if item.get('symbol')]
        
        logger.info(f"Retrieved {len(symbols)} S&P 500 symbols")
        return symbols
    
    
    
    
    def get_mid_small_cap_symbols(self, min_market_cap: float = 1e9, max_market_cap: float = 50e9) -> List[str]:
        """
        時価総額ベースで中小型株を取得
        
        Args:
            min_market_cap: 最小時価総額（デフォルト: $1B）
            max_market_cap: 最大時価総額（デフォルト: $50B）
        
        Returns:
            中小型株の銘柄コードリスト
        """
        logger.info(f"Fetching mid/small cap stocks (${min_market_cap/1e9:.1f}B - ${max_market_cap/1e9:.1f}B)")
        
        # FMPのstock screenerを使用
        params = {
            'marketCapMoreThan': int(min_market_cap),
            'marketCapLowerThan': int(max_market_cap),
            'limit': 3000  # 大きめの制限を設定
        }
        
        # Try different endpoints
        endpoints_to_try = [
            'stock_screener',  # 正しいエンドポイント名
            'screener',        # 代替エンドポイント 
            'stock-screener'   # 元のエンドポイント
        ]
        
        data = None
        for endpoint in endpoints_to_try:
            data = self._make_request(endpoint, params)
            if data is not None:
                logger.debug(f"Successfully used endpoint: {endpoint}")
                break
        
        if data is None:
            logger.warning("Stock screener API not available, using fallback method")
            # Fallback: Use market cap filtering in earnings data processing
            return self._get_mid_small_cap_fallback(min_market_cap, max_market_cap)
        
        # US市場の銘柄のみを抽出
        us_symbols = []
        if isinstance(data, list):
            for stock in data:
                symbol = stock.get('symbol', '')
                exchange = stock.get('exchangeShortName', '')
                country = stock.get('country', '')
                
                # US市場の銘柄のみを選択
                if (exchange in ['NASDAQ', 'NYSE', 'AMEX'] or country == 'US') and symbol:
                    # 一般的でない銘柄タイプを除外
                    if not any(x in symbol for x in ['.', '-', '^', '=']):
                        us_symbols.append(symbol)
        
        logger.info(f"Retrieved {len(us_symbols)} mid/small cap US stocks")
        return us_symbols[:2000]  # 実用的な数に制限
    
    def _get_mid_small_cap_fallback(self, min_market_cap: float, max_market_cap: float) -> List[str]:
        """
        Stock screenerが利用できない場合の代替手段
        人気のある中小型株リストを使用
        """
        logger.info("Using curated mid/small cap stock list as fallback")
        
        # 中小型株として人気の銘柄リスト（時価総額範囲に適合するもの）
        mid_small_cap_stocks = [
            # Regional Banks (typically $2-20B market cap)
            'OZK', 'ZION', 'PNFP', 'FHN', 'SNV', 'FULT', 'CBSH', 'ONB', 'IBKR',
            'BKU', 'OFG', 'FFBC', 'COLB', 'BANC', 'FFIN', 'FBP', 'CUBI', 'ASB',
            'HFWA', 'PPBI', 'SSB', 'TCBI', 'NBHC', 'BANR', 'CVBF', 'UMBF',
            'LKFN', 'NWBI', 'HOPE', 'SBCF', 'WSFS', 'SFBS', 'HAFC', 'FBNC',
            'CFFN', 'ABCB', 'BHLB', 'STBA',
            
            # Mid-cap industrials and tech
            'CALM', 'AIR', 'AZZ', 'JEF', 'ACI', 'MSM', 'SMPL', 'GBX', 'UNF',
            'NEOG', 'WDFC', 'CNXC', 'IIIN', 'WBS', 'HWC', 'PRGS', 'AGYS',
            'AA', 'ALK', 'SLG', 'PLXS', 'SFNC', 'KNX', 'MANH', 'QRVO', 'WRLD',
            'ADNT', 'TRMK', 'NXT', 'AIT', 'VFC', 'SF', 'EXTR', 'WHR', 'GPI',
            'CCS', 'CALX', 'CPF', 'CACI', 'GATX', 'ORI', 'HZO', 'MRTN', 'SANM',
            'ELS', 'HLI', 'RNR', 'RNST', 'CVLT', 'FLEX', 'NFG', 'LBRT', 'VIRT',
            'DLB', 'BHE', 'OSK', 'VIAV', 'ATGE', 'BC', 'SXI', 'OLN', 'PMT',
            'SXC', 'DT', 'CRS', 'ABG', 'NTCT', 'CFR', 'CVCO', 'STEL', 'HTH',
            'SKYW', 'CSWI', 'FHI', 'BOOT', 'BFH', 'ALGM', 'TMP', 'ALV', 'VSTS',
            'RBC', 'JHG', 'ARCB', 'PIPR', 'CR', 'NLY', 'EAT'
        ]
        
        logger.info(f"Using {len(mid_small_cap_stocks)} curated mid/small cap symbols")
        return mid_small_cap_stocks
    
    def get_api_usage_stats(self) -> Dict:
        """
        API使用統計を取得
        
        Returns:
            使用統計情報
        """
        now = datetime.now()
        recent_calls_minute = [
            ts for ts in self.call_timestamps 
            if (now - ts).total_seconds() < 60
        ]
        recent_calls_second = [
            ts for ts in self.call_timestamps 
            if (now - ts).total_seconds() < 1
        ]
        
        return {
            'calls_last_minute': len(recent_calls_minute),
            'calls_last_second': len(recent_calls_second),
            'calls_per_minute_limit': self.calls_per_minute,
            'calls_per_second_limit': self.calls_per_second,
            'remaining_calls_minute': max(0, self.calls_per_minute - len(recent_calls_minute)),
            'remaining_calls_second': max(0, self.calls_per_second - len(recent_calls_second)),
            'api_key_set': bool(self.api_key),
            'base_url': self.base_url,
            'min_request_interval': self.min_request_interval
        }

    def stock_screener(self, price_more_than: float = 10, market_cap_more_than: float = 1e9,
                       market_cap_less_than: Optional[float] = None,
                       volume_more_than: Optional[int] = None,  # Volume filtering is intentionally ignored in this stage
                       limit: int = 5000, exchange: Optional[str] = None) -> List[str]:
        """指定条件でFMPストックスクリーナーを実行し、銘柄シンボルのリストを返す

        Args:
            price_more_than: 株価下限（デフォルト: $10）
            market_cap_more_than: 時価総額下限（デフォルト: $1B）
            volume_more_than: 平均出来高下限（**第2段階でフィルタリングするため、この関数では使用しない**）
            limit: 取得件数上限（デフォルト: 5000）
            exchange: 取引所を限定する場合に指定（'NASDAQ' など）

        Returns:
            条件を満たす銘柄シンボルのリスト
        """
        logger.info(
            f"Running stock screener (price >= ${price_more_than}, marketCap >= {market_cap_more_than}) "
            f"[volume filter deferred]")

        params = {
            'priceMoreThan': price_more_than,
            'marketCapMoreThan': int(market_cap_more_than),
            'limit': limit,
            # 追加フィルタリング
            'country': 'US',             # 米国企業のみ（パラメータは "US"）
            'isEtf': 'false',            # ETF除外
            'isFund': 'false',           # Fund除外
            'isActivelyTrading': 'true', # 取引停止銘柄除外
            'includeAllShareClasses': 'false'
        }


        # 第1段階では出来高フィルタを適用しない方針
        # volumeMoreThan パラメータは使用せず、必要に応じて呼び出し側で後段フィルタをかける

        if market_cap_less_than is not None and market_cap_less_than < 1e12:
            params['marketCapLowerThan'] = int(market_cap_less_than)
        if exchange:
            params['exchange'] = exchange

        # エンドポイント候補。v3/v4で名称が異なることがある
        endpoints = [
            'stock-screener',     # 推奨（v3）
            'stock_screener',     # v3 の別名
            'stock-screener',     # ハイフン形式
            'screener'            # 古い形式
        ]

        data = None
        for ep in endpoints:
            data = self._make_request(ep, params)
            if data is not None:
                logger.debug(f"Stock screener succeeded with endpoint: {ep}")
                break
        if data is None:
            logger.warning("Stock screener API not available or returned no data")
            return []

        symbols: List[str] = []
        if isinstance(data, list):
            for item in data:
                symbol = item.get('symbol')
                exch = item.get('exchangeShortName', '')
                country = item.get('country', '')

                # 米国市場を優先
                if exchange:
                    allowed_market = exch == exchange
                else:
                    allowed_market = exch in ['NASDAQ', 'NYSE', 'AMEX'] or country == 'US'

                if symbol and allowed_market:
                    # ETF / Fund は除外
                    if item.get('isEtf') or item.get('isFund'):
                        continue
                    # 不要な特殊ティッカーを除外（指数・先物など）
                    if not any(x in symbol for x in ['^', '=']):
                        symbols.append(symbol)

        logger.info(f"Stock screener retrieved {len(symbols)} symbols")
        return symbols

    # -------------------------------------------------------------------------
    # Financial Ratios helpers
    # -------------------------------------------------------------------------
    def get_latest_financial_ratios(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return latest financial ratios for a given symbol (most recent period).

        Uses endpoint `/v3/ratios` with `symbol` and `limit=1`.
        Returns None when API fails or data missing.
        """
        params = {
            'symbol': symbol.upper(),
            'limit': 1,
        }
        data = self._make_request('ratios', params)
        if not data or not isinstance(data, list):
            return None
        return data[0]

    # -------------------------------------------------------------------------
    # Intraday pre-market helpers
    # -------------------------------------------------------------------------
    def get_preopen_price(self, symbol: str, trade_date: str, pre_open_time: str = "09:25:00") -> Optional[float]:
        """Return the price at pre-open time (default 09:25 ET) for given trade_date using 1-min intraday data.
        Requires Premium API (date filter). Returns None if data not available.
        """
        endpoint = f"historical-chart/1min/{symbol.upper()}"
        params = {
            'from': trade_date,
            'to': trade_date,
            'prepost': 'true',
        }
        data = self._make_request(endpoint, params)
        if not data or not isinstance(data, list):
            logger.debug(f"Intraday API returned no data for {symbol} {trade_date}")
            return None
        logger.debug(f"Intraday rows for {symbol} {trade_date}: {len(data)}")
        target_prefix = f"{trade_date} {pre_open_time}"
        for item in data:
            if item.get('date', '').startswith(target_prefix):
                try:
                    return float(item['open'])
                except (TypeError, ValueError):
                    return None
        # fallback: last 09:2x record
        candidates = [item for item in data if item.get('date', '').startswith(f"{trade_date} 09:2")]
        if not candidates:
            logger.debug(f"No 09:2x records for {symbol} {trade_date}. First times: {[i['date'] for i in data[:3]]}")
            return None
        try:
            return float(candidates[-1]['open'])
        except (TypeError, ValueError):
            return None

