"""
Forward-Return Measurement & Latency-Shifted Backtest Harness
Strictly measures:
1. Signal generation at T0 (when |Z| > threshold with / without ER & CVD filters)
2. Entry execution at T0 + latency_ms (default 150ms) with adverse spread slippage
3. Forward returns at multiple holding horizons: 1s, 5s, 15s, 30s, 60s, 300s (5m)
4. Gross return vs Net return after Binance retail fee hurdle (8 bps and 10 bps round trip)
"""

import sys
import csv
import numpy as np

TICKS_PATH = "D:/projects/QUANT/data/live_ticks.csv"

def run_forward_return_harness(
    file_path: str = TICKS_PATH,
    sample_size: int = 50_000,
    latency_sec: float = 0.150, # 150 ms network + processing latency
    z_threshold: float = 2.0,
    fee_bps: float = 8.0, # 8 bps = 0.08% round trip taker
    horizons_sec = [1.0, 5.0, 15.0, 30.0, 60.0, 300.0]
):
    print("=" * 80)
    print(" EMPIRICAL FORWARD RETURN & FEE HURDLE HARNESS")
    print(f" Sample Size: Last {sample_size:,} ticks | Latency Shift: {latency_sec*1000:.0f} ms | Fee Hurdle: {fee_bps:.1f} bps")
    print("=" * 80)

    # 1. Load data
    print(f"Loading data from {file_path}...")
    ts_list, price_list, vol_list = [], [], []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) >= 4:
                try:
                    ts_list.append(float(row[0]))
                    price_list.append(float(row[2]))
                    vol_list.append(float(row[3]))
                except ValueError:
                    continue

    if len(price_list) == 0:
        print("Error: No ticks loaded.")
        return

    ts = np.array(ts_list[-sample_size:], dtype=np.float64)
    price = np.array(price_list[-sample_size:], dtype=np.float64)
    vol = np.array(vol_list[-sample_size:], dtype=np.float64)
    n = len(price)

    # 2. Recompute incremental indicators strictly: VWAP, EWMA Sigma, Z-score, Kaufman ER
    print("Computing O(1) microstructure indicators (VWAP, EWMA Sigma, Kaufman ER)...")
    z_scores = np.zeros(n)
    er_scores = np.zeros(n)
    
    # 300-tick VWAP
    window = 300
    pv = price * vol
    cum_pv = np.cumsum(pv)
    cum_vol = np.cumsum(vol)
    
    # Fast rolling VWAP
    vwap = np.zeros(n)
    for i in range(n):
        if i < window:
            vwap[i] = cum_pv[i] / cum_vol[i] if cum_vol[i] > 0 else price[i]
        else:
            p_slice = cum_pv[i] - cum_pv[i - window]
            v_slice = cum_vol[i] - cum_vol[i - window]
            vwap[i] = p_slice / v_slice if v_slice > 0 else price[i]

    # EWMA Sigma & Z-Score
    ewma_var = 1.0
    lambda_var = 0.96
    devs = price - vwap
    for i in range(n):
        dev = devs[i]
        if i == 0:
            ewma_var = max(dev * dev, 1e-4)
        else:
            ewma_var = lambda_var * ewma_var + (1.0 - lambda_var) * (dev * dev)
        sigma = np.sqrt(max(ewma_var, 1e-6))
        z_scores[i] = dev / sigma

    # Kaufman ER (20-tick lookback)
    er_win = 20
    abs_diffs = np.zeros(n)
    abs_diffs[1:] = np.abs(price[1:] - price[:-1])
    diff_sum = 0.0
    for i in range(n):
        diff_sum += abs_diffs[i]
        if i >= er_win:
            diff_sum -= abs_diffs[i - er_win]
            net_change = abs(price[i] - price[i - er_win])
            er_scores[i] = (net_change / diff_sum) if diff_sum > 1e-6 else 0.0

    # 3. Detect signals:
    # A: Raw Z-Score Fade (Unfiltered)
    # B: Filtered Fade (Z-Score + ER <= 0.38 Regime Filter)
    
    for filter_name, use_er_filter in [("Unfiltered (Raw Z > 2.0)", False), ("Filtered (Z > 2.0 AND ER <= 0.38)", True)]:
        print("\n" + "-" * 80)
        print(f" STRATEGY VARIANT: {filter_name}")
        print("-" * 80)

        signals = [] # tuples: (idx, ts, side, price)
        # 1: Long (fade oversold Z < -threshold), -1: Short (fade overbought Z > threshold)
        for i in range(window, n - 1):
            z = z_scores[i]
            er = er_scores[i]
            
            if use_er_filter and er > 0.38:
                continue # ER Trend Veto
                
            if z < -z_threshold:
                signals.append((i, ts[i], 1, price[i])) # Propose Long
            elif z > z_threshold:
                signals.append((i, ts[i], -1, price[i])) # Propose Short

        if not signals:
            print("No signals generated.")
            continue

        print(f"Total Raw Trigger Events: {len(signals)}")
        
        # Enforce minimum trade spacing (cooldown 5s) to avoid clustering on the same tick spike
        pruned_signals = []
        last_t = -999.0
        for sig in signals:
            if sig[1] - last_t >= 5.0:
                pruned_signals.append(sig)
                last_t = sig[1]

        print(f"Independent Signal Events (5s spacing): {len(pruned_signals)}")
        print(f"{'Horizon':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Gross Return':<14} | {'Net Return (8bps)':<18} | {'Net Return (10bps)':<18}")
        print("-" * 88)

        for h in horizons_sec:
            returns_gross = []
            
            for sig_idx, sig_t, side, sig_price in pruned_signals:
                # Find execution tick at sig_t + latency_sec
                fill_t = sig_t + latency_sec
                # Find next tick with timestamp >= fill_t
                fill_indices = np.where((ts >= fill_t) & (np.arange(n) > sig_idx))[0]
                if len(fill_indices) == 0:
                    continue
                fill_idx = fill_indices[0]
                fill_price = price[fill_idx]
                
                # Adverse fill simulation: 0.5 tick spread penalty
                slippage = 0.50 # $0.50 spread penalty on BTC
                if side == 1:
                    actual_entry = fill_price + slippage
                else:
                    actual_entry = fill_price - slippage

                # Exit at horizon T_fill + h
                exit_t = fill_t + h
                exit_indices = np.where(ts >= exit_t)[0]
                if len(exit_indices) == 0:
                    continue
                exit_idx = exit_indices[0]
                actual_exit = price[exit_idx]
                
                # Gross return in bps
                if side == 1:
                    bps_gross = ((actual_exit - actual_entry) / actual_entry) * 10_000.0
                else:
                    bps_gross = ((actual_entry - actual_exit) / actual_entry) * 10_000.0
                    
                returns_gross.append(bps_gross)

            if len(returns_gross) == 0:
                continue

            arr = np.array(returns_gross)
            trades_cnt = len(arr)
            win_rate = (arr > 0).mean() * 100.0
            avg_gross_bps = arr.mean()
            avg_net_8bps = avg_gross_bps - 8.0
            avg_net_10bps = avg_gross_bps - 10.0

            print(f"{h:<8.1f}s | {trades_cnt:<8} | {win_rate:>6.1f}%    | {avg_gross_bps:>+8.2f} bps    | {avg_net_8bps:>+10.2f} bps      | {avg_net_10bps:>+10.2f} bps")

    print("=" * 80)

if __name__ == "__main__":
    run_forward_return_harness()
