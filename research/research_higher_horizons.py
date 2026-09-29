"""
Higher-Horizon (1m, 5m, 15m) Mean Reversion & Block-Bootstrap Statistical Harness
Evaluates:
1. Bar aggregation from raw ticks (1m and 5m bars)
2. Mean Reversion Signals: Bar Z-Score vs Rolling VWAP (window 20 bars)
3. Kaufman Efficiency Ratio (ER) regime filter
4. Forward Returns at 1 bar, 3 bars, 5 bars, 12 bars (e.g., 5m, 15m, 25m, 60m)
5. 1,000-iteration Block-Bootstrap to compute 95% Confidence Interval & p-value vs Fee Hurdle (8 bps)
"""

import sys
import csv
import numpy as np

TICKS_PATH = "D:/projects/QUANT/data/live_ticks.csv"

def resample_ticks_to_bars(file_path: str, bar_seconds: float = 60.0):
    print(f"Resampling raw ticks from {file_path} into {bar_seconds:.0f}s bars...")
    bars = []
    
    current_bar_start = None
    b_open = b_high = b_low = b_close = 0.0
    b_vol = 0.0
    b_pv = 0.0
    
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        _ = next(reader, None) # skip header
        for row in reader:
            if len(row) < 4:
                continue
            try:
                t = float(row[0])
                p = float(row[2])
                v = float(row[3])
            except ValueError:
                continue
                
            bar_bucket = int(t // bar_seconds) * bar_seconds
            
            if current_bar_start is None:
                current_bar_start = bar_bucket
                b_open = b_high = b_low = b_close = p
                b_vol = v
                b_pv = p * v
            elif bar_bucket == current_bar_start:
                if p > b_high: b_high = p
                if p < b_low: b_low = p
                b_close = p
                b_vol += v
                b_pv += p * v
            else:
                # Close current bar
                vwap = b_pv / b_vol if b_vol > 0 else b_close
                bars.append({
                    "time": current_bar_start,
                    "open": b_open, "high": b_high, "low": b_low, "close": b_close,
                    "volume": b_vol, "vwap": vwap
                })
                # Advance to next bar
                current_bar_start = bar_bucket
                b_open = b_high = b_low = b_close = p
                b_vol = v
                b_pv = p * v
                
        if current_bar_start is not None and b_vol > 0:
            bars.append({
                "time": current_bar_start,
                "open": b_open, "high": b_high, "low": b_low, "close": b_close,
                "volume": b_vol, "vwap": b_pv / b_vol
            })
            
    print(f"Generated {len(bars)} continuous {bar_seconds:.0f}s bars.")
    return bars

def block_bootstrap_ci(data: np.ndarray, block_size: int = 5, num_iter: int = 1000, alpha: float = 0.05):
    """Circular Block Bootstrap for dependent / serially correlated trade returns."""
    n = len(data)
    if n < 5:
        return np.nan, np.nan, np.nan
        
    num_blocks = int(np.ceil(n / block_size))
    boot_means = []
    
    for _ in range(num_iter):
        start_indices = np.random.randint(0, n, size=num_blocks)
        sampled = []
        for idx in start_indices:
            block = [data[(idx + i) % n] for i in range(block_size)]
            sampled.extend(block)
        sample = np.array(sampled[:n])
        boot_means.append(sample.mean())
        
    boot_means = np.array(boot_means)
    ci_low = np.percentile(boot_means, (alpha / 2.0) * 100.0)
    ci_high = np.percentile(boot_means, (1.0 - alpha / 2.0) * 100.0)
    p_val_above_zero = (boot_means <= 0.0).mean() # probability true mean <= 0
    return ci_low, ci_high, p_val_above_zero

def run_higher_horizon_analysis(bar_seconds: float = 60.0, z_thresh: float = 2.0, er_thresh: float = 0.38):
    bars = resample_ticks_to_bars(TICKS_PATH, bar_seconds)
    n = len(bars)
    if n < 30:
        print("Insufficient bars for statistical validity.")
        return

    closes = np.array([b["close"] for b in bars])
    vwaps = np.array([b["vwap"] for b in bars])
    
    # 20-bar rolling VWAP & Standard Deviation
    lookback = 20
    z_scores = np.zeros(n)
    er_scores = np.zeros(n)
    
    for i in range(lookback, n):
        win_closes = closes[i - lookback + 1: i + 1]
        win_vwaps = vwaps[i - lookback + 1: i + 1]
        devs = win_closes - win_vwaps
        mean_dev = np.mean(devs)
        std_dev = np.std(devs)
        z_scores[i] = (devs[-1] - mean_dev) / std_dev if std_dev > 1e-6 else 0.0
        
        # Kaufman ER over lookback
        net_change = abs(win_closes[-1] - win_closes[0])
        abs_diffs = np.sum(np.abs(win_closes[1:] - win_closes[:-1]))
        er_scores[i] = (net_change / abs_diffs) if abs_diffs > 1e-6 else 0.0

    horizons_bars = [1, 2, 3, 5, 10]
    
    print("\n" + "=" * 96)
    print(f" HIGHER-HORIZON ANALYSIS ({bar_seconds:.0f}s BARS) | Lookback: {lookback} bars | Z Cutoff: {z_thresh}")
    print("=" * 96)

    for mode, filter_er in [("Raw (No ER Filter)", False), (f"Filtered (ER <= {er_thresh})", True)]:
        print("\n" + "-" * 96)
        print(f" MODE: {mode}")
        print("-" * 96)

        # Detect signals and deduplicate within 3 bars
        signals = []
        last_sig_idx = -999
        for i in range(lookback, n - max(horizons_bars)):
            z = z_scores[i]
            er = er_scores[i]
            if filter_er and er > er_thresh:
                continue
                
            if i - last_sig_idx >= 3: # 3-bar deduplication spacing
                if z < -z_thresh:
                    signals.append((i, 1, closes[i])) # Propose Long
                    last_sig_idx = i
                elif z > z_thresh:
                    signals.append((i, -1, closes[i])) # Propose Short
                    last_sig_idx = i

        if len(signals) == 0:
            print("Zero signals generated in this timeframe.")
            continue

        print(f"Total Independent Signals: {len(signals)}")
        print(f"{'Horizon':<10} | {'Trades':<7} | {'Win Rate':<9} | {'Mean Gross':<12} | {'95% Block Bootstrap CI':<24} | {'Net (8bps)':<11} | {'p(H0:<=0)':<10}")
        print("-" * 96)

        for h in horizons_bars:
            returns = []
            for sig_idx, side, entry_p in signals:
                exit_idx = sig_idx + h
                if exit_idx >= n:
                    continue
                exit_p = closes[exit_idx]
                if side == 1:
                    bps = ((exit_p - entry_p) / entry_p) * 10_000.0
                else:
                    bps = ((entry_p - exit_p) / entry_p) * 10_000.0
                returns.append(bps)

            if len(returns) == 0:
                continue

            arr = np.array(returns)
            m = arr.mean()
            wr = (arr > 0).mean() * 100.0
            ci_low, ci_high, p_val = block_bootstrap_ci(arr, block_size=3, num_iter=1000)
            net_8 = m - 8.0

            ci_str = f"[{ci_low:>+6.1f}, {ci_high:>+6.1f}] bps"
            h_str = f"{h} bars ({(h * bar_seconds) / 60:.1f}m)"

            print(f"{h_str:<10} | {len(arr):<7} | {wr:>5.1f}%   | {m:>+7.2f} bps  | {ci_str:<24} | {net_8:>+7.2f} bps | {p_val:>8.3f}")

if __name__ == "__main__":
    # Test on 60s (1m) bars
    run_higher_horizon_analysis(bar_seconds=60.0)
    # Test on 300s (5m) bars
    run_higher_horizon_analysis(bar_seconds=300.0)
