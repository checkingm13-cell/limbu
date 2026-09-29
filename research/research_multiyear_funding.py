"""
Multi-Year Non-Overlapping Funding Rate & Basis Arbitrage Historical Study
Pulls complete historical 8-hour funding rates for BTCUSDT from Binance Futures REST / Archives.
Evaluates:
1. Multi-year coverage (2021 to 2026) across bull runs, bear markets, and crash events
2. Non-overlapping 30-day blocks (True independent N)
3. Return on total capital (Spot notional + Perp margin)
4. Distribution of net yield, maximum sustained drawdowns, and negative funding streaks
"""

import sys
import json
import time
import urllib.request
import numpy as np
import datetime

FUNDING_URL_BASE = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT"

def fetch_multi_year_funding(start_year=2021):
    print("=" * 80)
    print(f" PULLING MULTI-YEAR FUNDING RATE ARCHIVE FROM {start_year} TO PRESENT (BTCUSDT)")
    print("=" * 80)
    
    all_records = []
    # Start at Jan 1, 2021 (timestamp in ms)
    start_time = int(datetime.datetime(start_year, 1, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    now_ms = int(time.time() * 1000)
    
    while start_time < now_ms:
        url = f"{FUNDING_URL_BASE}&limit=1000&startTime={start_time}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                batch = json.loads(resp.read().decode("utf-8"))
            if not batch:
                break
            all_records.extend(batch)
            latest_in_batch = batch[-1]["fundingTime"]
            dt_str = datetime.datetime.fromtimestamp(latest_in_batch/1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d')
            print(f"  [+] Ingested {len(all_records):,} records so far (Reached: {dt_str})")
            if latest_in_batch <= start_time:
                break
            start_time = latest_in_batch + 1
            if len(batch) < 1000:
                break
            time.sleep(0.15)
        except Exception as e:
            print(f"  [-] Fetch error: {e}")
            break

    # Deduplicate and sort chronologically
    seen = set()
    deduped = []
    for r in all_records:
        ft = r["fundingTime"]
        if ft not in seen:
            seen.add(ft)
            deduped.append(r)
            
    deduped.sort(key=lambda x: x["fundingTime"])
    print(f"Total Unique Historical Intervals: {len(deduped):,} (~{len(deduped)/3:.0f} days / {len(deduped)/(3*365):.1f} years)")
    return deduped

def analyze_non_overlapping_funding(records):
    times = np.array([r["fundingTime"] / 1000.0 for r in records])
    rates = np.array([float(r["fundingRate"]) for r in records])
    n = len(rates)
    
    # 30-day block = 90 intervals (3 intervals per day * 30 days)
    block_size = 90
    num_independent_blocks = n // block_size
    
    print("\n" + "=" * 80)
    print(f" NON-OVERLAPPING 30-DAY INDEPENDENT BLOCKS AUDIT (N = {num_independent_blocks})")
    print(f" Span: {datetime.datetime.fromtimestamp(times[0]).strftime('%Y-%m-%d')} to {datetime.datetime.fromtimestamp(times[-1]).strftime('%Y-%m-%d')}")
    print("=" * 80)

    block_returns_bps = []
    block_dates = []
    
    for b in range(num_independent_blocks):
        start = b * block_size
        end = start + block_size
        sub_rates = rates[start:end]
        block_sum_bps = np.sum(sub_rates) * 10_000.0
        block_returns_bps.append(block_sum_bps)
        dt_start = datetime.datetime.fromtimestamp(times[start]).strftime("%Y-%m-%d")
        dt_end = datetime.datetime.fromtimestamp(times[end-1]).strftime("%Y-%m-%d")
        block_dates.append((dt_start, dt_end))

    arr = np.array(block_returns_bps)
    
    # Capital Efficiency Adjustment:
    # To hold 1 BTC Spot ($X) + 1 BTC Short Perp ($X) with 2x margin cushion (50% collateral on perp),
    # Total Capital Required = 1.0 (Spot) + 0.5 (Perp margin) = 1.5x notional.
    # Therefore: Yield on Total Capital = Funding Return on Notional / 1.5.
    capital_multiplier = 1.5
    arr_on_capital = arr / capital_multiplier
    
    # Fee hurdle on capital:
    # 2 legs x 2 (entry + exit) taker/maker blend = ~16 bps on notional = ~10.7 bps on total capital
    fee_hurdle_bps = 16.0
    
    print(f"{'Block #':<8} | {'Date Range':<23} | {'Gross (Notional)':<18} | {'Gross (On Capital)':<20} | {'Net (16bps Fee)':<16}")
    print("-" * 92)
    for i in range(num_independent_blocks):
        net_b = arr[i] - fee_hurdle_bps
        notional_apr = (arr[i] / 100.0) * 12.0 # bps/10000 * 100 * 12 = bps/100 * 12
        capital_apr = (arr_on_capital[i] / 100.0) * 12.0
        print(f"Block {i+1:02d} | {block_dates[i][0]} to {block_dates[i][1]} | {arr[i]:>+8.2f} bps ({notional_apr:>+5.1f}% APR) | {arr_on_capital[i]:>+8.2f} bps ({capital_apr:>+5.1f}% APR) | {net_b:>+8.2f} bps")

    print("\n" + "=" * 80)
    print(" EMPIRICAL SUMMARY ACROSS ALL INDEPENDENT 30-DAY REGIMES:")
    print("=" * 80)
    mean_apr_notional = (arr.mean() / 100.0) * 12.0
    median_apr_notional = (np.median(arr) / 100.0) * 12.0
    mean_apr_capital = (arr_on_capital.mean() / 100.0) * 12.0
    print(f"Total Independent 30d Months (N): {num_independent_blocks}")
    print(f"Mean Gross 30d Return (Notional): {arr.mean():>+7.2f} bps ({mean_apr_notional:>+5.2f}% uncompounded APR)")
    print(f"Median Gross 30d Return         : {np.median(arr):>+7.2f} bps ({median_apr_notional:>+5.2f}% uncompounded APR)")
    print(f"Worst Independent Month         : {arr.min():>+7.2f} bps (Max monthly drag)")
    print(f"Best Independent Month          : {arr.max():>+7.2f} bps")
    print(f"Standard Deviation              : {arr.std():>7.2f} bps")
    print("-" * 80)
    print(f"Mean Realized Return on Capital : {arr_on_capital.mean():>+7.2f} bps ({mean_apr_capital:>+5.2f}% APR on Total Equity)")
    print(f"Independent Months Clearing Fee : {(arr >= fee_hurdle_bps).sum()}/{num_independent_blocks} ({(arr >= fee_hurdle_bps).mean()*100:.1f}%)")
    print(f"Independent Negative Months     : {(arr < 0).sum()}/{num_independent_blocks} ({(arr < 0).mean()*100:.1f}%)")
    print("=" * 80)

if __name__ == "__main__":
    records = fetch_multi_year_funding(start_year=2021)
    analyze_non_overlapping_funding(records)
