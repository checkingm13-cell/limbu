"""
HISTORICAL BACKTESTING ENGINE: BTC/USDT MEAN REVERSION (VWAP + Z-SCORE)
========================================================================
Fetches real 1,000 historical 1-minute candles from Binance REST API,
runs the quantitative mean reversion strategy, computes accuracy/win rate,
profit factor, maximum drawdown, and generates a visual performance graph.

Run:
    python D:/projects/QUANT/backtest_mean_reversion.py
"""

import json
import math
import urllib.request
import time
import os
import sys

# Configure UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import matplotlib.pyplot as plt
import numpy as np


# =====================================================================
# 1. FETCH HISTORICAL BARS FROM BINANCE PUBLIC REST API
# =====================================================================

def fetch_binance_klines(symbol="BTCUSDT", interval="1m", limit=1000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}&interval={interval}&limit={limit}"
    print(f"Fetching {limit} historical {interval} candles for {symbol} from Binance API...")
    
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw_data = json.loads(response.read().decode())
    except Exception as e:
        print(f"Network error fetching from Binance: {e}. Generating realistic synthetic data instead.")
        return generate_synthetic_data(limit)

    bars = []
    for item in raw_data:
        # Binance kline format: [open_time, open, high, low, close, volume, close_time, quote_vol, trades, ...]
        t_open = int(item[0]) / 1000.0
        o = float(item[1])
        h = float(item[2])
        l = float(item[3])
        c = float(item[4])
        v = float(item[5])
        bars.append({
            "timestamp": t_open,
            "time_str": time.strftime("%H:%M", time.localtime(t_open)),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
            "typical_price": (h + l + c) / 3.0
        })
    print(f"Successfully loaded {len(bars)} historical candles.")
    return bars


def generate_synthetic_data(n=1000):
    np.random.seed(42)
    base = 83000.0
    prices = [base]
    bars = []
    cur_time = time.time() - (n * 60)
    for i in range(n):
        pull = 0.05 * (base - prices[-1])
        ret = np.random.normal(pull, 12.0)
        p = prices[-1] + ret
        prices.append(p)
        h = p + abs(np.random.normal(0, 5))
        l = p - abs(np.random.normal(0, 5))
        v = float(np.random.uniform(10, 100))
        bars.append({
            "timestamp": cur_time + i * 60,
            "time_str": time.strftime("%H:%M", time.localtime(cur_time + i * 60)),
            "open": p,
            "high": h,
            "low": l,
            "close": p,
            "volume": v,
            "typical_price": (h + l + p) / 3.0
        })
    return bars


# =====================================================================
# 2. RUN SYSTEMATIC BACKTEST
# =====================================================================

def run_backtest(bars, lookback=20, entry_z=2.0, exit_z=0.5, stop_loss_pct=0.0015):
    print("\nRunning backtest simulation...")
    
    n = len(bars)
    closes = np.array([b["close"] for b in bars])
    volumes = np.array([b["volume"] for b in bars])
    typical_prices = np.array([b["typical_price"] for b in bars])
    
    # Calculate Rolling VWAP (over lookback * 3 window to create an anchor)
    vwap_window = lookback * 3
    vwap = np.zeros(n)
    for i in range(n):
        start_idx = max(0, i - vwap_window + 1)
        pv = np.sum(typical_prices[start_idx:i+1] * volumes[start_idx:i+1])
        vol = np.sum(volumes[start_idx:i+1])
        vwap[i] = pv / vol if vol > 0 else closes[i]

    # Calculate Deviation and Rolling Z-Score
    deviations = closes - vwap
    z_scores = np.zeros(n)
    upper_band = np.full(n, np.nan)
    lower_band = np.full(n, np.nan)

    for i in range(lookback, n):
        win_dev = deviations[i - lookback + 1 : i + 1]
        std = np.std(win_dev)
        if std > 1e-8:
            z_scores[i] = (deviations[i] - np.mean(win_dev)) / std
            upper_band[i] = vwap[i] + entry_z * std
            lower_band[i] = vwap[i] - entry_z * std
        else:
            z_scores[i] = 0.0
            upper_band[i] = vwap[i]
            lower_band[i] = vwap[i]

    # Trend Filter: 14-period EMA slope
    ema = np.zeros(n)
    ema[0] = closes[0]
    alpha = 2.0 / (14 + 1)
    for i in range(1, n):
        ema[i] = alpha * closes[i] + (1 - alpha) * ema[i - 1]
    
    ema_slope = np.zeros(n)
    for i in range(1, n):
        ema_slope[i] = ema[i] - ema[i - 1]

    # Backtest Execution Loop
    position = 0 # +1 Long, -1 Short, 0 Flat
    entry_price = 0.0
    entry_idx = 0
    
    trades = []
    buy_signals = []   # (idx, price)
    sell_signals = []  # (idx, price)
    exit_signals = []  # (idx, price, pnl)
    equity_curve = [10000.0] # Starting Capital $10,000 USD
    current_equity = 10000.0
    
    for i in range(lookback + 5, n):
        p = closes[i]
        z = z_scores[i]
        slope = ema_slope[i]
        
        # Determine Regime
        is_bull = slope > 3.0
        is_bear = slope < -3.0

        if position == 0:
            # Entry rules with regime filters
            if z < -entry_z and not is_bear:
                position = 1
                entry_price = p
                entry_idx = i
                buy_signals.append((i, p))
            elif z > entry_z and not is_bull:
                position = -1
                entry_price = p
                entry_idx = i
                sell_signals.append((i, p))
        else:
            # Position is Open: check exit conditions
            pnl_pts = (p - entry_price) if position == 1 else (entry_price - p)
            pnl_pct = pnl_pts / entry_price
            bars_held = i - entry_idx
            
            # Exit Conditions:
            # 1. Asymmetric Z-Score Mean Reversion: |Z| < 0.5
            # 2. Hard Stop Loss: hit stop_loss_pct (e.g. 0.15%)
            # 3. Time Stop: held for more than 15 bars without reverting
            is_exit = False
            exit_reason = ""
            
            if pnl_pct <= -stop_loss_pct:
                is_exit = True
                exit_reason = "STOP LOSS"
            elif abs(z) < exit_z:
                is_exit = True
                exit_reason = "MEAN EXIT"
            elif bars_held >= 15:
                is_exit = True
                exit_reason = "TIME STOP"

            if is_exit:
                # Simulated trade size: 0.1 BTC per trade
                trade_size_btc = 0.1
                dollar_pnl = pnl_pts * trade_size_btc
                current_equity += dollar_pnl
                trades.append({
                    "entry_idx": entry_idx,
                    "exit_idx": i,
                    "type": "LONG" if position == 1 else "SHORT",
                    "entry_price": entry_price,
                    "exit_price": p,
                    "pnl_pts": pnl_pts,
                    "pnl_pct": pnl_pct * 100.0,
                    "pnl_usd": dollar_pnl,
                    "reason": exit_reason,
                    "bars_held": bars_held
                })
                exit_signals.append((i, p, dollar_pnl))
                position = 0

        equity_curve.append(current_equity)

    return {
        "bars": bars,
        "closes": closes,
        "vwap": vwap,
        "upper_band": upper_band,
        "lower_band": lower_band,
        "z_scores": z_scores,
        "trades": trades,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "exit_signals": exit_signals,
        "equity_curve": equity_curve,
        "initial_capital": 10000.0,
        "final_capital": current_equity
    }


# =====================================================================
# 3. METRICS COMPUTATION (ACCURACY, PERCENTAGE, DRAWDOWN)
# =====================================================================

def calculate_metrics(results):
    trades = results["trades"]
    init_cap = results["initial_capital"]
    final_cap = results["final_capital"]
    
    total_trades = len(trades)
    if total_trades == 0:
        print("No trades generated during this period.")
        return None

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100.0  # ACCURACY
    
    gross_profit = sum(t["pnl_usd"] for t in wins)
    gross_loss = abs(sum(t["pnl_usd"] for t in losses))
    net_pnl = gross_profit - gross_loss
    total_return_pct = ((final_cap - init_cap) / init_cap) * 100.0
    
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
    
    avg_win = (gross_profit / win_count) if win_count else 0.0
    avg_loss = (gross_loss / loss_count) if loss_count else 0.0
    reward_risk_ratio = (avg_win / avg_loss) if avg_loss else 0.0

    # Maximum Drawdown calculation on equity curve
    equity = np.array(results["equity_curve"])
    peak = np.maximum.accumulate(equity)
    drawdowns = (peak - equity) / peak * 100.0
    max_drawdown_pct = np.max(drawdowns)

    metrics = {
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pnl": net_pnl,
        "total_return_pct": total_return_pct,
        "profit_factor": profit_factor,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "reward_risk_ratio": reward_risk_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "final_capital": final_cap
    }
    
    print("\n" + "=" * 65)
    print("           BACKTEST PERFORMANCE SCORECARD")
    print("=" * 65)
    print(f"  • Accuracy (Win Rate)    : {win_rate:.2f}%  ({win_count} Wins / {loss_count} Losses)")
    print(f"  • Total Return           : {total_return_pct:+.2f}%  (${net_pnl:+.2f} USD)")
    print(f"  • Profit Factor          : {profit_factor:.2f}")
    print(f"  • Total Trades           : {total_trades}")
    print(f"  • Average Win            : +${avg_win:.2f}")
    print(f"  • Average Loss           : -${avg_loss:.2f}")
    print(f"  • Reward-to-Risk Ratio   : {reward_risk_ratio:.2f}")
    print(f"  • Maximum Drawdown (DD)  : {max_drawdown_pct:.2f}%")
    print(f"  • Starting Capital       : ${init_cap:,.2f}")
    print(f"  • Ending Capital         : ${final_cap:,.2f}")
    print("=" * 65)
    
    return metrics


# =====================================================================
# 4. PLOT HIGH-RESOLUTION QUANT GRAPH
# =====================================================================

def plot_backtest_graph(results, metrics, output_path="D:/projects/QUANT/backtest_results.png"):
    print(f"\nGenerating visual performance graph -> {output_path}...")
    
    plt.style.use('dark_background')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), sharex=True, 
                                       gridspec_kw={'height_ratios': [3, 1.5, 2]})
    fig.patch.set_facecolor('#0B0F19')
    
    for ax in (ax1, ax2, ax3):
        ax.set_facecolor('#131B2E')
        ax.grid(True, color='#243256', linestyle='--', alpha=0.5)
        ax.tick_params(colors='#9CA3AF')
    
    closes = results["closes"]
    vwap = results["vwap"]
    upper = results["upper_band"]
    lower = results["lower_band"]
    x = np.arange(len(closes))
    
    # --- SUBPLOT 1: PRICE, VWAP & BANDS ---
    start_bar = 25
    ax1.plot(x[start_bar:], closes[start_bar:], color='#F3F4F6', label='BTC Price', linewidth=1.2)
    ax1.plot(x[start_bar:], vwap[start_bar:], color='#3B82F6', label='VWAP (Anchor)', linewidth=1.5)
    ax1.plot(x[start_bar:], upper[start_bar:], color='#EF4444', linestyle=':', label='+2σ Upper Band (Short Entry)', alpha=0.8)
    ax1.plot(x[start_bar:], lower[start_bar:], color='#10B981', linestyle=':', label='-2σ Lower Band (Long Entry)', alpha=0.8)
    ax1.fill_between(x[start_bar:], upper[start_bar:], lower[start_bar:], color='#3B82F6', alpha=0.06)
    
    # Auto-scale y-axis tightly around actual data
    valid_lows = lower[start_bar:][~np.isnan(lower[start_bar:])]
    valid_highs = upper[start_bar:][~np.isnan(upper[start_bar:])]
    if len(valid_lows) and len(valid_highs):
        ax1.set_ylim(np.min(valid_lows) - 30, np.max(valid_highs) + 30)
    
    # Plot Trade Signals
    for (idx, price) in results["buy_signals"]:
        ax1.scatter(idx, price, color='#10B981', marker='^', s=100, zorder=5, label='BUY (Long)' if idx == results["buy_signals"][0][0] else "")
    for (idx, price) in results["sell_signals"]:
        ax1.scatter(idx, price, color='#EF4444', marker='v', s=100, zorder=5, label='SELL (Short)' if idx == results["sell_signals"][0][0] else "")
    for (idx, price, pnl) in results["exit_signals"]:
        c = '#10B981' if pnl > 0 else '#EF4444'
        ax1.scatter(idx, price, color=c, marker='o', s=40, zorder=4)

    ax1.set_title(f"BTC/USDT Quantitative Mean Reversion (Win Rate: {metrics['win_rate']:.1f}% | Profit Factor: {metrics['profit_factor']:.2f})", 
                  fontsize=14, fontweight='bold', color='#10B981', pad=12)
    ax1.set_ylabel("Price ($ USD)", color='#9CA3AF')
    ax1.legend(loc='upper left', facecolor='#0B0F19', edgecolor='#243256', fontsize=9)
    
    # --- SUBPLOT 2: Z-SCORE OSCILLATOR ---
    z = results["z_scores"]
    ax2.plot(x, z, color='#8B5CF6', label='Deviation Z-Score', linewidth=1.2)
    ax2.axhline(2.0, color='#EF4444', linestyle='--', alpha=0.7, label='Entry (+2.0)')
    ax2.axhline(-2.0, color='#10B981', linestyle='--', alpha=0.7, label='Entry (-2.0)')
    ax2.axhline(0.5, color='#F59E0B', linestyle=':', alpha=0.5, label='Exit (+0.5)')
    ax2.axhline(-0.5, color='#F59E0B', linestyle=':', alpha=0.5, label='Exit (-0.5)')
    ax2.axhline(0.0, color='#6B7280', linestyle='-', alpha=0.3)
    ax2.fill_between(x, z, 2.0, where=(z >= 2.0), color='#EF4444', alpha=0.25)
    ax2.fill_between(x, z, -2.0, where=(z <= -2.0), color='#10B981', alpha=0.25)
    ax2.set_ylabel("Z-Score (σ)", color='#9CA3AF')
    ax2.set_ylim(-4, 4)
    ax2.legend(loc='upper right', facecolor='#0B0F19', edgecolor='#243256', fontsize=8, ncol=2)

    # --- SUBPLOT 3: EQUITY GROWTH CURVE ---
    equity = np.array(results["equity_curve"])
    eq_x = np.linspace(0, len(closes)-1, len(equity))
    ax3.plot(eq_x, equity, color='#10B981' if metrics['net_pnl'] >= 0 else '#EF4444', linewidth=2.0, label='Portfolio Equity ($)')
    ax3.fill_between(eq_x, 10000.0, equity, color='#10B981' if metrics['net_pnl'] >= 0 else '#EF4444', alpha=0.15)
    ax3.axhline(10000.0, color='#9CA3AF', linestyle=':', alpha=0.6, label='Initial Capital ($10,000)')
    ax3.set_ylabel("Equity ($ USD)", color='#9CA3AF')
    ax3.set_xlabel("1-Minute Historical Candles", color='#9CA3AF')
    ax3.legend(loc='upper left', facecolor='#0B0F19', edgecolor='#243256', fontsize=9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"Graph successfully saved: {output_path}")


# =====================================================================
# 5. GENERATE INTERACTIVE HTML REPORT
# =====================================================================

def generate_html_report(metrics, trades, output_path="D:/projects/QUANT/backtest_report.html"):
    print(f"Generating interactive HTML report -> {output_path}...")
    
    trade_rows = ""
    for idx, t in enumerate(trades[:50], 1):
        pnl_class = "profit" if t["pnl_usd"] > 0 else "loss"
        badge = "badge-long" if t["type"] == "LONG" else "badge-short"
        trade_rows += f"""
        <tr>
            <td>#{idx}</td>
            <td><span class="badge {badge}">{t['type']}</span></td>
            <td>${t['entry_price']:.2f}</td>
            <td>${t['exit_price']:.2f}</td>
            <td class="{pnl_class}">{t['pnl_pct']:+.2f}%</td>
            <td class="{pnl_class}">${t['pnl_usd']:+.2f}</td>
            <td>{t['bars_held']} mins</td>
            <td><span class="tag">{t['reason']}</span></td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Mean Reversion Backtest Report | Quantitative Analytics</title>
    <style>
        body {{ background-color: #0B0F19; color: #F3F4F6; font-family: -apple-system, sans-serif; padding: 2rem; margin: 0; }}
        .header {{ text-align: center; margin-bottom: 2rem; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
        .card {{ background: #131B2E; border: 1px solid #243256; border-radius: 8px; padding: 1.2rem; text-align: center; }}
        .card-val {{ font-size: 1.8rem; font-weight: bold; margin-top: 0.5rem; }}
        .green {{ color: #10B981; }}
        .red {{ color: #EF4444; }}
        .chart-box {{ background: #131B2E; border: 1px solid #243256; border-radius: 8px; padding: 1rem; margin-bottom: 2rem; text-align: center; }}
        .chart-box img {{ max-width: 100%; border-radius: 6px; }}
        table {{ width: 100%; border-collapse: collapse; background: #131B2E; border-radius: 8px; overflow: hidden; font-size: 0.95rem; }}
        th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #243256; }}
        th {{ background: #1C2640; color: #9CA3AF; }}
        .profit {{ color: #10B981; font-weight: bold; }}
        .loss {{ color: #EF4444; font-weight: bold; }}
        .badge {{ padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }}
        .badge-long {{ background: rgba(16, 185, 129, 0.2); color: #10B981; }}
        .badge-short {{ background: rgba(239, 68, 68, 0.2); color: #EF4444; }}
        .tag {{ background: #1C2640; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; color: #9CA3AF; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Quantitative Mean Reversion Backtest Report</h1>
        <p style="color: #9CA3AF;">Instrument: BTC/USDT | Timeframe: 1-Minute | Model: VWAP + Z-Score Asymmetric Exit (0.5σ)</p>
    </div>

    <div class="cards">
        <div class="card">
            <div style="color: #9CA3AF; font-size: 0.85rem;">ACCURACY (WIN RATE)</div>
            <div class="card-val green">{metrics['win_rate']:.1f}%</div>
        </div>
        <div class="card">
            <div style="color: #9CA3AF; font-size: 0.85rem;">TOTAL RETURN</div>
            <div class="card-val {'green' if metrics['net_pnl'] >= 0 else 'red'}">{metrics['total_return_pct']:+.2f}%</div>
        </div>
        <div class="card">
            <div style="color: #9CA3AF; font-size: 0.85rem;">PROFIT FACTOR</div>
            <div class="card-val green">{metrics['profit_factor']:.2f}</div>
        </div>
        <div class="card">
            <div style="color: #9CA3AF; font-size: 0.85rem;">MAX DRAWDOWN</div>
            <div class="card-val red">{metrics['max_drawdown_pct']:.2f}%</div>
        </div>
        <div class="card">
            <div style="color: #9CA3AF; font-size: 0.85rem;">TOTAL TRADES</div>
            <div class="card-val" style="color: #3B82F6;">{metrics['total_trades']}</div>
        </div>
    </div>

    <div class="chart-box">
        <h3 style="margin-top: 0; color: #9CA3AF;">Visual Execution & Equity Curve</h3>
        <img src="backtest_results.png" alt="Backtest Chart">
    </div>

    <h3>Recent Trade Log (Sample of 50 Trades)</h3>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Type</th>
                <th>Entry Price</th>
                <th>Exit Price</th>
                <th>PnL (%)</th>
                <th>PnL ($)</th>
                <th>Duration</th>
                <th>Exit Reason</th>
            </tr>
        </thead>
        <tbody>
            {trade_rows}
        </tbody>
    </table>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML report successfully saved: {output_path}")


# =====================================================================
# MAIN RUNNER
# =====================================================================

if __name__ == "__main__":
    bars = fetch_binance_klines("BTCUSDT", interval="1m", limit=1000)
    results = run_backtest(bars, lookback=20, entry_z=2.0, exit_z=0.5, stop_loss_pct=0.0015)
    metrics = calculate_metrics(results)
    if metrics:
        plot_backtest_graph(results, metrics, "D:/projects/QUANT/backtest_results.png")
        generate_html_report(metrics, results["trades"], "D:/projects/QUANT/backtest_report.html")
