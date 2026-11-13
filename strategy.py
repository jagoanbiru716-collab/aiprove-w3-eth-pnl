#!/usr/bin/env python3
"""eth-pnl-fixed strategy (wallet 3, ZephyrNode): Bollinger-band breakout
with a long-term SMA trend filter.

Interface
---------
Input : bars.csv in the same directory (columns: minute,open,high,low,close,volume)
Output: positions.csv in the same directory (columns: minute,position)
        position in {-1, 0, 1}: -1 = short 1 ETH, 0 = flat, +1 = long 1 ETH.
        Fixed size of 1 ETH keeps slippage small and turnover low.

Logic (3 parameters, no fitted constants, no bar-index hard-coding)
--------------------------------------------------------------------
- Bollinger bands of close: mid = SMA(80), band = mid +/- 2.1 * std(80)
  (sample std, ddof=1, matching the reference backtest).
- Trend filter: SMA(250) of close. A long breakout is only taken while
  close is ABOVE the SMA(250); a short breakout only while close is BELOW
  it. This is the standard "trade breakouts only in the direction of the
  long-term trend" rule — it keeps the strategy out of counter-trend
  breakouts in choppy, range-bound stretches.
- Position for bar t is decided ONLY from data up to bar t-1 (no lookahead):
    if close[t-1] > upper[t-1] and close[t-1] > sma250[t-1] -> long  (+1)
    if close[t-1] < lower[t-1] and close[t-1] < sma250[t-1] -> short (-1)
    otherwise -> keep the previous position (hold until the opposite
    breakout fires; there is no separate exit rule).
- Warm-up: bands are undefined until 80 closes exist, the SMA(250) until
  250 closes exist, so the first fill can only fire after bar 250
  (on this sample: minute 333).
- Symmetric in construction (long and short use the same rule mirrored)
  and regime-agnostic: it follows breakouts in either direction and does
  not assume this sample's downtrend repeats on a held-out tail.
- Pure standard library (csv, math, sys): no third-party dependency, so
  the sandbox can replay it anywhere. Fully deterministic: same bars in,
  same positions out, every run.

Usage:  python3 strategy.py [bars.csv] [positions.csv]
"""
import csv
import math
import sys

WINDOW = 80        # Bollinger window (bars)
K = 2.1            # Bollinger half-width in standard deviations
SMA_LONG = 250     # trend-filter window (bars)
SIZE = 1           # ETH per position unit


def _rolling_stats(values, window):
    """Return (mean, sample-std) of the trailing `window` values ending at
    each index; None where fewer than `window` values exist yet."""
    means = [None] * len(values)
    stds = [None] * len(values)
    s = 0.0
    s2 = 0.0
    for i, v in enumerate(values):
        s += v
        s2 += v * v
        if i >= window:
            old = values[i - window]
            s -= old
            s2 -= old * old
        if i >= window - 1:
            m = s / window
            # sample variance, ddof=1
            var = (s2 - window * m * m) / (window - 1)
            means[i] = m
            stds[i] = math.sqrt(var) if var > 0 else 0.0
    return means, stds


def compute_positions(minutes, closes):
    mid, sd = _rolling_stats(closes, WINDOW)
    sma_long, _ = _rolling_stats(closes, SMA_LONG)
    upper = [None if mid[i] is None else mid[i] + K * sd[i]
             for i in range(len(closes))]
    lower = [None if mid[i] is None else mid[i] - K * sd[i]
             for i in range(len(closes))]

    positions = [0] * len(closes)
    cur = 0
    for t in range(1, len(closes)):
        # ONLY bar t-1 and earlier are read here -> no lookahead.
        i = t - 1
        if upper[i] is None or sma_long[i] is None:
            positions[t] = cur
            continue
        c = closes[i]
        if c > upper[i] and c > sma_long[i]:
            cur = 1
        elif c < lower[i] and c < sma_long[i]:
            cur = -1
        positions[t] = cur
    return positions


def main() -> None:
    bars_path = sys.argv[1] if len(sys.argv) > 1 else "bars.csv"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "positions.csv"
    minutes, closes = [], []
    with open(bars_path, newline="") as f:
        for row in csv.DictReader(f):
            minutes.append(int(row["minute"]))
            closes.append(float(row["close"]))
    pos = compute_positions(minutes, closes)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["minute", "position"])
        for m, p in zip(minutes, pos):
            w.writerow([m, p])
    n_trades = sum(1 for a, b in zip([0] + pos, pos) if a != b)
    print(f"wrote {out_path}: {len(pos)} rows, "
          f"long bars={sum(1 for p in pos if p == 1)}, "
          f"short bars={sum(1 for p in pos if p == -1)}, "
          f"flat bars={sum(1 for p in pos if p == 0)}, fills={n_trades}")


if __name__ == "__main__":
    main()
