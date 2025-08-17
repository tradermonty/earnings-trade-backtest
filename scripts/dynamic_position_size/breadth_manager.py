"""
Market Breadth Index データ管理クラス
実際のCSVファイル構造に対応
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging


class MarketBreadthManager:
    """Market Breadth Indexデータの読み込み・管理クラス"""
    
    def __init__(self, csv_path: str):
        """
        Args:
            csv_path: Market Breadth IndexのCSVファイルパス
        """
        self.csv_path = csv_path
        self.breadth_data = None
        self._load_csv()
        
    def _load_csv(self):
        """実際のCSV構造に対応した読み込み"""
        try:
            # CSVファイル読み込み
            df = pd.read_csv(self.csv_path)
            
            # Date列をdatetimeに変換してインデックスに設定
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            
            # Boolean列の処理（文字列の場合）
            boolean_columns = ['Bearish_Signal', 'Is_Peak', 'Is_Trough', 'Is_Trough_8MA_Below_04']
            for col in boolean_columns:
                if col in df.columns:
                    if df[col].dtype == 'object':  # 文字列の場合
                        df[col] = df[col].astype(str).str.lower() == 'true'
                    else:  # 既にbooleanの場合はそのまま
                        df[col] = df[col].astype(bool)
            
            self.breadth_data = df
            
            logging.info(f"Market Breadth data loaded successfully:")
            logging.info(f"  Period: {df.index.min()} to {df.index.max()}")
            logging.info(f"  Records: {len(df):,}")
            logging.info(f"  Columns: {list(df.columns)}")
            
        except Exception as e:
            logging.error(f"Failed to load Market Breadth CSV: {e}")
            raise
    
    def get_market_data(self, date: datetime) -> Optional[Dict[str, Any]]:
        """
        指定日のMarket Breadthデータを取得
        
        Args:
            date: 取得したい日付
            
        Returns:
            Dict containing market data or None if not found
        """
        if self.breadth_data is None:
            return None
            
        # 日付を正規化（時間部分を除去）
        target_date = pd.Timestamp(date.date())
        
        # 完全一致を試行
        if target_date in self.breadth_data.index:
            row = self.breadth_data.loc[target_date]
            return self._row_to_dict(row, target_date)
        
        # 完全一致しない場合、前後のデータで補間
        return self._interpolate_data(target_date)
    
    def _row_to_dict(self, row: pd.Series, date: pd.Timestamp) -> Dict[str, Any]:
        """pandas Seriesを辞書に変換"""
        return {
            'date': date,
            'sp500_price': float(row.get('S&P500_Price', 0)),
            'breadth_raw': float(row.get('Breadth_Index_Raw', 0)),
            'breadth_200ma': float(row.get('Breadth_Index_200MA', 0)),
            'breadth_8ma': float(row.get('Breadth_Index_8MA', 0)),
            'trend_200ma': int(row.get('Breadth_200MA_Trend', 0)),
            'bearish_signal': bool(row.get('Bearish_Signal', False)),
            'is_peak': bool(row.get('Is_Peak', False)),
            'is_trough': bool(row.get('Is_Trough', False)),
            'is_trough_8ma_below_04': bool(row.get('Is_Trough_8MA_Below_04', False))
        }
    
    def _interpolate_data(self, target_date: pd.Timestamp) -> Optional[Dict[str, Any]]:
        """
        データが見つからない場合の補間処理
        前後数日のデータを探して最も近いものを使用
        """
        # 前後5営業日の範囲で検索
        for days_offset in range(1, 6):
            # 前の日を試行
            prev_date = target_date - timedelta(days=days_offset)
            if prev_date in self.breadth_data.index:
                row = self.breadth_data.loc[prev_date]
                logging.debug(f"Using interpolated data from {prev_date} for {target_date}")
                return self._row_to_dict(row, prev_date)
            
            # 後の日を試行
            next_date = target_date + timedelta(days=days_offset)
            if next_date in self.breadth_data.index:
                row = self.breadth_data.loc[next_date]
                logging.debug(f"Using interpolated data from {next_date} for {target_date}")
                return self._row_to_dict(row, next_date)
        
        # 見つからない場合
        logging.warning(f"No Market Breadth data found near {target_date}")
        return None
    
    def get_market_condition(self, breadth_8ma: float) -> str:
        """Breadth Index 8MA値から市場状況を判定"""
        if breadth_8ma < 0.3:
            return "extreme_stress"
        elif breadth_8ma < 0.4:
            return "stress"
        elif breadth_8ma < 0.6:
            return "normal_weak"
        elif breadth_8ma < 0.7:
            return "normal_strong"
        elif breadth_8ma < 0.8:
            return "bullish"
        else:
            return "extreme_bullish"
    
    def get_data_range(self) -> tuple:
        """データの有効期間を取得"""
        if self.breadth_data is None:
            return None, None
        return self.breadth_data.index.min(), self.breadth_data.index.max()
    
    def get_statistics(self) -> Dict[str, Any]:
        """データの統計情報を取得"""
        if self.breadth_data is None:
            return {}
        
        breadth_8ma = self.breadth_data['Breadth_Index_8MA']
        
        return {
            'total_records': len(self.breadth_data),
            'date_range': self.get_data_range(),
            'breadth_8ma_stats': {
                'min': float(breadth_8ma.min()),
                'max': float(breadth_8ma.max()),
                'mean': float(breadth_8ma.mean()),
                'std': float(breadth_8ma.std())
            },
            'condition_distribution': {
                'extreme_stress': int((breadth_8ma < 0.3).sum()),
                'stress': int(((breadth_8ma >= 0.3) & (breadth_8ma < 0.4)).sum()),
                'normal': int(((breadth_8ma >= 0.4) & (breadth_8ma < 0.7)).sum()),
                'bullish': int(((breadth_8ma >= 0.7) & (breadth_8ma < 0.8)).sum()),
                'extreme_bullish': int((breadth_8ma >= 0.8).sum())
            },
            'signal_counts': {
                'bearish_signals': int(self.breadth_data['Bearish_Signal'].sum()),
                'peaks': int(self.breadth_data['Is_Peak'].sum()),
                'troughs': int(self.breadth_data['Is_Trough'].sum()),
                'trough_8ma_below_04': int(self.breadth_data['Is_Trough_8MA_Below_04'].sum())
            }
        }
    
    def validate_backtest_coverage(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """バックテスト期間のデータカバレッジを検証"""
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        if self.breadth_data is None:
            return {'covered': False, 'reason': 'No data loaded'}
        
        data_start, data_end = self.get_data_range()
        
        coverage = {
            'covered': data_start <= start_dt and end_dt <= data_end,
            'requested_period': (start_dt, end_dt),
            'available_period': (data_start, data_end),
            'missing_start_days': max(0, (start_dt - data_start).days) if start_dt < data_start else 0,
            'missing_end_days': max(0, (end_dt - data_end).days) if end_dt > data_end else 0
        }
        
        if coverage['covered']:
            # 期間内のデータ分布
            period_data = self.breadth_data[(self.breadth_data.index >= start_dt) & 
                                          (self.breadth_data.index <= end_dt)]
            breadth_8ma = period_data['Breadth_Index_8MA']
            
            coverage['period_stats'] = {
                'records': len(period_data),
                'breadth_distribution': {
                    'extreme_stress': int((breadth_8ma < 0.3).sum()),
                    'stress': int(((breadth_8ma >= 0.3) & (breadth_8ma < 0.4)).sum()),
                    'normal': int(((breadth_8ma >= 0.4) & (breadth_8ma < 0.7)).sum()),
                    'bullish': int((breadth_8ma >= 0.7).sum())
                }
            }
        
        return coverage