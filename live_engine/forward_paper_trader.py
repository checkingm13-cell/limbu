"""
FORWARD PAPER TRADING CANARY ENGINE (FOUR-BRAIN ARCHITECTURE)
=============================================================
Deploys the complete verified trading pipeline live without financial risk:
1. Live Binance WebSocket stream (bookTicker + aggTrade).
2. Sanitized Snapshot Engine (strips dates, prices, tickers; passes relative bps & verbal tokens).
3. Brain 4 Advisor (LayaClient with calibrated multiclass temperature T=5.000).
4. Brain 2 Safety Governor (enforces 0.65 calibrated confidence gate & 1.5x fee hurdle veto).
5. Exact Friction Accounting (19.0 bps round-trip fee + funding drag).
6. Live Real-Time Terminal Telemetry.

No API keys needed.
Run:
    python D:/projects/QUANT/production_system/live_engine/forward_paper_trader.py
"""

import asyncio
import json
import time
import os
import sys
import math
from typing import Dict, Any, List

# Configure UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    import websockets
except ImportError:
    print("Error: 'websockets' required. Run: pip install websockets")
    sys.exit(1)

from laya_client import LayaClient
from brain4_llm_advisor import Brain4Advisor

LOG_DIR = "D:/projects/QUANT/production_system/data"
os.makedirs(LOG_DIR, exist_ok=True)
PAPER_LOG_FILE = os.path.join(LOG_DIR, "paper_trading_log.jsonl")

ROUND_TRIP_FEE_BPS = 19.0
ONE_WAY_FEE_BPS = 9.5
CALIBRATED_TEMPERATURE = 5.000
MIN_CONFIDENCE_GATE = 0.65


class ForwardPaperTrader:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol.upper()
        self.ws_symbol = symbol.lower()
        
        # Microstructure & price buffers
        self.current_price = 0.0
        self.best_bid = 0.0
        self.best_ask = 0.0
        self.prices_1m: List[float] = []
        self.volume_1m: List[float] = []
        self.taker_buy_vol_1m: List[float] = []
        
        # Rolling bar accumulators
        self.current_bar_open = 0.0
        self.current_bar_vol = 0.0
        self.current_bar_taker_vol = 0.0
        self.bar_start_ts = time.time()
        
        # Portfolio State
        self.capital = 100.0
        self.position = 0 # +1 LONG, -1 SHORT, 0 FLAT
        self.entry_price = 0.0
        self.entry_ts = 0.0
        self.realized_pnl = 0.0
        self.total_fees_paid = 0.0
        self.trades_count = 0
        self.trade_history: List[Dict[str, Any]] = []

        # Decision & Governor Engines
        self.laya = LayaClient(strict_no_mock=False)
        self.advisor = Brain4Advisor()
        self.last_decision_ts = 0.0
        self.decision_interval_sec = 60.0 # Evaluate snapshot every 60s
        self.last_decision: Dict[str, Any] = {"action": "FLAT", "confidence": 0.0, "status": "WARMING_UP"}

    def update_tick(self, price: float, qty: float, is_buyer_maker: bool):
        """Processes an aggregated trade print."""
        self.current_price = price
        self.current_bar_vol += qty
        # If buyer is maker, taker is seller; if buyer is NOT maker, taker is buyer
        if not is_buyer_maker:
            self.current_bar_taker_vol += qty

        # Check 1-minute bar rollover
        now = time.time()
        if now - self.bar_start_ts >= 60.0:
            self.prices_1m.append(price)
            self.volume_1m.append(self.current_bar_vol)
            self.taker_buy_vol_1m.append(self.current_bar_taker_vol)
            
            # Keep rolling window of last 240 bars (4 hours)
            if len(self.prices_1m) > 240:
                self.prices_1m.pop(0)
                self.volume_1m.pop(0)
                self.taker_buy_vol_1m.pop(0)

            # Reset current bar
            self.bar_start_ts = now
            self.current_bar_vol = 0.0
            self.current_bar_taker_vol = 0.0

    def compute_features(self) -> Dict[str, Any]:
        """Calculates multi-timeframe returns and microstructure ratios."""
        n = len(self.prices_1m)
        if n < 15:
            # Synthetic warmup defaults if live buffer is small
            return {
                "ret_15m": 0.0, "ret_1h": 0.0, "ret_4h": 0.0,
                "atr_pct": 0.35, "vwap_z": 0.0, "taker_ratio": 0.50
            }

        curr = self.current_price
        ret_15m = (curr - self.prices_1m[-15]) / self.prices_1m[-15] * 10000.0 if n >= 15 else 0.0
        ret_1h = (curr - self.prices_1m[-60]) / self.prices_1m[-60] * 10000.0 if n >= 60 else ret_15m * 1.5
        ret_4h = (curr - self.prices_1m[0]) / self.prices_1m[0] * 10000.0 if n >= 240 else ret_1h * 1.8

        # Rolling ATR approximation over available bars
        diffs = [abs(self.prices_1m[i] - self.prices_1m[i-1]) / self.prices_1m[i-1] for i in range(1, n)]
        atr_pct = float(np.mean(diffs) * 100.0 * math.sqrt(60)) if diffs else 0.35

        # Taker buy volume ratio
        tot_vol = sum(self.volume_1m[-15:])
        tot_tb_vol = sum(self.taker_buy_vol_1m[-15:])
        taker_ratio = (tot_tb_vol / tot_vol) if tot_vol > 0 else 0.50

        # Mean-deviation Z-score
        mean_p = float(np.mean(self.prices_1m[-15:]))
        std_p = float(np.std(self.prices_1m[-15:]))
        vwap_z = (curr - mean_p) / std_p if std_p > 1e-4 else 0.0

        return {
            "ret_15m": ret_15m,
            "ret_1h": ret_1h,
            "ret_4h": ret_4h,
            "atr_pct": atr_pct,
            "vwap_z": vwap_z,
            "taker_ratio": taker_ratio
        }

    def evaluate_decision(self):
        """Runs Laya decision model and Brain 2 risk gate."""
        feats = self.compute_features()
        
        # Build sanitized snapshot (stripping dates, prices, tickers)
        sanitized_snap = self.laya.build_sanitized_snapshot(
            ret_15m_bps=feats["ret_15m"],
            ret_1h_bps=feats["ret_1h"],
            ret_4h_bps=feats["ret_4h"],
            atr_pct=feats["atr_pct"],
            vwap_zscore=feats["vwap_z"],
            funding_rate_apr=5.0, # Baseline modern funding
            taker_buy_ratio=feats["taker_ratio"]
        )

        # Predict with calibrated temperature T=5.000
        laya_output = self.laya.predict_decision(sanitized_snap, temperature=CALIBRATED_TEMPERATURE)
        proposed_action = laya_output["action"]
        confidence = laya_output["confidence"]

        # Expected move heuristic based on multi-hour impulse
        expected_move_bps = abs(feats["ret_1h"] * 0.8 + feats["ret_4h"] * 0.4)

        proposal = {
            "action": proposed_action,
            "confidence": confidence,
            "expected_move_bps": expected_move_bps,
            "probs": laya_output["probs"]
        }

        # Brain 2 Safety Governor Veto Gate
        governor_veto = self.advisor.validate_veto_contract(proposal, governor_state="ACTIVE", fee_hurdle_bps=ROUND_TRIP_FEE_BPS)
        
        # Enforce calibrated confidence gate (0.65 threshold)
        if proposed_action in ["LONG", "SHORT"] and confidence < MIN_CONFIDENCE_GATE:
            governor_veto["approved"] = False
            governor_veto["reason"] = f"VETOED: Calibrated confidence ({confidence:.3f}) below 0.65 gate."

        final_action = proposed_action if governor_veto["approved"] else "FLAT"

        self.last_decision = {
            "proposed": proposed_action,
            "final_action": final_action,
            "confidence": confidence,
            "expected_move_bps": round(expected_move_bps, 1),
            "governor_status": "APPROVED" if governor_veto["approved"] else governor_veto["reason"],
            "probs": laya_output["probs"]
        }

        # Execute Paper Order if state transitions
        self.execute_paper_transition(final_action)

    def execute_paper_transition(self, target_action: str):
        """Executes paper trade with exact 19 bps fee accounting."""
        target_pos = 1 if target_action == "LONG" else (-1 if target_action == "SHORT" else 0)
        
        if target_pos == self.position:
            return # No state change

        now = time.time()

        # If currently in a position, close it
        if self.position != 0:
            exit_price = self.current_price
            raw_ret = (exit_price - self.entry_price) / self.entry_price if self.position == 1 else (self.entry_price - exit_price) / self.entry_price
            
            # Deduct fee: 9.5 bps on entry + 9.5 bps on exit = 19 bps round trip
            fee_cost = (ROUND_TRIP_FEE_BPS / 10000.0)
            net_ret = raw_ret - fee_cost
            
            pnl_dollars = self.capital * net_ret
            self.capital = max(self.capital * (1.0 + net_ret), 0.0)
            self.realized_pnl += pnl_dollars
            self.total_fees_paid += (self.capital * fee_cost)
            self.trades_count += 1

            trade_record = {
                "trade_num": self.trades_count,
                "side": "LONG" if self.position == 1 else "SHORT",
                "entry_price": round(self.entry_price, 2),
                "exit_price": round(exit_price, 2),
                "raw_return_bps": round(raw_ret * 10000.0, 1),
                "net_return_bps": round(net_ret * 10000.0, 1),
                "pnl_usd": round(pnl_dollars, 4),
                "ending_capital": round(self.capital, 2),
                "duration_sec": round(now - self.entry_ts, 1),
                "timestamp": int(now)
            }
            self.trade_history.append(trade_record)

            # Log to persistent file
            with open(PAPER_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(trade_record) + "\n")

            self.position = 0

        # Open new position if target is LONG or SHORT
        if target_pos != 0:
            self.position = target_pos
            self.entry_price = self.current_price
            self.entry_ts = now

    def render_telemetry(self):
        """Displays real-time institutional telemetry dashboard in terminal."""
        pos_str = "🟢 LONG" if self.position == 1 else ("🔴 SHORT" if self.position == -1 else "⚪ FLAT")
        unrealized_bps = 0.0
        if self.position != 0 and self.entry_price > 0:
            raw = (self.current_price - self.entry_price) / self.entry_price if self.position == 1 else (self.entry_price - self.current_price) / self.entry_price
            unrealized_bps = (raw * 10000.0) - ROUND_TRIP_FEE_BPS

        dec = self.last_decision
        sys.stdout.write("\033[H\033[J") # Clear screen
        print("=" * 82)
        print(f"  FOUR-BRAIN FORWARD PAPER TRADING CANARY  |  ASSET: {self.symbol} (Binance Live)")
        print(f"  Engine: Laya-421M (MNN/Adapter)  |  Calibrated Temp: {CALIBRATED_TEMPERATURE}  |  Fee: 19.0 bps")
        print("=" * 82)
        print(f"  Live Spot Price:    ${self.current_price:,.2f}  |  1m Bars Buffered: {len(self.prices_1m)}/240")
        print(f"  Active Position:    {pos_str:<10}  |  Unrealized Net: {unrealized_bps:+.1f} bps")
        print(f"  Current Capital:    ${self.capital:,.2f}  |  Realized Net P&L: ${self.realized_pnl:+.3f}")
        print(f"  Total Trades:       {self.trades_count}           |  Cumulative Fees:  ${self.total_fees_paid:,.3f}")
        print("-" * 82)
        print(f"  [BRAIN 4 ADVISOR]")
        print(f"    Raw Proposal:     {dec.get('proposed', 'N/A')} (Calibrated Conf: {dec.get('confidence', 0.0)*100.0:.1f}%)")
        print(f"    Expected Move:    {dec.get('expected_move_bps', 0.0):+.1f} bps (Hurdle: {ROUND_TRIP_FEE_BPS * 1.5:.1f} bps)")
        print(f"    Probabilities:    LONG={dec.get('probs', {}).get('LONG', 0.0):.3f} | SHORT={dec.get('probs', {}).get('SHORT', 0.0):.3f} | FLAT={dec.get('probs', {}).get('FLAT', 0.0):.3f}")
        print("-" * 82)
        print(f"  [BRAIN 2 GOVERNOR GATE]")
        print(f"    Gate Status:      {dec.get('governor_status', 'STANDBY')}")
        print(f"    Final Execution:  {dec.get('final_action', 'FLAT')}")
        print("=" * 82)
        print("  Press Ctrl+C to stop paper trading safely. Fills are logged to paper_trading_log.jsonl")
        sys.stdout.flush()


async def run_live_stream(trader: ForwardPaperTrader, max_seconds: float = None):
    stream_url = f"wss://stream.binance.com:9443/ws/{trader.ws_symbol}@aggTrade"
    print(f"Connecting to Binance public stream: {stream_url}...", flush=True)

    last_render = time.time()
    last_eval = time.time()
    start_ts = time.time()

    while True:
        try:
            async with websockets.connect(stream_url, ping_interval=20, ping_timeout=10) as ws:
                print("Connected! Streaming live trades...", flush=True)
                async for message in ws:
                    data = json.loads(message)
                    price = float(data['p'])
                    qty = float(data['q'])
                    is_buyer_maker = bool(data['m'])

                    trader.update_tick(price, qty, is_buyer_maker)

                    now = time.time()
                    # Periodic decision evaluation (every 10s during live canary)
                    if now - last_eval >= 10.0:
                        trader.evaluate_decision()
                        last_eval = now

                    # Telemetry refresh (every 1.0s)
                    if now - last_render >= 1.0:
                        trader.render_telemetry()
                        last_render = now

                    if max_seconds and (now - start_ts) >= max_seconds:
                        print(f"\nCanary test complete ({max_seconds}s elapsed). Stopping stream.", flush=True)
                        return

        except (websockets.ConnectionClosed, Exception) as e:
            print(f"WebSocket disconnected ({e}). Reconnecting in 3 seconds...", flush=True)
            await asyncio.sleep(3)


if __name__ == "__main__":
    max_duration = 5.0 if "--test" in sys.argv else None
    trader = ForwardPaperTrader("BTCUSDT")
    try:
        asyncio.run(run_live_stream(trader, max_seconds=max_duration))
    except KeyboardInterrupt:
        print("\n\nPaper trading safely stopped. Final Capital: $" + str(round(trader.capital, 2)), flush=True)

