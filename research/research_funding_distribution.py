"""
Rolling 30-Day Funding Distribution & Regime Vulnerability Analysis
Evaluates:
1. Rolling 30-day funding yield sum (annualized) across all 500 intervals
2. Historical probability of breaking even vs fee hurdle (16 bps)
3. Worst 30-day funding drought / negative regime
"""

import json
import urllib.request
import numpy as np

FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1000"

def run_funding_distribution():
    req = urllib.request.Request(FUNDING_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        
    rates = np.array([float(x["fundingRate"]) for x in data])
    # 30 days = 90 intervals of 8h
    win = 90
    n = len(rates)
    
    if n < win:
        print("Insufficient history.")
        return
        
    rolling_30d_sums = []
    for i in range(win, n + 1):
        # Sum of 30-day funding in bps
        r_sum_bps = np.sum(rates[i - win: i]) * 10_000.0
        rolling_30d_sums.append(r_sum_bps)
        
    arr = np.array(rolling_30d_sums)
    fee_hurdle_bps = 16.0 # 2 legs x 2 trades taker/maker blend
    
    print("=" * 80)
    print(f" ROLLING 30-DAY CASH-AND-CARRY FUNDING DISTRIBUTION ({len(arr)} ROLLING WINDOWS)")
    print("=" * 80)
    print(f"Mean 30-Day Funding Return   : {arr.mean():>+6.2f} bps ({arr.mean()*12:>+5.2f}% uncompounded APR)")
    print(f"Median 30-Day Funding Return : {np.median(arr):>+6.2f} bps")
    print(f"Worst 30-Day Funding Return  : {arr.min():>+6.2f} bps  [Severe Drought / Backwardation]")
    print(f"Best 30-Day Funding Return   : {arr.max():>+6.2f} bps")
    print(f"Std Dev of 30-Day Return     : {arr.std():>6.2f} bps")
    print("-" * 80)
    
    p_breakeven = (arr >= fee_hurdle_bps).mean() * 100.0
    p_loss = (arr < 0).mean() * 100.0
    print(f"Probability of Clearing {fee_hurdle_bps} bps Fee in 30 Days : {p_breakeven:>5.1f}%")
    print(f"Probability of Negative Funding (Shorts pay Longs) in 30 Days: {p_loss:>5.1f}%")
    print("=" * 80)

if __name__ == "__main__":
    run_funding_distribution()
