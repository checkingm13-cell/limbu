"""
REAL-TIME QUANT SERVER: BINANCE WEBSOCKET + KDB-STYLE IN-MEMORY RDB
====================================================================
Architecture:
  [Binance WebSocket] ──► Ticker Plant (TP)
                               │
                               ▼
                   kdb+ In-Memory RDB (Columnar Ring Buffer)
                               │
                               ▼
                   CEP Engine (VWAP, Z-Score, Regime Filter, Trades)
                               │
                               ▼
                   WebSocket Broadcast ──► Live Web Dashboard (localhost:8000)

Run:
    python D:/projects/QUANT/live_quant_server.py
"""

import asyncio
import json
import math
import time
import os
import sys
import csv
import hashlib
from contextlib import asynccontextmanager
from typing import List, Dict, Any

# Configure UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import numpy as np
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn
from jev_client import JevClient

# Jev Brain 4 Instance
jev_client = JevClient()
latest_jev_decision = {
    "action": "FLAT",
    "confidence": 0.0,
    "expected_move_bps": 0.0,
    "regime": "INITIALIZING",
    "model": jev_client.model,
    "status": "APPROVED",
    "last_updated": "Never"
}

# Disk Persistence Paths (kdb+ HDB equivalent)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
TICKS_CSV = os.path.join(DATA_DIR, "live_ticks.csv")
TRADES_CSV = os.path.join(DATA_DIR, "live_trades.csv")
TELEMETRY_CSV = os.path.join(DATA_DIR, "telemetry_stream.csv")
SHADOW_JEV_LOG = os.path.join(DATA_DIR, "shadow_jev_log.jsonl")

# Initialize CSV files with headers if they do not exist
if not os.path.exists(TICKS_CSV):
    with open(TICKS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "time_str", "price", "volume", "vwap", "deviation", "z_score", "regime"])

if not os.path.exists(TRADES_CSV):
    with open(TRADES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["trade_id", "type", "entry_time", "exit_time", "entry_price", "exit_price", "pnl_usd", "reason"])

if not os.path.exists(TELEMETRY_CSV):
    with open(TELEMETRY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "price", "volume", "vwap", "vwap_slope", "ema_slope", "z_score", "regime", "intent", "approved", "qty", "pnl", "drawdown"])

# Async queue for non-blocking disk persistence
tick_disk_queue: asyncio.Queue = asyncio.Queue()

from brain2_safety_governor import SafetyGovernorFSM, ACTIVE_CONFIG_PATH


# =====================================================================
# 1. KDB+ STYLE IN-MEMORY REAL-TIME DATABASE (COLUMNAR RING BUFFER)
# =====================================================================

class KdbStyleRDB:
    """
    Simulates a kdb+/q In-Memory Real-Time Database (RDB) table.
    Stores high-frequency ticks in pre-allocated columnar NumPy arrays
    for zero-garbage-collection and sub-microsecond vector operations.
    """
    def __init__(self, capacity: int = 50_000):
        self.capacity = capacity
        self.size = 0
        self.idx = 0
        
        # Columnar memory buffers (kdb table equivalent: flip `time`price`vol`vwap`z!(...))
        self.t_time = np.zeros(capacity, dtype=np.float64)
        self.t_price = np.zeros(capacity, dtype=np.float64)
        self.t_volume = np.zeros(capacity, dtype=np.float64)
        self.t_vwap = np.zeros(capacity, dtype=np.float64)
        self.t_dev = np.zeros(capacity, dtype=np.float64)
        self.t_zscore = np.zeros(capacity, dtype=np.float64)
        self.t_cvd = np.zeros(capacity, dtype=np.float64)
        self.t_er = np.zeros(capacity, dtype=np.float64)
        
        # Rolling accumulator states
        self.pv_sum = 0.0
        self.vol_sum = 0.0
        self.window_ticks = 300 # sliding ~30-60 second VWAP window
        self.cum_cvd = 0.0
        
        # O(1) EWMA Variance states
        self.ewma_var = 1.0
        self.lambda_var = 0.96 # ~25-tick half-life
        
        # O(1) Kaufman Efficiency Ratio (ER) states (20-tick lookback)
        self.er_window = 20
        self.diff_sum = 0.0
        
    def insert_tick(self, ts: float, price: float, vol: float, is_buyer_maker: bool = False):
        i = self.idx
        self.t_time[i] = ts
        self.t_price[i] = price
        self.t_volume[i] = vol
        
        # 1. Delta & Cumulative Volume Delta (CVD)
        # m = False: Market Buy (+vol). m = True: Market Sell (-vol)
        delta = -vol if is_buyer_maker else vol
        self.cum_cvd += delta
        self.t_cvd[i] = self.cum_cvd
        
        # 2. Fast rolling VWAP update
        self.pv_sum += price * vol
        self.vol_sum += vol
        
        if self.size >= self.window_ticks:
            old_i = (i - self.window_ticks) % self.capacity
            self.pv_sum -= self.t_price[old_i] * self.t_volume[old_i]
            self.vol_sum -= self.t_volume[old_i]
            
        cur_vwap = self.pv_sum / self.vol_sum if self.vol_sum > 0 else price
        dev = price - cur_vwap
        self.t_vwap[i] = cur_vwap
        self.t_dev[i] = dev
        
        # 3. O(1) EWMA Sigma (Continuous, no window boundary artifacts)
        if self.size == 0:
            self.ewma_var = max(dev * dev, 1e-4)
        else:
            self.ewma_var = self.lambda_var * self.ewma_var + (1.0 - self.lambda_var) * (dev * dev)
        sigma = math.sqrt(max(self.ewma_var, 1e-6))
        z = dev / sigma
        self.t_zscore[i] = z
        
        # 4. O(1) Efficiency Ratio (ER) (Chop vs Trend Drift)
        # ER = |Price - Price_{t-n}| / Sum(|Price_k - Price_{k-1}|)
        prev_idx = (i - 1) % self.capacity
        step = abs(price - self.t_price[prev_idx]) if self.size > 0 else 0.0
        self.diff_sum += step
        
        if self.size >= self.er_window:
            old_prev = (i - self.er_window - 1) % self.capacity
            old_curr = (i - self.er_window) % self.capacity
            old_step = abs(self.t_price[old_curr] - self.t_price[old_prev])
            self.diff_sum = max(0.0, self.diff_sum - old_step)
            
            n_ago_idx = (i - self.er_window) % self.capacity
            net_change = abs(price - self.t_price[n_ago_idx])
            er = (net_change / self.diff_sum) if self.diff_sum > 1e-6 else 0.0
        else:
            er = 0.0
        self.t_er[i] = er
        
        # Advance ring buffer
        self.idx = (self.idx + 1) % self.capacity
        if self.size < self.capacity:
            self.size += 1
            
        return {
            "timestamp": ts,
            "price": price,
            "volume": vol,
            "vwap": cur_vwap,
            "dev": dev,
            "std": float(sigma),
            "z": float(z),
            "cvd": float(self.cum_cvd),
            "er": float(er),
            "delta": float(delta)
        }

    def get_latest_series(self, count: int = 150):
        """Extracts the most recent N points for live chart rendering."""
        n = min(self.size, count)
        if n == 0:
            return {"prices": [], "vwap": [], "upper": [], "lower": [], "z": []}
            
        if self.idx >= n:
            indices = np.arange(self.idx - n, self.idx)
        else:
            indices = np.concatenate((np.arange(self.capacity - (n - self.idx), self.capacity), np.arange(0, self.idx)))
            
        prices = self.t_price[indices].tolist()
        vwaps = self.t_vwap[indices].tolist()
        zs = self.t_zscore[indices].tolist()
        
        # Calculate dynamic +/- 2 sigma bands
        devs = self.t_dev[indices]
        current_std = float(np.std(devs)) if len(devs) > 1 else 1.0
        uppers = [v + 2.0 * current_std for v in vwaps]
        lowers = [v - 2.0 * current_std for v in vwaps]
        
        return {
            "times": [time.strftime("%H:%M:%S", time.localtime(t)) for t in self.t_time[indices]],
            "prices": prices,
            "vwap": vwaps,
            "upper": uppers,
            "lower": lowers,
            "z": zs
        }


# =====================================================================
# 2. REAL-TIME STRATEGY EXECUTION ENGINE
# =====================================================================

class LiveQuantEngine:
    def __init__(self):
        self.rdb = KdbStyleRDB(capacity=50_000)
        self.position = 0 # +1 Long, -1 Short, 0 Flat
        self.entry_price = 0.0
        self.entry_time = ""

        # Load Brain 2 approved active config
        self.config = {
            "entry_z": 2.0,
            "exit_z": 0.5,
            "stop_loss_usd": 8.0,
            "cooldown_sec": 0,
            "session_profit_target_usd": 10.0
        }
        if os.path.exists(ACTIVE_CONFIG_PATH):
            try:
                with open(ACTIVE_CONFIG_PATH, "r", encoding="utf-8") as f:
                    self.config.update(json.load(f))
            except Exception:
                pass
                
        self.entry_z = self.config["entry_z"]
        self.exit_z = self.config["exit_z"]
        self.stop_loss_usd = self.config["stop_loss_usd"]
        self.cooldown_sec = self.config.get("cooldown_sec", 15)
        self.bar_interval_sec = self.config.get("bar_interval_sec", 1.0)
        self.session_profit_target = self.config.get("session_profit_target_usd", 10.0)
        self.last_exit_ts = 0.0
        self.last_bar_eval_ts = 0.0
        self._last_cfg_mtime = 0.0
        self.current_contract_size = 0.1
        self.prev_vwap = 0.0
        
        # Brain 2: Safety Governor & Risk FSM
        self.governor = SafetyGovernorFSM(session_profit_target_usd=self.session_profit_target)
        
        # Performance tracking
        self.trades = []
        self.initial_capital = 10_000.0
        self.equity = 10_000.0
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0
        
        # Trend EMA (15-period on prices)
        self.ema = None
        self.last_ema = None
        self.ema_alpha = 2.0 / (15 + 1)
        self.regime = "CALIBRATING"
        
        # Active trade notifications
        self.total_ticks_processed = 0
        
        # 1-Second Micro-Bar Candle Aggregator for Wick Rejection
        self.bar_start_ts = 0.0
        self.bar_open = 0.0
        self.bar_high = -1e9
        self.bar_low = 1e9
        self.bar_close = 0.0
        self.last_bar_stats = {"wick_upper": 0.0, "wick_lower": 0.0, "range": 0.0}

    def process_tick(self, ts: float, price: float, vol: float, is_buyer_maker: bool = False):
        self.total_ticks_processed += 1
        tick_stats = self.rdb.insert_tick(ts, price, vol, is_buyer_maker=is_buyer_maker)
        
        # 1-Second Micro-Bar tracking for wick calculation
        bar_idx = math.floor(ts / self.bar_interval_sec) * self.bar_interval_sec
        if bar_idx != self.bar_start_ts:
            if self.bar_start_ts > 0.0 and self.bar_high >= self.bar_low:
                bar_range = max(self.bar_high - self.bar_low, 1e-6)
                upper_wick = (self.bar_high - max(self.bar_open, self.bar_close)) / bar_range
                lower_wick = (min(self.bar_open, self.bar_close) - self.bar_low) / bar_range
                self.last_bar_stats = {
                    "wick_upper": upper_wick,
                    "wick_lower": lower_wick,
                    "range": bar_range
                }
            self.bar_start_ts = bar_idx
            self.bar_open = price
            self.bar_high = price
            self.bar_low = price
            self.bar_close = price
        else:
            self.bar_high = max(self.bar_high, price)
            self.bar_low = min(self.bar_low, price)
            self.bar_close = price
        
        # Update Trend EMA
        if self.ema is None:
            self.ema = price
            self.last_ema = price
        else:
            self.last_ema = self.ema
            self.ema = self.ema_alpha * price + (1.0 - self.ema_alpha) * self.ema
            
        ema_slope = (self.ema - self.last_ema) * 10.0
        er = tick_stats["er"]
        
        # Institutional Regime Filter: Combines EMA slope and Efficiency Ratio (ER)
        if er > 0.40:
            self.regime = "STRONG TREND DRIFT"
        elif ema_slope > 2.0:
            self.regime = "BULL TREND"
        elif ema_slope < -2.0:
            self.regime = "BEAR TREND"
        else:
            self.regime = "RANGING (CHOP / SWEET SPOT)"

        z = tick_stats["z"]
        cur_time = time.strftime("%H:%M:%S", time.localtime(ts))
        
        # Wait for buffer warm-up
        if self.rdb.size < 40:
            self.last_signal = f"BUFFER WARMUP: {self.rdb.size}/40 ticks"
            return tick_stats
            
        # Check Brain 2 Governor authorization
        can_trade, size_mult, gov_state = self.governor.can_trade()

        # Hot-reload Brain 2 active config periodically
        if self.total_ticks_processed % 50 == 0 and os.path.exists(ACTIVE_CONFIG_PATH):
            try:
                mtime = os.path.getmtime(ACTIVE_CONFIG_PATH)
                if mtime > self._last_cfg_mtime:
                    self._last_cfg_mtime = mtime
                    with open(ACTIVE_CONFIG_PATH, "r", encoding="utf-8") as f:
                        self.config.update(json.load(f))
                    self.entry_z = self.config.get("entry_z", 2.0)
                    self.exit_z = self.config.get("exit_z", 0.2)
                    self.stop_loss_usd = self.config.get("stop_loss_usd", 8.0)
                    self.cooldown_sec = self.config.get("cooldown_sec", 15)
                    self.bar_interval_sec = self.config.get("bar_interval_sec", 1.0)
                    self.session_profit_target = self.config.get("session_profit_target_usd", 10.0)
                    self.governor.update_config(self.config)
            except Exception:
                pass

        # Strategy Logic: Proposes Intent -> Risk Engine Audits -> Router Executes
        intent = None
        if self.position == 0:
            # Check if profit target locked
            if self.governor.state == "PROFIT_TARGET_LOCKED":
                self.last_signal = f"PROFIT LOCKED (+${self.total_pnl:.2f} >= Target +${self.session_profit_target:.2f}) [TRADING HALTED]"
                return tick_stats

            # Enforce Brain 3 statistical cooldown
            elapsed_cd = ts - self.last_exit_ts
            if elapsed_cd < self.cooldown_sec:
                rem = int(self.cooldown_sec - elapsed_cd)
                self.last_signal = f"COOLDOWN ({rem}s remaining)"
                return tick_stats

            # Throttle new entry evaluation to bar_interval_sec (1.0s candle resolution)
            if (ts - self.last_bar_eval_ts) < self.bar_interval_sec:
                return tick_stats
            self.last_bar_eval_ts = ts

            # 1. Strategy evaluates setup (Proposes intent only, NO sizing authority)
            # HARD VETO 1: Kaufman ER > 0.38 indicates clean directional breakout drift (no mean reversion)
            # HARD VETO 2: Wick Rejection confirmation (requires exhaustion wick >= 30% of 1s range)
            is_er_safe = er <= 0.38
            has_lower_wick = self.last_bar_stats["wick_lower"] >= 0.25 or (price - self.bar_low) >= 0.3 * max(self.bar_high - self.bar_low, 1e-4)
            has_upper_wick = self.last_bar_stats["wick_upper"] >= 0.25 or (self.bar_high - price) >= 0.3 * max(self.bar_high - self.bar_low, 1e-4)
            
            if z < -self.entry_z and self.regime != "BEAR TREND" and is_er_safe and has_lower_wick:
                intent = {"side": "LONG", "price": price, "z": z, "confidence": 0.85}
            elif z > self.entry_z and self.regime != "BULL TREND" and is_er_safe and has_upper_wick:
                intent = {"side": "SHORT", "price": price, "z": z, "confidence": 0.85}

            # 2. Risk Engine holds absolute veto and sizing authority
            if intent is not None:
                verdict = self.governor.audit_intent(intent["side"], intent["price"], intent["z"], intent["confidence"])
                if verdict["approved"]:
                    self.position = 1 if intent["side"] == "LONG" else -1
                    self.current_contract_size = verdict["quantity"]
                    self.entry_price = price
                    self.entry_time = cur_time
                    self.last_signal = f"EXECUTED {intent['side']} @ ${price:.2f} (Qty: {verdict['quantity']:.2f}, ER: {er:.2f}) [{verdict['reason']}]"
                else:
                    self.last_signal = f"VETOED {intent['side']} [{verdict['reason']}]"
            else:
                if not is_er_safe:
                    self.last_signal = f"VETOED DRIFT (ER: {er:.2f} > 0.38 Breakout Veto)"
                else:
                    self.last_signal = f"MONITORING ({gov_state} | ER: {er:.2f})"
        else:
            # Active Position: Check exits
            unrealized_pnl = (price - self.entry_price) if self.position == 1 else (self.entry_price - price)
            dollar_pnl = unrealized_pnl * self.current_contract_size
            
            # 0. Capital Preservation: Early exit if this trade reaches session profit target
            if (self.total_pnl + dollar_pnl) >= self.session_profit_target:
                self._record_trade(cur_time, price, dollar_pnl, f"PROFIT TARGET REACHED (+${(self.total_pnl + dollar_pnl):.2f})")
            # 1. Hard Stop-Loss
            elif unrealized_pnl <= -self.stop_loss_usd:
                self._record_trade(cur_time, price, dollar_pnl, "HARD STOP LOSS")
            # 2. Asymmetric Exit: Return to exit_z
            elif abs(z) < self.exit_z:
                self._record_trade(cur_time, price, dollar_pnl, f"MEAN REVERSION TARGET ({self.exit_z} sigma)")
            else:
                pos_str = "LONG" if self.position == 1 else "SHORT"
                self.last_signal = f"HOLD {pos_str} (PnL: ${dollar_pnl:+.2f} | ER: {er:.2f})"

        # Calculate slopes for rich telemetry
        cur_vwap = tick_stats["vwap"]
        vwap_slope = (cur_vwap - self.prev_vwap) * 100.0 if self.prev_vwap > 0 else 0.0
        self.prev_vwap = cur_vwap

        # Enqueue tick & rich telemetry for background disk persistence
        try:
            tick_disk_queue.put_nowait([
                ts, cur_time, price, vol, cur_vwap, tick_stats["dev"], z, self.regime
            ])
            # Append rich telemetry record
            with open(TELEMETRY_CSV, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    f"{ts:.3f}", f"{price:.2f}", f"{vol:.5f}", f"{cur_vwap:.2f}",
                    f"{vwap_slope:.3f}", f"{ema_slope:.3f}", f"{z:.2f}", self.regime,
                    intent["side"] if intent else "NONE",
                    1 if (intent and self.position != 0) else 0,
                    self.current_contract_size,
                    f"{self.total_pnl:.2f}",
                    f"{self.governor.session_drawdown:.2f}"
                ])
        except Exception:
            pass

        return tick_stats

    def _record_trade(self, exit_time: str, exit_price: float, dollar_pnl: float, reason: str):
        pos_type = "LONG" if self.position == 1 else "SHORT"
        self.total_trades += 1
        self.total_pnl += dollar_pnl
        self.equity += dollar_pnl
        if dollar_pnl > 0:
            self.winning_trades += 1
            
        trade_record = {
            "id": self.total_trades,
            "type": pos_type,
            "entry_time": self.entry_time,
            "exit_time": exit_time,
            "entry_price": self.entry_price,
            "exit_price": exit_price,
            "pnl_usd": dollar_pnl,
            "reason": reason
        }
        self.trades.insert(0, trade_record) # Newest first
        self.last_signal = f"CLOSED {pos_type} -> PnL: ${dollar_pnl:+.2f} ({reason})"
        self.position = 0
        self.last_exit_ts = time.time()

        # Notify Brain 2 Governor to update circuit breaker state
        self.governor.on_trade_completed(dollar_pnl)

        # Persist trade immediately to disk
        try:
            with open(TRADES_CSV, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    self.total_trades, pos_type, self.entry_time, exit_time,
                    f"{self.entry_price:.2f}", f"{exit_price:.2f}", f"{dollar_pnl:.2f}", reason
                ])
        except Exception as e:
            print(f"[Persistence] Error writing trade: {e}")


# =====================================================================
# 3. FASTAPI SERVER & WEBSOCKET DISPATCHER
# =====================================================================

async def disk_writer_worker():
    """Flushes ticks to live_ticks.csv in batches every 1 second (kdb+ HDB style)."""
    batch = []
    while True:
        try:
            # Drain up to 100 ticks
            while len(batch) < 100:
                try:
                    item = tick_disk_queue.get_nowait()
                    batch.append(item)
                except asyncio.QueueEmpty:
                    break
            
            if batch:
                with open(TICKS_CSV, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerows(batch)
                batch.clear()
        except Exception as e:
            print(f"[Persistence] Error writing ticks to disk: {e}")
        await asyncio.sleep(1.0)


async def jev_evaluator_worker():
    """Background worker evaluating Jev predictions every 30 seconds."""
    global latest_jev_decision
    print("[Brain4] Jev background evaluation worker started...")
    
    # Wait 10 seconds for initial ticks to accumulate
    await asyncio.sleep(10.0)
    
    while True:
        try:
            rdb = quant_engine.rdb
            if rdb.size > 20:
                idx = (rdb.idx - 1) % rdb.capacity
                cur_p = float(rdb.t_price[idx])
                
                # Sample past prices for momentum
                n = min(rdb.size, 100)
                past_idx = (rdb.idx - n) % rdb.capacity
                past_p = float(rdb.t_price[past_idx])
                
                ret_1h_bps = ((cur_p - past_p) / past_p) * 10000.0 if past_p > 0 else 0.0
                vwap_z = float(rdb.t_zscore[idx])
                cvd = float(rdb.t_cvd[idx])
                taker_ratio = 0.55 if cvd > 0 else 0.45
                
                snap = {
                    "relative_returns_bps": {"r15m": round(ret_1h_bps * 0.4, 1), "r1h": round(ret_1h_bps, 1), "r4h": round(ret_1h_bps * 1.5, 1)},
                    "categorical": {
                        "momentum_1h": "positive" if ret_1h_bps > 10 else ("negative" if ret_1h_bps < -10 else "flat"),
                        "volatility": "normal",
                        "order_flow": "buying" if cvd > 0 else "selling"
                    },
                    "microstructure": {"vwap_z": round(vwap_z, 2), "funding_apr": 5.0, "taker_ratio": taker_ratio}
                }
                
                # Non-blocking async API evaluation in thread pool
                loop = asyncio.get_event_loop()
                jev_res = await loop.run_in_executor(None, jev_client.predict_decision, snap)
                
                action = jev_res.get("action", "FLAT")
                conf = float(jev_res.get("confidence", 0.5))
                exp_move = float(jev_res.get("expected_move_bps", 0.0))
                
                # Brain 2 Veto Gate logic
                veto_status = "APPROVED"
                if action in ["LONG", "SHORT"]:
                    if conf < 0.65:
                        veto_status = f"VETOED (Confidence {conf*100:.0f}% < 65%)"
                    elif abs(exp_move) < 28.5:
                        veto_status = f"VETOED (Move {exp_move:.0f} bps < 28.5 bps hurdle)"
                
                latest_jev_decision = {
                    "action": action,
                    "confidence": conf,
                    "expected_move_bps": exp_move,
                    "regime": jev_res.get("regime", "UNKNOWN"),
                    "model": jev_res.get("model", jev_client.model),
                    "status": veto_status,
                    "last_updated": time.strftime("%H:%M:%S")
                }
                print(f"[Brain4 Jev] Decision: {action} (Conf: {conf*100:.1f}%, Move: {exp_move:+.1f} bps) -> Status: {veto_status}")

                # === SHADOW MODE LOGGER ===
                # Logs full state immutably for discrimination testing & threshold re-calibration
                snap_str = json.dumps(snap, sort_keys=True)
                snap_hash = hashlib.sha256(snap_str.encode("utf-8")).hexdigest()[:16]
                
                # Rule signal at this exact moment
                rule_signal = "FLAT"
                if vwap_z < -quant_engine.entry_z:
                    rule_signal = "LONG"
                elif vwap_z > quant_engine.entry_z:
                    rule_signal = "SHORT"

                shadow_record = {
                    "timestamp": int(time.time()),
                    "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "snapshot_hash": snap_hash,
                    "snapshot_features": snap,
                    "rule_signal": rule_signal,
                    "rule_z": round(vwap_z, 2),
                    "jev_returned_model": jev_res.get("model", jev_client.model),
                    "jev_action": action,
                    "jev_confidence": conf,
                    "jev_probs": jev_res.get("probs", {action: conf}),
                    "jev_expected_move_bps": exp_move,
                    "jev_regime": jev_res.get("regime", "UNKNOWN"),
                    "brain2_verdict": veto_status,
                    "is_mock": bool(jev_res.get("is_mock", False)),
                    "spot_price_at_eval": cur_p,
                    "forward_outcomes": {
                        "eval_price": cur_p,
                        "p_15m": None, "p_1h": None, "p_4h": None,
                        "ret_15m_net_bps": None, "ret_1h_net_bps": None, "ret_4h_net_bps": None
                    }
                }
                
                try:
                    with open(SHADOW_JEV_LOG, "a", encoding="utf-8") as sf:
                        sf.write(json.dumps(shadow_record) + "\n")
                except Exception as log_err:
                    print(f"[ShadowLogger] Error appending record: {log_err}")

        except Exception as e:
            print(f"[Brain4 Jev] Evaluator error: {e}")
            
        await asyncio.sleep(30.0) # Evaluate every 30 seconds


@asynccontextmanager
async def lifespan(app: FastAPI):
    t1 = asyncio.create_task(ingest_binance_stream("btcusdt"))
    t2 = asyncio.create_task(broadcast_live_state())
    t3 = asyncio.create_task(disk_writer_worker())
    t4 = asyncio.create_task(jev_evaluator_worker())
    yield
    t1.cancel()
    t2.cancel()
    t3.cancel()
    t4.cancel()

app = FastAPI(lifespan=lifespan)
quant_engine = LiveQuantEngine()
active_clients: List[WebSocket] = []


@app.get("/")
def get_dashboard():
    # Read HTML dashboard file
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_dashboard.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h3>Dashboard HTML loading...</h3>")


@app.get("/download/ticks")
def download_ticks():
    if os.path.exists(TICKS_CSV):
        return FileResponse(TICKS_CSV, media_type="text/csv", filename="live_ticks.csv")
    return {"error": "No ticks logged yet"}


@app.get("/download/trades")
def download_trades():
    if os.path.exists(TRADES_CSV):
        return FileResponse(TRADES_CSV, media_type="text/csv", filename="executed_trades.csv")
    return {"error": "No trades logged yet"}


@app.get("/download/shadow_log")
def download_shadow_log():
    if os.path.exists(SHADOW_JEV_LOG):
        return FileResponse(SHADOW_JEV_LOG, media_type="application/x-jsonlines", filename="shadow_jev_log.jsonl")
    return {"error": "No shadow log recorded yet"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    active_clients.append(ws)
    try:
        while True:
            # Keep-alive receive
            _ = await ws.receive_text()
    except WebSocketDisconnect:
        active_clients.remove(ws)


async def broadcast_live_state():
    """Broadcasts 10 updates per second to all connected browsers."""
    while True:
        await asyncio.sleep(0.1) # 10 Hz stream
        if not active_clients:
            continue
            
        rdb = quant_engine.rdb
        if rdb.size == 0:
            continue
            
        latest_idx = (rdb.idx - 1) % rdb.capacity
        cur_price = float(rdb.t_price[latest_idx])
        cur_vwap = float(rdb.t_vwap[latest_idx])
        cur_z = float(rdb.t_zscore[latest_idx])
        
        cur_cvd = float(rdb.t_cvd[latest_idx])
        cur_er = float(rdb.t_er[latest_idx])
        
        # Calculate win rate
        win_rate = (quant_engine.winning_trades / quant_engine.total_trades * 100.0) if quant_engine.total_trades else 0.0
        
        # Get latest series for Chart
        series_data = rdb.get_latest_series(count=120)
        
        payload = {
            "price": cur_price,
            "vwap": cur_vwap,
            "z": cur_z,
            "cvd": cur_cvd,
            "er": cur_er,
            "regime": quant_engine.regime,
            "governor_state": quant_engine.governor.state,
            "session_profit_target": quant_engine.session_profit_target,
            "profit_locked": quant_engine.governor.state == "PROFIT_TARGET_LOCKED",
            "signal": quant_engine.last_signal,
            "position": quant_engine.position,
            "equity": quant_engine.equity,
            "total_pnl": quant_engine.total_pnl,
            "total_trades": quant_engine.total_trades,
            "win_rate": win_rate,
            "cached_ticks": rdb.size,
            "chart": series_data,
            "recent_trades": quant_engine.trades[:8],
            "jev": latest_jev_decision
        }
        
        msg = json.dumps(payload)
        for client in list(active_clients):
            try:
                await client.send_text(msg)
            except Exception:
                if client in active_clients:
                    active_clients.remove(client)


# =====================================================================
# 4. BINANCE LIVE WEBSOCKET INGESTION (aggTrade with Taker Side m Flag)
# =====================================================================

async def ingest_binance_stream(symbol: str = "btcusdt"):
    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@aggTrade"
    print(f"[TickerPlant] Connecting to Binance aggTrade WebSocket for {symbol.upper()}...")
    
    while True:
        try:
            async with websockets.connect(url) as ws:
                print(f"[TickerPlant] Connected to aggTrade! Streaming real-time CVD & ticks into kdb+ In-Memory RDB...\n")
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    price = float(data["p"])
                    vol = float(data["q"])
                    ts = data["T"] / 1000.0
                    is_buyer_maker = bool(data.get("m", False))
                    
                    # Direct ingestion into CEP Quant Engine with buyer_maker flag
                    quant_engine.process_tick(ts, price, vol, is_buyer_maker=is_buyer_maker)
        except Exception as e:
            print(f"[TickerPlant] Connection error: {e}. Reconnecting in 3s...")
            await asyncio.sleep(3.0)


# =====================================================================
# 5. START SERVER
# =====================================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print(" LIVE QUANTITATIVE TRADING SERVER (BINANCE WS + KDB RDB + 60FPS GRAPH)")
    print("=" * 80)
    print("Web Dashboard -> http://localhost:8000")
    print("WebSocket URL -> ws://localhost:8000/ws")
    print("In-Memory DB  -> kdb+ Style Columnar NumPy Buffer (50,000 tick capacity)")
    print("Strategy      -> Real-Time VWAP + Z-Score Asymmetric Exit (0.5 sigma) + Trend Veto")
    print("=" * 80 + "\n")
    
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
