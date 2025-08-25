"""
Market Breadth Index CSVファイルの管理
"""

import pandas as pd
import os
from datetime import datetime
from typing import Dict, Optional, Any


class MarketBreadthManager:
    """Market Breadth Index データの管理クラス"""
    
    def __init__(self, csv_path: str):
        """
        Args:
            csv_path: Market Breadth CSV ファイルのパス
        """
        self.csv_path = csv_path
        self.data = None
        self._load_data()
    
    def _load_data(self):
        """CSVファイルを読み込み"""
        try:
            if not os.path.exists(self.csv_path):
                raise FileNotFoundError(f"Market Breadth CSV not found: {self.csv_path}")
            
            # CSVファイル読み込み
            df = pd.read_csv(self.csv_path)
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            
            # Boolean列の処理
            boolean_columns = ['Bearish_Signal', 'Is_Peak', 'Is_Trough', 'Is_Trough_8MA_Below_04']
            for col in boolean_columns:
                if col in df.columns:
                    if df[col].dtype == 'object':
                        df[col] = df[col].astype(str).str.lower() == 'true'
                    else:
                        df[col] = df[col].astype(bool)
            
            self.data = df
            print(f"✅ Market Breadth data loaded: {len(df)} records from {df.index.min().date()} to {df.index.max().date()}")
            
        except Exception as e:
            print(f"❌ Error loading Market Breadth CSV: {e}")
            raise
    
    def get_market_data(self, date: datetime) -> Optional[Dict[str, Any]]:
        """
        指定日のMarket Breadthデータを取得
        
        Args:
            date: 対象日
            
        Returns:
            Market Breadthデータの辞書、データがない場合はNone
        """
        if self.data is None:
            return None
        
        target_date = pd.Timestamp(date.date())
        
        # 完全一致を試行
        if target_date in self.data.index:
            row = self.data.loc[target_date]
            return self._create_market_data_dict(row)
        
        # 前後数日のデータで補間
        for days_offset in range(1, 6):
            for offset in [-days_offset, days_offset]:
                test_date = target_date + pd.Timedelta(days=offset)
                if test_date in self.data.index:
                    row = self.data.loc[test_date]
                    return self._create_market_data_dict(row)
        
        return None
    
    def _create_market_data_dict(self, row) -> Dict[str, Any]:
        """データ行から辞書を作成"""
        return {
            'breadth_8ma': float(row.get('Breadth_Index_8MA', 0)),
            'breadth_200ma': float(row.get('Breadth_Index_200MA', 0)),
            'bearish_signal': bool(row.get('Bearish_Signal', False)),
            'is_peak': bool(row.get('Is_Peak', False)),
            'is_trough': bool(row.get('Is_Trough', False)),
            'is_trough_8ma_below_04': bool(row.get('Is_Trough_8MA_Below_04', False))
        }
    
    def get_market_condition(self, breadth_8ma: float) -> str:
        """Market Breadth Index 8MAから市場状況を判定"""
        if breadth_8ma < 0.3:
            return "extreme_stress"
        elif breadth_8ma < 0.4:
            return "stress"
        elif breadth_8ma < 0.7:
            return "normal"
        elif breadth_8ma < 0.8:
            return "bullish"
        else:
            return "extreme_bullish"
    
    def validate_backtest_coverage(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        バックテスト期間のデータカバレッジを検証
        
        Returns:
            カバレッジ情報の辞書
        """
        if self.data is None:
            return {'covered': False, 'reason': 'No data loaded'}
        
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        
        data_start = self.data.index.min()
        data_end = self.data.index.max()
        
        covered = (start_dt >= data_start) and (end_dt <= data_end)
        
        return {
            'covered': covered,
            'requested_period': f"{start_date} to {end_date}",
            'available_period': f"{data_start.date()} to {data_end.date()}",
            'total_records': len(self.data)
        }