"""
Rigorous 35-Day Train / Out-of-Sample Backtest & Holm-Bonferroni Hypothesis Battery
Dataset: 50,400 continuous 1-minute BTCUSDT bars (Aug 25 to Sep 28, 2026)
Design:
- In-Sample (Train): Days 1 to 21 (30,240 bars)
- Out-of-Sample (Test): Days 22 to 35 (20,160 bars) - STRICTLY RUN ONCE
- Fixed Hypotheses:
    Entry: |Z| > 2.0 (against 20-bar rolling VWAP)
    Filter: Kaufman ER <= 0.38
    Horizons: 3m, 5m, 15m
    Hurdle: Gross Edge >= 10.0 bps on 95% Bootstrap CI Lower Bound
- Statistical Tests:
    1,000 Circular Block Bootstrap iterations
    Holm-Bonferroni Family-Wise Error Rate (FWER) adjusted p-values
"""

import sys
import csv
import numpy as np

DATA_PATH = "D:/projects/QUANT/data/historical/BTCUSDT_1m_35d.csv"

def load_data(file_path=DATA_PATH):
    print(f"Loading 1m bar dataset from: {file_path}...")
    ts_list, o_list, h_list, l_list, c_list, v_list = [], [], [], [], [], []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) >= 6:
                try:
                    ts_list.append(float(row[0]))
                    o_list.append(float(row[1]))
                    h_list.append(float(row[2]))
                    l_list.append(float(row[3]))
                    c_list.append(float(row[4]))
                    v_list.append(float(row[5]))
                except ValueError:
                    continue
                    
    ts = np.array(ts_list, dtype=np.float64)
    c = np.array(c_list, dtype=np.float64)
    v = np.array(v_list, dtype=np.float64)
    print(f"Loaded {len(c):,} continuous 1-minute bars ({len(c)/1440:.1f} days).")
    return ts, c, v

def compute_indicators(c, v, lookback=20):
    n = len(c)
    z_scores = np.zeros(n)
    er_scores = np.zeros(n)
    
    # 20-bar VWAP
    pv = c * v
    cum_pv = np.cumsum(pv)
    cum_vol = np.cumsum(v)
    vwap = np.zeros(n)
    
    for i in range(n):
        if i < lookback:
            vwap[i] = cum_pv[i] / cum_vol[i] if cum_vol[i] > 0 else c[i]
        else:
            p_slice = cum_pv[i] - cum_pv[i - lookback]
            v_slice = cum_vol[i] - cum_vol[i - lookback]
            vwap[i] = p_slice / v_slice if v_slice > 0 else c[i]
            
    devs = c - vwap
    
    # Rolling 20-bar Z-score of deviation
    for i in range(lookback, n):
        w_dev = devs[i - lookback + 1: i + 1]
        m = np.mean(w_dev)
        s = np.std(w_dev)
        z_scores[i] = (w_dev[-1] - m) / s if s > 1e-6 else 0.0
        
        # Kaufman ER over 20 bars
        w_c = c[i - lookback + 1: i + 1]
        net_change = abs(w_c[-1] - w_c[0])
        abs_diffs = np.sum(np.abs(w_c[1:] - w_c[:-1]))
        er_scores[i] = (net_change / abs_diffs) if abs_diffs > 1e-6 else 0.0
        
    return z_scores, er_scores

def block_bootstrap_ci(data: np.ndarray, block_size: int = 5, num_iter: int = 1000, alpha: float = 0.05):
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
    # One-sided p-value: probability true mean <= 0
    p_val_less_than_zero = (boot_means <= 0.0).mean()
    return ci_low, ci_high, p_val_less_than_zero

def evaluate_subset(c, z_scores, er_scores, start_idx, end_idx, subset_name=""):
    print("\n" + "=" * 100)
    print(f" SUBSET EVALUATION: {subset_name} (Bars {start_idx:,} to {end_idx:,} | { (end_idx-start_idx)/1440:.1f} days)")
    print("=" * 100)

    horizons = [3, 5, 15] # 3m, 5m, 15m
    z_thresh = 2.0
    er_thresh = 0.38
    spacing = 3 # 3-bar deduplication spacing
    
    for mode, filter_er in [("Raw Z > 2.0 (No ER Filter)", False), ("Filtered (Z > 2.0 AND ER <= 0.38)", True)]:
        print("\n" + "-" * 100)
        print(f"  STRATEGY MODE: {mode}")
        print("-" * 100)
        
        signals = [] # (idx, side, price)
        last_sig = -999
        
        for i in range(start_idx, end_idx - max(horizons)):
            z = z_scores[i]
            er = er_scores[i]
            
            if filter_er and er > er_thresh:
                continue
                
            if i - last_sig >= spacing:
                if z < -z_thresh:
                    signals.append((i, 1, c[i]))
                    last_sig = i
                elif z > z_thresh:
                    signals.append((i, -1, c[i]))
                    last_sig = i

        n_signals = len(signals)
        print(f"  Total Independent Trigger Events: {n_signals}")
        if n_signals < 5:
            print("  Insufficient signals.")
            continue

        raw_results = []
        for h in horizons:
            returns = []
            for s_idx, side, entry_p in signals:
                exit_p = c[s_idx + h]
                if side == 1:
                    bps = ((exit_p - entry_p) / entry_p) * 10_000.0
                else:
                    bps = ((entry_p - exit_p) / entry_p) * 10_000.0
                returns.append(bps)
                
            arr = np.array(returns)
            m = arr.mean()
            wr = (arr > 0).mean() * 100.0
            ci_low, ci_high, p_val = block_bootstrap_ci(arr, block_size=5, num_iter=1000)
            raw_results.append({
                "h": h,
                "n": len(arr),
                "wr": wr,
                "mean": m,
                "ci_low": ci_low,
                "ci_high": ci_high,
                "p_val": p_val
            })

        # Apply Holm-Bonferroni Correction across the 3 hypotheses
        # Sort by p_val ascending
        raw_results.sort(key=lambda x: x["p_val"])
        m_tests = len(raw_results)
        for rank, res in enumerate(raw_results):
            # Holm multiplier: (m - rank)
            holm_p = min(1.0, res["p_val"] * (m_tests - rank))
            res["holm_p"] = holm_p

        # Re-sort by horizon for presentation
        raw_results.sort(key=lambda x: x["h"])

        print(f"  {'Horizon':<8} | {'Trades':<7} | {'WinRate':<8} | {'Mean Gross':<12} | {'95% Block Bootstrap CI':<24} | {'Net (8bps)':<11} | {'Raw p':<8} | {'Holm p':<8}")
        print("  " + "-" * 96)
        for res in raw_results:
            h_str = f"{res['h']}m"
            ci_str = f"[{res['ci_low']:>+6.1f}, {res['ci_high']:>+6.1f}] bps"
            net_8 = res['mean'] - 8.0
            print(f"  {h_str:<8} | {res['n']:<7} | {res['wr']:>5.1f}%  | {res['mean']:>+7.2f} bps  | {ci_str:<24} | {net_8:>+7.2f} bps | {res['p_val']:>6.3f}   | {res['holm_p']:>6.3f}")

def run_experiment():
    ts, c, v = load_data()
    print("Computing 20-bar VWAP, Z-score, and Kaufman ER on all 50,400 bars...")
    z_scores, er_scores = compute_indicators(c, v, lookback=20)
    
    # Train: First 21 days (30,240 bars)
    train_bars = 21 * 1440
    evaluate_subset(c, z_scores, er_scores, 20, train_bars, "TRAIN (IN-SAMPLE: Days 1-21)")
    
    # Test: Days 22 to 35 (20,160 bars) - STRICT OUT-OF-SAMPLE
    evaluate_subset(c, z_scores, er_scores, train_bars, len(c), "TEST (STRICT OUT-OF-SAMPLE: Days 22-35)")

if __name__ == "__main__":
    run_experiment()
