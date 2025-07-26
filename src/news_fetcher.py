#!/usr/bin/env python3
"""
ニュースデータ取得モジュール
"""

import requests
import time
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NewsFetcher:
    """ニュースデータ取得クラス"""
    
    def __init__(self, api_key: str, cache_dir: str = "cache/news"):
        """
        NewsFetcherの初期化
        
        Args:
            api_key: EODHD API Key
            cache_dir: キャッシュディレクトリパス
        """
        self.api_key = api_key
        self.base_url = "https://eodhistoricaldata.com/api/news"
        self.cache_dir = cache_dir
        self.rate_limit_delay = 0.1  # API制限対応（100ms間隔）
        
        # キャッシュディレクトリを作成
        os.makedirs(cache_dir, exist_ok=True)
    
    def fetch_news(self, symbol: str, start_date: str, end_date: str, 
                   use_cache: bool = True) -> List[Dict]:
        """
        指定期間のニュースを取得
        
        Args:
            symbol: 銘柄コード（例: "AAPL"）
            start_date: 開始日（YYYY-MM-DD）
            end_date: 終了日（YYYY-MM-DD）
            use_cache: キャッシュを使用するか
        
        Returns:
            ニュース記事のリスト
        """
        try:
            # キャッシュファイルパス
            cache_file = os.path.join(
                self.cache_dir, 
                f"{symbol}_{start_date}_{end_date}.json"
            )
            
            # キャッシュから読み込み
            if use_cache and os.path.exists(cache_file):
                logger.info(f"Loading cached news for {symbol} ({start_date} to {end_date})")
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            logger.info(f"Fetching news for {symbol} from {start_date} to {end_date}")
            
            # APIパラメータ
            params = {
                'api_token': self.api_key,
                's': f"{symbol}.US",
                'from': start_date,
                'to': end_date,
                'limit': 100,
                'fmt': 'json'
            }
            
            # API呼び出し
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            # レスポンス解析
            data = response.json()
            
            # データ形式の確認と正規化
            if isinstance(data, list):
                news_list = data
            elif isinstance(data, dict) and 'data' in data:
                news_list = data['data']
            else:
                logger.warning(f"Unexpected API response format for {symbol}")
                news_list = []
            
            # キャッシュに保存
            if use_cache and news_list:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(news_list, f, indent=2, ensure_ascii=False)
                logger.info(f"Cached {len(news_list)} news articles for {symbol}")
            
            # レート制限対応
            time.sleep(self.rate_limit_delay)
            
            return news_list
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {symbol}: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {symbol}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching news for {symbol}: {e}")
            return []
    
    def fetch_earnings_period_news(self, symbol: str, earnings_date: str,
                                   days_before: int = 3, days_after: int = 3,
                                   use_cache: bool = True) -> List[Dict]:
        """
        決算日前後の期間のニュースを取得
        
        Args:
            symbol: 銘柄コード
            earnings_date: 決算日（YYYY-MM-DD）
            days_before: 決算日前の日数
            days_after: 決算日後の日数
            use_cache: キャッシュを使用するか
        
        Returns:
            ニュース記事のリスト
        """
        try:
            base_date = datetime.strptime(earnings_date, '%Y-%m-%d')
            start_date = (base_date - timedelta(days=days_before)).strftime('%Y-%m-%d')
            end_date = (base_date + timedelta(days=days_after)).strftime('%Y-%m-%d')
            
            return self.fetch_news(symbol, start_date, end_date, use_cache)
            
        except ValueError as e:
            logger.error(f"Invalid date format for {symbol}: {earnings_date}")
            return []
    
    def clear_cache(self, symbol: str = None):
        """
        キャッシュをクリア
        
        Args:
            symbol: 特定銘柄のキャッシュのみクリア（Noneの場合は全て）
        """
        try:
            if symbol:
                # 特定銘柄のキャッシュファイルを削除
                for filename in os.listdir(self.cache_dir):
                    if filename.startswith(f"{symbol}_") and filename.endswith('.json'):
                        file_path = os.path.join(self.cache_dir, filename)
                        os.remove(file_path)
                        logger.info(f"Removed cache file: {filename}")
            else:
                # 全キャッシュを削除
                for filename in os.listdir(self.cache_dir):
                    if filename.endswith('.json'):
                        file_path = os.path.join(self.cache_dir, filename)
                        os.remove(file_path)
                        logger.info(f"Removed cache file: {filename}")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
    
    def get_cache_info(self) -> Dict:
        """
        キャッシュ情報を取得
        
        Returns:
            キャッシュファイル数と総サイズ
        """
        try:
            cache_files = [f for f in os.listdir(self.cache_dir) if f.endswith('.json')]
            total_size = sum(
                os.path.getsize(os.path.join(self.cache_dir, f)) 
                for f in cache_files
            )
            
            return {
                'file_count': len(cache_files),
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'cache_dir': self.cache_dir
            }
        except Exception as e:
            logger.error(f"Error getting cache info: {e}")
            return {'file_count': 0, 'total_size_mb': 0, 'cache_dir': self.cache_dir}