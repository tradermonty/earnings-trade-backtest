#!/usr/bin/env python3
import pandas as pd
import numpy as np
from itertools import combinations


def load_and_merge():
    screen_df = pd.read_csv('earnings/aggregated_screen.csv')
    trades_df = pd.read_csv('reports/earnings_backtest_2024_09_01_2025_07_30_finviz_.csv')

    screen_df['Trade Date'] = pd.to_datetime(screen_df['Trade Date'])
    trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])

    merged = []
    for _, trade in trades_df.iterrows():
        ticker = trade['ticker']
        entry_date = trade['entry_date']
        matches = screen_df[(screen_df['Ticker'] == ticker) &
                            (abs((screen_df['Trade Date'] - entry_date).dt.days) <= 3)]
        if len(matches) > 0:
            closest = matches.loc[(matches['Trade Date'] - entry_date).abs().idxmin()]
            merged.append({**trade.to_dict(), **closest.to_dict()})

    merged_df = pd.DataFrame(merged)
    return merged_df


def to_numeric(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.replace('%', '', regex=False).str.replace(',', '', regex=False)
    s = pd.to_numeric(s, errors='coerce')
    return s


def eval_metrics(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return {'count': 0, 'win_rate': np.nan, 'avg_pnl_rate': np.nan, 'total_pnl': 0.0}
    wins = (df['pnl'] > 0).sum()
    total = len(df)
    return {
        'count': total,
        'win_rate': wins / total if total else np.nan,
        'avg_pnl_rate': df['pnl_rate'].mean() if total else np.nan,
        'total_pnl': df['pnl'].sum() if total else 0.0,
    }


def main():
    df = load_and_merge()
    base = eval_metrics(df)
    print("BASE:")
    print(f"  count={base['count']} win_rate={base['win_rate']*100:.1f}% avg_pnl_rate={base['avg_pnl_rate']:.3f} total_pnl={base['total_pnl']:.2f}")

    candidates = [
        ('P/E', 'upper'),
        ('Gap', 'upper'),
        ('Performance (Week)', 'upper'),
        ('Performance (Month)', 'upper'),
        ('Relative Strength Index (14)', 'upper'),
        ('Beta', 'upper'),
        ('Volatility (Week)', 'upper'),
    ]

    # Prepare numeric columns
    numcols = {}
    for name, _ in candidates:
        if name in df.columns:
            numcols[name] = to_numeric(df[name])

    percentiles = [50, 60, 70, 80, 85, 90, 95]
    results = []

    min_retain_ratio = 0.5  # keep at least 50% of trades

    for name, direction in candidates:
        if name not in numcols:
            continue
        col = numcols[name]
        valid = ~col.isna()
        if valid.sum() == 0:
            continue
        for p in percentiles:
            thresh = np.nanpercentile(col, p)
            if direction == 'upper':
                mask = col <= thresh
            else:
                mask = col >= thresh
            filtered = df[valid & mask]
            met = eval_metrics(filtered)
            retain = met['count'] / base['count'] if base['count'] else 0
            if retain >= min_retain_ratio:
                improvement = met['total_pnl'] - base['total_pnl']
                results.append({
                    'feature': name,
                    'percentile': p,
                    'threshold': float(thresh) if np.isfinite(thresh) else np.nan,
                    'retain_ratio': retain,
                    'win_rate': met['win_rate'],
                    'avg_pnl_rate': met['avg_pnl_rate'],
                    'total_pnl': met['total_pnl'],
                    'pnl_improvement': improvement,
                })

    if not results:
        print("No univariate thresholds met retention constraint.")
        return

    # Sort by pnl improvement then win rate
    results.sort(key=lambda r: (r['pnl_improvement'], r['win_rate']), reverse=True)
    print("\nTOP UNIVARIATE THRESHOLDS (retain>=50%):")
    for r in results[:10]:
        print(f"- {r['feature']} <= {r['threshold']:.2f} (p{r['percentile']}): count={int(base['count']*r['retain_ratio'])}, win_rate={r['win_rate']*100:.1f}%, avg_rate={r['avg_pnl_rate']:.3f}, total_pnl={r['total_pnl']:.2f}, ΔPnL={r['pnl_improvement']:.2f}")

    # Try simple pairwise combos from top 5
    top_features = list({r['feature'] for r in results[:5]})
    combos_out = []
    for f1, f2 in combinations(top_features, 2):
        opts1 = [r for r in results if r['feature'] == f1][:3]
        opts2 = [r for r in results if r['feature'] == f2][:3]
        for o1 in opts1:
            for o2 in opts2:
                m1 = (numcols[f1] <= o1['threshold'])
                m2 = (numcols[f2] <= o2['threshold'])
                filt = df[m1 & m2]
                met = eval_metrics(filt)
                retain = met['count'] / base['count'] if base['count'] else 0
                if retain >= min_retain_ratio:
                    improvement = met['total_pnl'] - base['total_pnl']
                    combos_out.append({
                        'features': (f1, f2),
                        'thresholds': (o1['threshold'], o2['threshold']),
                        'retain_ratio': retain,
                        'win_rate': met['win_rate'],
                        'avg_pnl_rate': met['avg_pnl_rate'],
                        'total_pnl': met['total_pnl'],
                        'pnl_improvement': improvement,
                    })

    if combos_out:
        combos_out.sort(key=lambda r: (r['pnl_improvement'], r['win_rate']), reverse=True)
        print("\nTOP PAIRWISE COMBINATIONS (retain>=50%):")
        for c in combos_out[:10]:
            (f1, f2) = c['features']
            (t1, t2) = c['thresholds']
            print(f"- {f1} <= {t1:.2f} & {f2} <= {t2:.2f}: count={int(base['count']*c['retain_ratio'])}, win_rate={c['win_rate']*100:.1f}%, avg_rate={c['avg_pnl_rate']:.3f}, total_pnl={c['total_pnl']:.2f}, ΔPnL={c['pnl_improvement']:.2f}")


if __name__ == '__main__':
    main()


