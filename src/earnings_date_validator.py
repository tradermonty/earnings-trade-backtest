#!/usr/bin/env python3
"""
決算日検証モジュール
"""

import json
import re
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from collections import defaultdict

from .news_fetcher import NewsFetcher

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EarningsDateValidator:
    """決算日検証クラス"""
    
    def __init__(self, news_fetcher: NewsFetcher, keywords_file: str = None):
        """
        EarningsDateValidatorの初期化
        
        Args:
            news_fetcher: NewsFetcherインスタンス
            keywords_file: キーワード設定ファイルパス
        """
        self.news_fetcher = news_fetcher
        self.keywords_config = self._load_keywords(keywords_file)
        
        # 日付パターンの正規表現をコンパイル
        self._compile_date_patterns()
        
        # 統計情報
        self.validation_stats = defaultdict(int)
    
    def _load_keywords(self, keywords_file: str = None) -> Dict:
        """キーワード設定を読み込み"""
        if keywords_file is None:
            keywords_file = os.path.join(
                os.path.dirname(__file__), '..', 'config', 'news_keywords.json'
            )
        
        try:
            with open(keywords_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Keywords file not found: {keywords_file}")
            # デフォルト設定
            return {
                "earnings_keywords": {
                    "primary": ["earnings report", "quarterly results"],
                    "secondary": ["revenue", "profit", "EPS"],
                    "date_patterns": ["reported on", "announced on"]
                },
                "scoring": {"primary_weight": 1.0, "secondary_weight": 0.5},
                "confidence_thresholds": {"high": 0.8, "medium": 0.6, "low": 0.4}
            }
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing keywords file: {e}")
            return {}
    
    def _compile_date_patterns(self):
        """日付抽出用の正規表現パターンをコンパイル"""
        # 一般的な日付フォーマット
        self.date_patterns = [
            r'\b(\d{4}-\d{2}-\d{2})\b',  # YYYY-MM-DD
            r'\b(\d{1,2}/\d{1,2}/\d{4})\b',  # MM/DD/YYYY
            r'\b(\d{1,2}-\d{1,2}-\d{4})\b',  # MM-DD-YYYY
            r'\b([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b',  # Month DD, YYYY
            r'\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b',  # DD Month YYYY
        ]
        
        # 相対日付パターン
        self.relative_patterns = [
            r'\b(today|yesterday|tomorrow)\b',
            r'\b(this\s+(?:monday|tuesday|wednesday|thursday|friday))\b',
            r'\b(last\s+(?:monday|tuesday|wednesday|thursday|friday))\b',
        ]
        
        # コンパイル済み正規表現
        self.compiled_date_patterns = [re.compile(p, re.IGNORECASE) for p in self.date_patterns]
        self.compiled_relative_patterns = [re.compile(p, re.IGNORECASE) for p in self.relative_patterns]
    
    def validate_earnings_date(self, symbol: str, eodhd_date: str) -> Dict:
        """
        EODHDの決算日を検証し、実際の決算日を特定
        
        Args:
            symbol: 銘柄コード
            eodhd_date: EODHDが示す決算日（YYYY-MM-DD）
        
        Returns:
            検証結果辞書
        """
        logger.info(f"Validating earnings date for {symbol}: EODHD={eodhd_date}")
        
        try:
            # 前後1週間のニュースを取得
            news_articles = self.news_fetcher.fetch_earnings_period_news(
                symbol, eodhd_date, days_before=7, days_after=7
            )
            
            logger.info(f"Found {len(news_articles)} news articles for {symbol}")
            self.validation_stats['total_articles'] += len(news_articles)
            
            if not news_articles:
                logger.warning(f"No news articles found for {symbol}")
                return self._create_validation_result(
                    symbol, eodhd_date, eodhd_date, 0.0, []
                )
            
            # ニュース記事を分析
            earnings_evidence = []
            for article in news_articles:
                analysis = self._analyze_news_article(article, eodhd_date)
                if analysis['earnings_score'] > 0:
                    earnings_evidence.append(analysis)
            
            logger.info(f"Found {len(earnings_evidence)} earnings-related articles for {symbol}")
            
            if not earnings_evidence:
                logger.warning(f"No earnings-related articles found for {symbol}")
                return self._create_validation_result(
                    symbol, eodhd_date, eodhd_date, 0.0, []
                )
            
            # 最も信頼性の高い日付を特定
            actual_date, confidence = self._determine_actual_date(
                earnings_evidence, eodhd_date
            )
            
            # 統計情報更新
            self.validation_stats['validated_stocks'] += 1
            if actual_date != eodhd_date:
                self.validation_stats['date_corrections'] += 1
            
            result = self._create_validation_result(
                symbol, eodhd_date, actual_date, confidence, earnings_evidence
            )
            
            logger.info(f"Validation complete for {symbol}: actual_date={actual_date}, confidence={confidence:.2f}")
            return result
            
        except Exception as e:
            logger.error(f"Error validating earnings date for {symbol}: {e}")
            return self._create_validation_result(
                symbol, eodhd_date, eodhd_date, 0.0, []
            )
    
    def _analyze_news_article(self, article: Dict, reference_date: str) -> Dict:
        """
        ニュース記事を分析して決算関連度を判定
        
        Args:
            article: ニュース記事データ
            reference_date: 参照日（EODHD決算日）
        
        Returns:
            分析結果辞書
        """
        try:
            title = article.get('title', '').lower()
            content = article.get('content', '').lower()
            date = article.get('date', '')
            
            # 決算関連キーワードのスコア計算
            earnings_score = self._calculate_earnings_score(title, content)
            
            # 記事内から日付を抽出
            extracted_dates = self._extract_dates_from_text(title + ' ' + content, date)
            
            # 発表タイミングを検出
            timing_info = self._detect_announcement_timing(title, content)
            
            return {
                'title': article.get('title', ''),
                'date': date,
                'earnings_score': earnings_score,
                'extracted_dates': extracted_dates,
                'timing_info': timing_info,
                'url': article.get('link', ''),
                'source': article.get('source', '')
            }
            
        except Exception as e:
            logger.error(f"Error analyzing news article: {e}")
            return {
                'title': '',
                'date': '',
                'earnings_score': 0.0,
                'extracted_dates': [],
                'timing_info': {'type': 'unknown', 'confidence': 0.0, 'matched_phrases': []},
                'url': '',
                'source': ''
            }
    
    def _detect_announcement_timing(self, title: str, content: str) -> Dict:
        """
        ニュース記事から決算発表のタイミング（寄り付き前/引け後）を検出
        
        Args:
            title: 記事タイトル（小文字）
            content: 記事内容（小文字）
        
        Returns:
            タイミング情報辞書
        """
        try:
            timing_keywords = self.keywords_config['earnings_keywords'].get('timing_keywords', {})
            
            timing_scores = {
                'before_market': 0.0,
                'after_market': 0.0,
                'during_market': 0.0
            }
            
            matched_phrases = {
                'before_market': [],
                'after_market': [],
                'during_market': []
            }
            
            text = title + ' ' + content
            
            # 各タイミングキーワードを検索
            for timing_type, keywords in timing_keywords.items():
                for keyword in keywords:
                    if keyword.lower() in text:
                        # タイトルにある場合は重みを増加
                        weight = 2.0 if keyword.lower() in title else 1.0
                        timing_scores[timing_type] += weight
                        matched_phrases[timing_type].append(keyword)
            
            # 最も高いスコアのタイミングを決定
            if max(timing_scores.values()) == 0:
                return {
                    'type': 'unknown',
                    'confidence': 0.0,
                    'matched_phrases': []
                }
            
            best_timing = max(timing_scores.keys(), key=lambda k: timing_scores[k])
            total_score = sum(timing_scores.values())
            confidence = timing_scores[best_timing] / total_score if total_score > 0 else 0.0
            
            return {
                'type': best_timing,
                'confidence': min(confidence, 1.0),
                'matched_phrases': matched_phrases[best_timing],
                'all_scores': timing_scores
            }
            
        except Exception as e:
            logger.error(f"Error detecting announcement timing: {e}")
            return {
                'type': 'unknown',
                'confidence': 0.0,
                'matched_phrases': []
            }
    
    def _calculate_earnings_score(self, title: str, content: str) -> float:
        """決算関連キーワードのスコアを計算"""
        try:
            keywords = self.keywords_config['earnings_keywords']
            scoring = self.keywords_config['scoring']
            
            score = 0.0
            matched_keywords = []
            
            # Primary keywords
            for keyword in keywords['primary']:
                if keyword.lower() in title:
                    score += scoring['primary_weight'] * scoring.get('title_multiplier', 2.0)
                    matched_keywords.append(f"title:{keyword}")
                elif keyword.lower() in content:
                    score += scoring['primary_weight']
                    matched_keywords.append(f"content:{keyword}")
            
            # Secondary keywords
            for keyword in keywords['secondary']:
                if keyword.lower() in title:
                    score += scoring['secondary_weight'] * scoring.get('title_multiplier', 2.0)
                    matched_keywords.append(f"title:{keyword}")
                elif keyword.lower() in content:
                    score += scoring['secondary_weight']
                    matched_keywords.append(f"content:{keyword}")
            
            # Date pattern keywords
            for pattern in keywords['date_patterns']:
                if pattern.lower() in content:
                    score += scoring.get('date_pattern_weight', 0.8)
                    matched_keywords.append(f"pattern:{pattern}")
            
            # Multiple keyword bonus
            if len(matched_keywords) > 1:
                score += scoring.get('multiple_keyword_bonus', 0.3)
            
            return min(score, 2.0)  # スコアの上限を設定
            
        except Exception as e:
            logger.error(f"Error calculating earnings score: {e}")
            return 0.0
    
    def _extract_dates_from_text(self, text: str, article_date: str) -> List[Dict]:
        """テキストから日付を抽出"""
        extracted_dates = []
        
        try:
            # 絶対日付の抽出
            for pattern in self.compiled_date_patterns:
                matches = pattern.findall(text)
                for match in matches:
                    normalized_date = self._normalize_date(match)
                    if normalized_date:
                        extracted_dates.append({
                            'date': normalized_date,
                            'type': 'absolute',
                            'raw': match
                        })
            
            # 相対日付の抽出（記事日付を基準に変換）
            if article_date:
                for pattern in self.compiled_relative_patterns:
                    matches = pattern.findall(text)
                    for match in matches:
                        normalized_date = self._resolve_relative_date(match, article_date)
                        if normalized_date:
                            extracted_dates.append({
                                'date': normalized_date,
                                'type': 'relative',
                                'raw': match
                            })
            
            return extracted_dates
            
        except Exception as e:
            logger.error(f"Error extracting dates from text: {e}")
            return []
    
    def _normalize_date(self, date_str: str) -> Optional[str]:
        """日付文字列をYYYY-MM-DD形式に正規化"""
        try:
            # 既にYYYY-MM-DD形式の場合
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                return date_str
            
            # MM/DD/YYYY形式
            if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_str):
                date_obj = datetime.strptime(date_str, '%m/%d/%Y')
                return date_obj.strftime('%Y-%m-%d')
            
            # MM-DD-YYYY形式
            if re.match(r'^\d{1,2}-\d{1,2}-\d{4}$', date_str):
                date_obj = datetime.strptime(date_str, '%m-%d-%Y')
                return date_obj.strftime('%Y-%m-%d')
            
            # Month DD, YYYY形式
            try:
                date_obj = datetime.strptime(date_str, '%B %d, %Y')
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                try:
                    date_obj = datetime.strptime(date_str, '%b %d, %Y')
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    pass
            
            return None
            
        except Exception as e:
            logger.error(f"Error normalizing date '{date_str}': {e}")
            return None
    
    def _resolve_relative_date(self, relative_str: str, article_date: str) -> Optional[str]:
        """相対日付を絶対日付に変換"""
        try:
            base_date = datetime.strptime(article_date[:10], '%Y-%m-%d')
            
            if 'yesterday' in relative_str.lower():
                target_date = base_date - timedelta(days=1)
            elif 'tomorrow' in relative_str.lower():
                target_date = base_date + timedelta(days=1)
            elif 'today' in relative_str.lower():
                target_date = base_date
            else:
                # 曜日ベースの相対日付（簡略実装）
                return None
            
            return target_date.strftime('%Y-%m-%d')
            
        except Exception as e:
            logger.error(f"Error resolving relative date '{relative_str}': {e}")
            return None
    
    def _determine_actual_date(self, earnings_evidence: List[Dict], 
                             eodhd_date: str) -> Tuple[str, float]:
        """証拠に基づいて実際の決算日を決定"""
        try:
            date_scores = defaultdict(float)
            date_counts = defaultdict(int)
            timing_info = self._aggregate_timing_info(earnings_evidence)
            
            # 各記事の証拠を評価
            for evidence in earnings_evidence:
                score = evidence['earnings_score']
                
                # 抽出された日付にスコアを配分
                for date_info in evidence['extracted_dates']:
                    date = date_info['date']
                    if date:
                        date_scores[date] += score
                        date_counts[date] += 1
                
                # 記事日付も候補として考慮（重みは低め）
                if evidence['date']:
                    article_date = evidence['date'][:10]
                    date_scores[article_date] += score * 0.3
                    date_counts[article_date] += 1
            
            # EODHDの日付も候補として追加
            if eodhd_date not in date_scores:
                date_scores[eodhd_date] = 0.5  # 基準スコア
                date_counts[eodhd_date] = 1
            
            if not date_scores:
                return eodhd_date, 0.0
            
            # 最高スコアの日付を選択
            best_date = max(date_scores.keys(), key=lambda d: date_scores[d])
            
            # 信頼度を計算
            confidence = min(date_scores[best_date] / 2.0, 1.0)  # 正規化
            
            return best_date, confidence
            
        except Exception as e:
            logger.error(f"Error determining actual date: {e}")
            return eodhd_date, 0.0
    
    def _aggregate_timing_info(self, earnings_evidence: List[Dict]) -> Dict:
        """複数の記事からタイミング情報を集約"""
        try:
            timing_counts = defaultdict(float)
            total_confidence = 0.0
            
            for evidence in earnings_evidence:
                timing = evidence.get('timing_info', {})
                if timing.get('type') != 'unknown':
                    weight = evidence['earnings_score'] * timing.get('confidence', 0.0)
                    timing_counts[timing['type']] += weight
                    total_confidence += weight
            
            if total_confidence == 0:
                return {'type': 'unknown', 'confidence': 0.0}
            
            # 最も信頼性の高いタイミングを決定
            best_timing = max(timing_counts.keys(), key=lambda k: timing_counts[k])
            confidence = timing_counts[best_timing] / total_confidence
            
            return {
                'type': best_timing,
                'confidence': confidence,
                'all_timings': dict(timing_counts)
            }
            
        except Exception as e:
            logger.error(f"Error aggregating timing info: {e}")
            return {'type': 'unknown', 'confidence': 0.0}
    
    def _create_validation_result(self, symbol: str, eodhd_date: str, 
                                actual_date: str, confidence: float,
                                evidence: List[Dict]) -> Dict:
        """検証結果を作成"""
        thresholds = self.keywords_config.get('confidence_thresholds', {})
        
        if confidence >= thresholds.get('high', 0.8):
            confidence_level = 'high'
        elif confidence >= thresholds.get('medium', 0.6):
            confidence_level = 'medium'
        elif confidence >= thresholds.get('low', 0.4):
            confidence_level = 'low'
        else:
            confidence_level = 'very_low'
        
        # タイミング情報を集約
        timing_info = self._aggregate_timing_info(evidence)
        
        return {
            'symbol': symbol,
            'eodhd_date': eodhd_date,
            'actual_date': actual_date,
            'confidence': confidence,
            'confidence_level': confidence_level,
            'date_changed': actual_date != eodhd_date,
            'announcement_timing': timing_info,
            'news_evidence': evidence,
            'validation_timestamp': datetime.now().isoformat()
        }
    
    def get_validation_stats(self) -> Dict:
        """検証統計情報を取得"""
        return dict(self.validation_stats)