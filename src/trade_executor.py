import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from tqdm import tqdm

from .data_fetcher import DataFetcher
from .risk_manager import RiskManager


class TradeExecutor:
    """トレード実行クラス"""
    
    def __init__(self, data_fetcher: DataFetcher, risk_manager: RiskManager,
                 initial_capital: float = 10000, position_size: float = 6,
                 stop_loss: float = 6, trail_stop_ma: int = 21,
                 max_holding_days: int = 90, slippage: float = 0.3,
                 partial_profit: bool = True):
        """TradeExecutorの初期化"""
        self.data_fetcher = data_fetcher
        self.risk_manager = risk_manager
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.stop_loss = stop_loss
        self.trail_stop_ma = trail_stop_ma
        self.max_holding_days = max_holding_days
        self.slippage = slippage
        self.partial_profit = partial_profit
        
        # トレード記録
        self.trades = []
        self.current_capital = initial_capital
    
    def execute_backtest(self, trade_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """バックテストの実行"""
        print("\n4. バックテストの実行中...")
        print(f"初期資金: ${self.initial_capital:,.2f}")
        print(f"ポジションサイズ: {self.position_size}%")
        print(f"ストップロス: {self.stop_loss}%")
        print(f"トレーリングストップMA: {self.trail_stop_ma}日")
        print(f"最大保有期間: {self.max_holding_days}日")
        print(f"スリッページ: {self.slippage}%")
        
        self.trades = []
        self.current_capital = self.initial_capital
        total_candidates = len(trade_candidates)
        
        # tqdmを使用してプログレスバーを表示
        for candidate in tqdm(trade_candidates, desc="バックテスト実行", total=total_candidates):
            try:
                symbol = candidate['code']
                entry_date = candidate['trade_date']
                
                # リスク管理チェック
                if not self.risk_manager.check_risk_management(entry_date, self.current_capital, self.trades):
                    tqdm.write(f"\n{entry_date}: {symbol} - リスク管理によりトレードをスキップ")
                    continue
                
                # トレードを実行
                trade_result = self._execute_single_trade(candidate)
                if trade_result:
                    self.trades.extend(trade_result)
                
            except Exception as e:
                tqdm.write(f"エラー ({candidate.get('code', 'Unknown')}): {str(e)}")
                continue
        
        print("\n5. バックテスト完了")
        print(f"実行したトレード数: {len(self.trades)}")
        print(f"最終資産: ${self.current_capital:,.2f}")
        
        return self.trades
    
    def _execute_single_trade(self, candidate: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """単一トレードの実行"""
        symbol = candidate['code']
        entry_date = candidate['trade_date']
        
        tqdm.write(f"\n処理中: {symbol} - {entry_date}")
        
        # 株価データの取得
        stock_data = self._get_stock_data(symbol, entry_date)
        if stock_data is None:
            tqdm.write(f"- スキップ: 株価データなし")
            return None
        
        # ポジションサイズの計算
        position_info = self.risk_manager.calculate_position_size(
            self.current_capital, self.position_size, candidate['price'], self.slippage
        )
        
        if position_info['shares'] == 0:
            tqdm.write(f"- スキップ: 購入可能株数が0")
            return None
        
        entry_price = position_info['adjusted_entry_price']
        shares = position_info['shares']
        
        tqdm.write(f"- エントリー: ${entry_price:.2f} x {shares}株")
        
        # トレードの実行
        trades = []
        
        # エントリー当日のストップロスチェック
        intraday_stop_trade = self._check_intraday_stop_loss(
            stock_data, entry_date, symbol, shares, entry_price, candidate['gap']
        )
        if intraday_stop_trade:
            trades.append(intraday_stop_trade)
            self.current_capital += intraday_stop_trade['pnl']
            return trades
        
        # 部分利確のチェック
        partial_trade, remaining_shares = self._check_partial_profit(
            stock_data, entry_date, symbol, shares, entry_price
        )
        if partial_trade:
            trades.append(partial_trade)
            self.current_capital += partial_trade['pnl']
            shares = remaining_shares
        
        # メインポジションの売却
        main_trade = self._execute_main_position_exit(
            stock_data, entry_date, symbol, shares, entry_price, candidate['gap']
        )
        if main_trade:
            trades.append(main_trade)
            self.current_capital += main_trade['pnl']
        
        return trades
    
    def _get_stock_data(self, symbol: str, entry_date: str) -> Optional[pd.DataFrame]:
        """株価データの取得と前処理"""
        stock_data = self.data_fetcher.get_historical_data(
            symbol,
            entry_date,
            (datetime.strptime(entry_date, "%Y-%m-%d") + 
             timedelta(days=self.max_holding_days + 30)).strftime("%Y-%m-%d")
        )
        
        if stock_data is None or stock_data.empty:
            return None
        
        # DataFrameのカラム名を統一
        if 'close' in stock_data.columns:
            stock_data = stock_data.rename(columns={
                'open': 'Open', 'high': 'High', 'low': 'Low', 
                'close': 'Close', 'volume': 'Volume'
            })
        
        # 日付をインデックスに設定
        stock_data = stock_data.set_index('date')
        
        # 移動平均を計算
        stock_data[f'MA{self.trail_stop_ma}'] = stock_data['Close'].rolling(
            window=self.trail_stop_ma
        ).mean()
        
        return stock_data
    
    def _check_intraday_stop_loss(self, stock_data: pd.DataFrame, entry_date: str,
                                 symbol: str, shares: int, entry_price: float,
                                 gap: float) -> Optional[Dict[str, Any]]:
        """エントリー当日のストップロスチェック"""
        try:
            trade_data = stock_data.loc[entry_date:]
            entry_idx = trade_data.index.get_loc(entry_date)
            
            # ストップロス価格
            stop_loss_price = entry_price * (1 - self.stop_loss/100)
            
            # エントリー当日の安値がストップロス価格を下回っているかチェック
            entry_day_low = trade_data.iloc[entry_idx]['Low']
            if entry_day_low <= stop_loss_price:
                # ストップロス価格で決済（スリッページを適用）
                exit_price = stop_loss_price * (1 - self.slippage/100)
                trade_pnl = (exit_price - entry_price) * shares
                trade_pnl_rate = ((exit_price - entry_price) / entry_price) * 100
                
                trade_record = {
                    'entry_date': entry_date,
                    'exit_date': entry_date,
                    'ticker': symbol,
                    'shares': shares,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl': trade_pnl,
                    'pnl_rate': trade_pnl_rate,
                    'holding_period': 0,
                    'exit_reason': "stop_loss_intraday",
                    'gap': gap
                }
                
                tqdm.write(f"- 当日ストップロス: ${exit_price:.2f}")
                tqdm.write(f"- 損益: ${trade_pnl:.2f} ({trade_pnl_rate:.2f}%)")
                return trade_record
            
        except (KeyError, IndexError):
            pass
        
        return None
    
    def _check_partial_profit(self, stock_data: pd.DataFrame, entry_date: str,
                             symbol: str, shares: int, entry_price: float) -> tuple:
        """初日の部分利確チェック"""
        if not self.partial_profit:
            return None, shares
        
        try:
            trade_data = stock_data.loc[entry_date:]
            entry_idx = trade_data.index.get_loc(entry_date)
            
            # 初日の終値で部分利確をチェック
            entry_day_close = trade_data.iloc[entry_idx]['Close']
            entry_day_profit_rate = ((entry_day_close - entry_price) / entry_price) * 100
            
            if entry_day_profit_rate >= 6:
                # 半分のポジションを利確（スリッページを適用）
                half_shares = shares // 2
                if half_shares > 0:
                    exit_price_partial = entry_day_close * (1 - self.slippage/100)
                    trade_pnl_partial = (exit_price_partial - entry_price) * half_shares
                    trade_pnl_rate_partial = ((exit_price_partial - entry_price) / entry_price) * 100
                    
                    # 部分利確のトレード記録
                    trade_record_partial = {
                        'entry_date': entry_date,
                        'exit_date': entry_date,
                        'ticker': symbol,
                        'holding_period': 0,
                        'entry_price': round(entry_price, 2),
                        'exit_price': round(exit_price_partial, 2),
                        'shares': half_shares,
                        'pnl_rate': round(trade_pnl_rate_partial, 2),
                        'pnl': round(trade_pnl_partial, 2),
                        'exit_reason': 'partial_profit'
                    }
                    
                    tqdm.write(f"- 部分利確: ${exit_price_partial:.2f} x {half_shares}株")
                    tqdm.write(f"- 部分利確損益: ${trade_pnl_partial:.2f} ({trade_pnl_rate_partial:.2f}%)")
                    
                    # 残りのポジションサイズを更新
                    remaining_shares = shares - half_shares
                    return trade_record_partial, remaining_shares
            
        except (KeyError, IndexError):
            pass
        
        return None, shares
    
    def _execute_main_position_exit(self, stock_data: pd.DataFrame, entry_date: str,
                                   symbol: str, shares: int, entry_price: float,
                                   gap: float) -> Optional[Dict[str, Any]]:
        """メインポジションの売却実行"""
        try:
            trade_data = stock_data.loc[entry_date:]
            entry_idx = trade_data.index.get_loc(entry_date)
            
            # ストップロス価格
            stop_loss_price = entry_price * (1 - self.stop_loss/100)
            
            # 売却条件のチェック
            exit_price = None
            exit_date = None
            exit_reason = None
            
            for i in range(entry_idx + 1, len(trade_data)):
                current_date = trade_data.index[i]
                current_row = trade_data.iloc[i]
                days_held = (current_date - datetime.strptime(entry_date, "%Y-%m-%d")).days
                
                # 1. 最大保有期間のチェック
                if days_held >= self.max_holding_days:
                    exit_price = current_row['Close'] * (1 - self.slippage/100)
                    exit_date = current_date.strftime("%Y-%m-%d")
                    exit_reason = "max_holding_days"
                    break
                
                # 2. ストップロスのチェック
                if current_row['Low'] <= stop_loss_price:
                    exit_price = stop_loss_price * (1 - self.slippage/100)
                    exit_date = current_date.strftime("%Y-%m-%d")
                    exit_reason = "stop_loss"
                    break
                
                # 3. トレーリングストップのチェック
                ma_column = f'MA{self.trail_stop_ma}'
                if ma_column in current_row and pd.notna(current_row[ma_column]):
                    if current_row['Close'] < current_row[ma_column]:
                        exit_price = current_row[ma_column] * (1 - self.slippage/100)
                        exit_date = current_date.strftime("%Y-%m-%d")
                        exit_reason = "trailing_stop"
                        break
            
            # 売却が発生しなかった場合は最終日で売却
            if exit_price is None:
                last_row = trade_data.iloc[-1]
                exit_price = last_row['Close'] * (1 - self.slippage/100)
                exit_date = last_row.name.strftime("%Y-%m-%d")
                exit_reason = "end_of_data"
            
            # 損益計算
            trade_pnl = (exit_price - entry_price) * shares
            trade_pnl_rate = ((exit_price - entry_price) / entry_price) * 100
            
            # トレード記録
            trade_record = {
                'entry_date': entry_date,
                'exit_date': exit_date,
                'ticker': symbol,
                'shares': shares,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl': trade_pnl,
                'pnl_rate': trade_pnl_rate,
                'holding_period': (datetime.strptime(exit_date, "%Y-%m-%d") - 
                                 datetime.strptime(entry_date, "%Y-%m-%d")).days,
                'exit_reason': exit_reason,
                'gap': gap
            }
            
            tqdm.write(f"- 決済: ${exit_price:.2f} ({exit_reason})")
            tqdm.write(f"- 損益: ${trade_pnl:.2f} ({trade_pnl_rate:.2f}%)")
            
            return trade_record
            
        except Exception as e:
            tqdm.write(f"メインポジション売却エラー: {str(e)}")
            return None