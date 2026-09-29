"""
Binance Perpetual Funding Rate & Basis Arbitrage Historical Research Harness
Analyzes historical 8-hour funding rates for BTCUSDT:
1. Long-term annualized funding yield (Cash-and-Carry: Long Spot + Short Perpetual)
2. Compounded APR vs Drawdown during negative funding spikes
3. Fee hurdle analysis:
   - 2 legs × 2 (entry + exit) = 4 execution fees
   - Spot taker (0.04% - 0.10%) + Perp taker (0.02% - 0.05%)
   - Minimum holding period required to clear fee drag
"""

import sys
import json
import urllib.request
import numpy as np
import datetime

FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1000"

def fetch_funding_history():
    print("=" * 80)
    print(" FETCHING BINANCE PERPETUAL FUNDING RATE HISTORY (BTCUSDT)")
    print("=" * 80)
    
    # Binance returns up to 1000 records (~333 days of 8-hour funding intervals)
    req = urllib.request.Request(
        FUNDING_URL,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        
    print(f"Ingested {len(data)} funding intervals (approx {len(data)/3:.1f} days / {len(data)/(3*30):.1f} months).")
    return data

def analyze_cash_and_carry(data):
    # data: [{'symbol': 'BTCUSDT', 'fundingTime': 179..., 'fundingRate': '0.00010000', ...}]
    times = []
    rates = []
    for item in data:
        times.append(item["fundingTime"] / 1000.0)
        rates.append(float(item["fundingRate"]))
        
    rates = np.array(rates)
    times = np.array(times)
    n = len(rates)
    
    # 8-hour interval = 3 intervals per day = 3 * 365 = 1095 intervals per year
    intervals_per_year = 3 * 365
    
    mean_rate_8h = rates.mean()
    median_rate_8h = np.median(rates)
    std_rate_8h = rates.std()
    
    annualized_simple_apr = mean_rate_8h * intervals_per_year * 100.0
    compounded_apy = ((1.0 + mean_rate_8h) ** intervals_per_year - 1.0) * 100.0
    
    pos_intervals = (rates > 0).sum()
    neg_intervals = (rates < 0).sum()
    zero_intervals = (rates == 0).sum()
    
    # Cumulative funding return curve
    cum_return = np.cumsum(rates)
    peak = np.maximum.accumulate(cum_return)
    drawdown = cum_return - peak
    max_dd_bps = abs(drawdown.min()) * 10_000.0
    
    print("\n" + "=" * 80)
    print(" CASH-AND-CARRY STRUCTURAL YIELD AUDIT (LONG SPOT + SHORT PERP)")
    print("=" * 80)
    print(f"Total Evaluated Intervals : {n} ({n/3:.1f} days)")
    print(f"Positive Funding Intervals: {pos_intervals} ({pos_intervals/n*100:.1f}%) [Longs pay Shorts]")
    print(f"Negative Funding Intervals: {neg_intervals} ({neg_intervals/n*100:.1f}%) [Shorts pay Longs]")
    print(f"Neutral Funding Intervals : {zero_intervals} ({zero_intervals/n*100:.1f}%)")
    print("-" * 80)
    print(f"Average 8h Funding Rate   : {mean_rate_8h*10_000:>+.2f} bps ({mean_rate_8h*100:.4f}%)")
    print(f"Median 8h Funding Rate    : {median_rate_8h*10_000:>+.2f} bps ({median_rate_8h*100:.4f}%)")
    print(f"Std Dev 8h Funding Rate   : {std_rate_8h*10_000:>.2f} bps")
    print(f"Unlevered Simple APR      : {annualized_simple_apr:>+.2f}%")
    print(f"Compounded APY            : {compounded_apy:>+.2f}%")
    print(f"Max Funding Drawdown      : {max_dd_bps:.2f} bps")
    print("-" * 80)
    
    # Fee Hurdle Calculation
    # Spot round-trip taker: 2 x 0.075% (or 0.04% VIP) = 8-15 bps
    # Perp round-trip taker: 2 x 0.04% = 8 bps
    # Total round-trip entry + exit hurdle = ~16 to 23 bps
    print("FEE HURDLE & BREAK-EVEN ANALYSIS:")
    for fee_hurdle_bps in [12.0, 16.0, 20.0, 24.0]:
        # Average days needed to clear hurdle
        avg_bps_per_day = mean_rate_8h * 3.0 * 10_000.0
        breakeven_days = fee_hurdle_bps / avg_bps_per_day if avg_bps_per_day > 0 else np.nan
        print(f"  Fee Hurdle: {fee_hurdle_bps:4.1f} bps | Daily Yield: {avg_bps_per_day:+.2f} bps/day | Break-even Horizon: {breakeven_days:4.1f} days")

if __name__ == "__main__":
    data = fetch_funding_history()
    analyze_cash_and_carry(data)
