"""
LIVE BINANCE WEBSOCKET MEAN REVERSION ENGINE (ENHANCED QUANT EDITION)
====================================================================
Upgrades from raw tick experiment:
1. 5-Second Bar Aggregator: Eliminates high-frequency microstructure noise.
2. Trend / Regime Guard: Detects EMA slope to VETO trades against strong momentum.
3. Hard Stop-Loss: Protects capital from runaway trends (no more falling knives).
4. Asymmetric Exit: Exits when Z returns within +/- 0.5.

No API keys needed. Free public stream.
Run:
    python D:/projects/QUANT/binance_live_mean_reversion.py btcusdt
"""

import asyncio
import json
import math
import time
import sys

# Configure stdout for clean printing
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    import websockets
except ImportError:
    print("Error: 'websockets' package is required. Install via: pip install websockets")
    sys.exit(1)


# =====================================================================
# 1. ROLLING WINDOW STATS (O(1) Incremental Calculation)
# =====================================================================

class RollingWindow:
    def __init__(self, size: int):
        self.size = size
        self.buf = [0.0] * size
        self.n = 0
        self.head = 0
        self._sum = 0.0
        self._sumsq = 0.0

    def push(self, x: float):
        if self.n == self.size:
            old = self.buf[self.head]
            self._sum -= old
            self._sumsq -= old * old
        else:
            self.n += 1
        self.buf[self.head] = x
        self._sum += x
        self._sumsq += x * x
        self.head = (self.head + 1) % self.size

    @property
    def is_full(self):
        return self.n == self.size

    def mean(self):
        return self._sum / self.n if self.n else 0.0

    def std(self):
        if self.n < 2: return 0.0
        var = (self._sumsq - (self._sum ** 2) / self.n) / (self.n - 1)
        return math.sqrt(max(var, 0.0))

    def zscore(self, x: float):
        s = self.std()
        return (x - self.mean()) / s if s > 1e-8 else 0.0


# =====================================================================
# 2. 5-SECOND BAR AGGREGATOR
# =====================================================================

class BarAggregator:
    """Aggregates raw high-frequency trades into 5-second OHLCV bars."""
    def __init__(self, interval_sec: float = 5.0):
        self.interval = interval_sec
        self.current_bar_start = 0.0
        self.open = 0.0
        self.high = 0.0
        self.low = 0.0
        self.close = 0.0
        self.volume = 0.0
        self.pv_sum = 0.0

    def add_trade(self, price: float, volume: float, timestamp: float):
        # Round down to bar start
        bar_start = (timestamp // self.interval) * self.interval
        completed_bar = None

        if self.current_bar_start == 0.0:
            self.current_bar_start = bar_start
            self.open = self.high = self.low = self.close = price
            self.volume = volume
            self.pv_sum = price * volume
        elif bar_start > self.current_bar_start:
            # Emit completed bar
            completed_bar = {
                "time": time.strftime("%H:%M:%S", time.localtime(self.current_bar_start)),
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "close": self.close,
                "volume": self.volume,
                "typical_price": (self.high + self.low + self.close) / 3.0,
                "pv": self.pv_sum
            }
            # Start new bar
            self.current_bar_start = bar_start
            self.open = self.high = self.low = self.close = price
            self.volume = volume
            self.pv_sum = price * volume
        else:
            self.high = max(self.high, price)
            self.low = min(self.low, price)
            self.close = price
            self.volume += volume
            self.pv_sum += price * volume

        return completed_bar


# =====================================================================
# 3. ENHANCED QUANT STRATEGY ENGINE
# =====================================================================

class MeanReversionStrategy:
    def __init__(self, lookback_bars: int = 24, stop_loss_usd: float = 8.0):
        self.lookback = lookback_bars
        self.stop_loss_usd = stop_loss_usd
        self.dev_win = RollingWindow(lookback_bars)
        
        # Cumulative session VWAP tracking
        self.cum_pv = 0.0
        self.cum_vol = 0.0
        
        # Trend EMA (12-bar EMA)
        self.ema = None
        self.ema_multiplier = 2.0 / (12 + 1)
        self.last_ema = None
        
        # Position tracking
        self.position = 0 # +1 Long, -1 Short, 0 Flat
        self.entry_price = 0.0
        self.entry_time = ""
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0

    def update_bar(self, bar: dict):
        close = bar["close"]
        vol = bar["volume"]
        tp = bar["typical_price"]
        
        # 1. Update Session VWAP
        self.cum_pv += tp * vol
        self.cum_vol += vol
        vwap = self.cum_pv / self.cum_vol if self.cum_vol > 0 else close
        
        # 2. Update EMA for Trend Regime Detection
        if self.ema is None:
            self.ema = close
            self.last_ema = close
        else:
            self.last_ema = self.ema
            self.ema = (close - self.ema) * self.ema_multiplier + self.ema
            
        ema_slope = (self.ema - self.last_ema)  # Direction of momentum
        
        # Regime determination
        regime = "RANGING"
        if ema_slope > 1.2:
            regime = "BULL TREND"
        elif ema_slope < -1.2:
            regime = "BEAR TREND"
            
        # 3. Update Deviation and Z-Score
        dev = close - vwap
        self.dev_win.push(dev)
        
        if not self.dev_win.is_full:
            return None  # Warming up
            
        z = self.dev_win.zscore(dev)
        
        # 4. Signal and Trade Logic
        action = "FLAT"
        pnl = 0.0
        trade_closed = False
        
        if self.position == 0:
            # ENTRY LOGIC (with Trend Veto!)
            if z < -2.0:
                if regime == "BEAR TREND":
                    action = "VETO BUY (Dumping Knife)"
                else:
                    self.position = 1
                    self.entry_price = close
                    self.entry_time = bar["time"]
                    action = ">>> BUY (LONG) <<<"
            elif z > 2.0:
                if regime == "BULL TREND":
                    action = "VETO SELL (Pumping Rocket)"
                else:
                    self.position = -1
                    self.entry_price = close
                    self.entry_time = bar["time"]
                    action = ">>> SELL (SHORT) <<<"
        else:
            # POSITION OPEN: Check Hard Stop-Loss first
            current_pnl = (close - self.entry_price) if self.position == 1 else (self.entry_price - close)
            
            if current_pnl <= -self.stop_loss_usd:
                # HARD STOP HIT!
                trade_closed = True
                pnl = current_pnl
                action = f"STOP LOSS (PnL: ${pnl:+.2f})"
                self.position = 0
            # Asymmetric Mean Reversion Exit: Return to within +/- 0.5
            elif abs(z) < 0.5:
                trade_closed = True
                pnl = current_pnl
                action = f"EXIT MEAN (PnL: ${pnl:+.2f})"
                self.position = 0
            else:
                pos_str = "LONG" if self.position == 1 else "SHORT"
                action = f"HOLD {pos_str} (PnL: ${current_pnl:+.2f})"

        if trade_closed:
            self.total_trades += 1
            self.total_pnl += pnl
            if pnl > 0:
                self.winning_trades += 1

        return {
            "time": bar["time"],
            "close": close,
            "vwap": vwap,
            "dev": dev,
            "z": z,
            "regime": regime,
            "action": action,
            "position": self.position
        }


# =====================================================================
# ASCII METER
# =====================================================================

def render_z_gauge(z: float, width: int = 24) -> str:
    clamped_z = max(-3.0, min(3.0, z))
    norm = (clamped_z + 3.0) / 6.0
    pos = int(norm * (width - 1))
    bar = ["-"] * width
    center = width // 2
    bar[center] = "|"
    bar[pos] = "O"
    return "[" + "".join(bar) + "]"


# =====================================================================
# LIVE WEBSOCKET LOOP
# =====================================================================

async def stream_binance(symbol: str = "btcusdt"):
    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@trade"
    
    print("\n" + "=" * 105, flush=True)
    print(f" LIVE BINANCE QUANT ENGINE: {symbol.upper()} (5-SECOND BARS + TREND VETO + HARD STOP)", flush=True)
    print("=" * 105, flush=True)
    print("Bar Interval    : 5.0 seconds (Aggregates high-frequency noise)", flush=True)
    print("Lookback Window : 24 bars (~2 minutes)", flush=True)
    print("Entry Threshold : |Z| > 2.0  (Vetoed if trending against momentum!)", flush=True)
    print("Exit Threshold  : |Z| < 0.5  (Asymmetric profit target)", flush=True)
    print("Hard Stop-Loss  : $8.00 USD  (Guards against falling knives)", flush=True)
    print("Connecting to Binance WebSocket...\n", flush=True)
    
    aggregator = BarAggregator(interval_sec=5.0)
    engine = MeanReversionStrategy(lookback_bars=24, stop_loss_usd=8.0)
    
    async with websockets.connect(url) as ws:
        print("Connected! Streaming live market data...\n", flush=True)
        header = f"{'Time':<8} | {'Close ($)':<10} | {'VWAP ($)':<10} | {'Dev ($)':<8} | {'Z-Score':<7} | {'Z Meter (-3 to +3)':<26} | {'Regime':<12} | {'Action / Signal':<25}"
        print(header, flush=True)
        print("-" * 125, flush=True)
        
        warmup_bars = 0
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            
            price = float(data["p"])
            volume = float(data["q"])
            timestamp = data["T"] / 1000.0
            
            bar = aggregator.add_trade(price, volume, timestamp)
            if bar is not None:
                # A 5-second bar just completed!
                warmup_bars += 1
                if warmup_bars <= engine.lookback:
                    print(f"[{bar['time']}] Building 5-second bars: {warmup_bars}/{engine.lookback}...", flush=True)
                    engine.update_bar(bar)
                    continue
                
                result = engine.update_bar(bar)
                if result:
                    meter = render_z_gauge(result["z"])
                    print(f"{result['time']:<8} | {result['close']:<10.2f} | {result['vwap']:<10.2f} | {result['dev']:<+8.2f} | {result['z']:<+7.2f} | {meter:<26} | {result['regime']:<12} | {result['action']:<25}", flush=True)


if __name__ == "__main__":
    try:
        symbol = sys.argv[1] if len(sys.argv) > 1 else "btcusdt"
        asyncio.run(stream_binance(symbol))
    except KeyboardInterrupt:
        print("\nDisconnected from Binance live feed. Engine stopped.")
