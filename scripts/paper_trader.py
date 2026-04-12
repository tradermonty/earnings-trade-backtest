#!/usr/bin/env python3
"""
Paper Trading CLI — manual management tool

Usage:
  python scripts/paper_trader.py status
  python scripts/paper_trader.py positions
  python scripts/paper_trader.py close VSNT
  python scripts/paper_trader.py close VSNT --qty 10
"""

import argparse
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.alpaca_order_manager import AlpacaOrderManager

DATA_DIR = os.path.join(project_root, 'data')
TRADES_FILE = os.path.join(DATA_DIR, 'paper_trades.json')


def cmd_status(args):
    mgr = AlpacaOrderManager(account_type='paper')
    summary = mgr.get_account_summary()
    print(f"=== Paper Account Status ===")
    print(f"Account ID: {summary['account_id']}")
    print(f"Status:     {summary['status']}")
    print(f"Equity:     ${summary['equity']:,.2f}")
    print(f"Cash:       ${summary['cash']:,.2f}")
    print(f"Portfolio:  ${summary['portfolio_value']:,.2f}")
    print(f"Buying Power: ${summary['buying_power']:,.2f}")

    # Local trade stats
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE) as f:
            trades = json.load(f)
        open_count = sum(1 for t in trades if t['status'] == 'open')
        closed_count = sum(1 for t in trades if t['status'] == 'closed')
        total_pnl = sum(
            leg.get('pnl', 0) for t in trades
            for leg in t.get('legs', [])
            if leg.get('action', '').startswith('exit')
        )
        print(f"\n--- Strategy Trades ---")
        print(f"Open:   {open_count}")
        print(f"Closed: {closed_count}")
        print(f"Realized P&L: ${total_pnl:,.2f}")


def cmd_positions(args):
    mgr = AlpacaOrderManager(account_type='paper')
    positions = mgr.get_positions()

    if not positions:
        print("No open positions.")
        return

    print(f"{'Symbol':8s} {'Qty':>5s} {'AvgEntry':>10s} {'Current':>10s} {'P&L%':>8s} {'P&L$':>10s}")
    print("-" * 55)
    for p in sorted(positions, key=lambda x: x['unrealized_plpc'], reverse=True):
        print(f"{p['symbol']:8s} {p['qty']:5d} ${p['avg_entry_price']:9.2f} "
              f"${p['current_price']:9.2f} {p['unrealized_plpc']*100:+7.1f}% "
              f"${p['unrealized_pl']:+9.2f}")


def cmd_close(args):
    mgr = AlpacaOrderManager(account_type='paper')
    symbol = args.symbol.upper()
    qty = args.qty

    if qty:
        print(f"Closing {qty} shares of {symbol}...")
        result = mgr.close_position(symbol, qty=qty)
    else:
        print(f"Closing all shares of {symbol}...")
        result = mgr.close_position(symbol)

    print(f"Order: {result}")


def main():
    parser = argparse.ArgumentParser(description='Paper trading CLI')
    subparsers = parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser('status', help='Account summary')
    subparsers.add_parser('positions', help='Open positions')

    close_parser = subparsers.add_parser('close', help='Close position')
    close_parser.add_argument('symbol', type=str, help='Stock symbol')
    close_parser.add_argument('--qty', type=int, default=None,
                              help='Number of shares (default: all)')

    args = parser.parse_args()

    if args.command == 'status':
        cmd_status(args)
    elif args.command == 'positions':
        cmd_positions(args)
    elif args.command == 'close':
        cmd_close(args)


if __name__ == '__main__':
    main()
