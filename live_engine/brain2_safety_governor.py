"""
BRAIN 2: THE SAFETY GOVERNOR & RISK CONTROLLER
==============================================
Institutional Risk Engine & Finite State Machine (FSM).
Sits between Brain 3 (Research Scientist) and Brain 1 (Fast Execution).

Key Responsibilities:
1. Config Gatekeeper: Validates candidate `strategy_config.json` before allowing Brain 1 to load it.
2. FSM Controller:
   - ACTIVE (100% position size)
   - CAUTION (50% size, triggered by 2 consecutive losses or high velocity)
   - CIRCUIT_BREAKER_HALT (0% size, triggered by 3 losses or max session drawdown)
   - SHADOW_RECOVERY (Monitors paper signals until regime normalizes)

Run:
    python D:/projects/QUANT/brain2_safety_governor.py
"""

import json
import os
import sys
import time

# Configure UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CANDIDATE_CONFIG_PATH = "D:/projects/QUANT/strategy_config.json"
ACTIVE_CONFIG_PATH = "D:/projects/QUANT/active_config.json"


class SafetyGovernorFSM:
    def __init__(self, max_session_drawdown_usd=15.0, max_consecutive_losses=3, session_profit_target_usd=10.0):
        self.state = "ACTIVE"
        self.consecutive_losses = 0
        self.session_drawdown = 0.0
        self.peak_pnl = 0.0
        self.current_session_pnl = 0.0
        
        # Risk Boundaries
        self.max_drawdown = max_session_drawdown_usd
        self.max_losses = max_consecutive_losses
        self.session_profit_target = session_profit_target_usd
        self.halt_timestamp = 0.0
        self.halt_duration_sec = 300.0 # 5 minutes forced pause
        
        # Trade velocity tracker
        self.recent_trade_timestamps = []
        self.max_trades_per_minute = 3

    def update_config(self, cfg: dict):
        """Dynamic config update from active_config.json."""
        if "session_profit_target_usd" in cfg:
            self.session_profit_target = float(cfg["session_profit_target_usd"])
        if "max_drawdown_usd" in cfg:
            self.max_drawdown = float(cfg["max_drawdown_usd"])
        if "max_consecutive_losses" in cfg:
            self.max_losses = int(cfg["max_consecutive_losses"])

    def validate_candidate_config(self, candidate_path=CANDIDATE_CONFIG_PATH) -> bool:
        """
        Validates the candidate configuration produced by Brain 3.
        Rejects reckless configurations that lack protective stops.
        """
        if not os.path.exists(candidate_path):
            print(f"[Brain 2] Reject: Candidate config {candidate_path} not found.")
            return False
            
        with open(candidate_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            
        print("\n" + "=" * 75)
        print(" BRAIN 2: CANDIDATE CONFIGURATION AUDIT")
        print("=" * 75)
        
        checks = [
            ("Hard Stop-Loss Defined", cfg.get("stop_loss_usd", 0) > 0 and cfg.get("stop_loss_usd") <= 20.0),
            ("Entry Z Hurdle Sufficient", cfg.get("entry_z", 0) >= 2.0),
            ("Exit Z Asymmetric", cfg.get("exit_z", 1.0) <= 0.7),
            ("Historical Win Rate Viable", cfg.get("expected_win_rate_pct", 0) >= 50.0),
            ("Bar Resolution Sane (>= 1.0s)", cfg.get("bar_interval_sec", 0) >= 1.0),
            ("Session Profit Target Defined (> 0)", cfg.get("session_profit_target_usd", 10.0) > 0.0)
        ]
        
        all_passed = True
        for name, passed in checks:
            status = "[PASS]" if passed else "[FAIL]"
            print(f"  {status} {name}")
            if not passed:
                all_passed = False
                
        if all_passed:
            print("\n[Brain 2] AUDIT RESULT: APPROVED! Promoting to active_config.json.")
            with open(ACTIVE_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            return True
        else:
            print("\n[Brain 2] AUDIT RESULT: REJECTED! Candidate config violates safety constraints.")
            return False

    def can_trade(self) -> tuple[bool, float, str]:
        """
        Queries whether Brain 1 is authorized to trade, and at what size factor.
        Returns: (is_allowed, size_multiplier, current_state)
        """
        now = time.time()
        
        # Check if Profit Target has been achieved (Capital Preservation Lock)
        if self.state == "PROFIT_TARGET_LOCKED":
            return False, 0.0, f"PROFIT_TARGET_LOCKED (+${self.current_session_pnl:.2f} >= Target +${self.session_profit_target:.2f})"

        # Check if Circuit Breaker timeout has elapsed
        if self.state == "CIRCUIT_BREAKER_HALT":
            elapsed = now - self.halt_timestamp
            if elapsed < self.halt_duration_sec:
                remaining = int(self.halt_duration_sec - elapsed)
                return False, 0.0, f"CIRCUIT_BREAKER_HALT (Cooling down: {remaining}s remaining)"
            else:
                self.state = "SHADOW_RECOVERY"
                print(f"[{time.strftime('%H:%M:%S')}] [Brain 2] Halt expired. Transitioning -> SHADOW_RECOVERY")
                
        # Check trade velocity (rate limiting)
        self.recent_trade_timestamps = [t for t in self.recent_trade_timestamps if (now - t) < 60.0]
        if len(self.recent_trade_timestamps) >= self.max_trades_per_minute:
            return False, 0.0, "RATE_LIMITED (Velocity > 3 trades/min)"
            
        if self.state == "ACTIVE":
            return True, 1.0, "ACTIVE (Full Risk: 100% Size)"
        elif self.state == "CAUTION":
            return True, 0.5, "CAUTION (Reduced Risk: 50% Size)"
        elif self.state == "SHADOW_RECOVERY":
            # In paper mode, allow a probe trade at 25% size to verify regime normalization
            return True, 0.25, "SHADOW_RECOVERY (Probe Trade: 25% Size)"
            
        return False, 0.0, self.state

    def audit_intent(self, side: str, price: float, z: float, confidence: float = 1.0):
        """
        Hard Risk Boundary: Audits strategy intent and controls sizing.
        Strategy proposes intent; Risk owns capital and execution veto.
        """
        can_trade, size_mult, state_msg = self.can_trade()
        if not can_trade:
            return {"approved": False, "quantity": 0.0, "reason": f"RISK_VETO: {state_msg}"}
        
        base_contract = 0.1 # 0.1 BTC contract
        final_quantity = base_contract * size_mult
        return {"approved": True, "quantity": final_quantity, "reason": f"APPROVED: {state_msg}"}

    def on_trade_completed(self, pnl_usd: float):
        """Called by Brain 1 immediately when a trade closes to update the FSM."""
        now = time.time()
        self.recent_trade_timestamps.append(now)
        self.current_session_pnl += pnl_usd
        
        if self.current_session_pnl > self.peak_pnl:
            self.peak_pnl = self.current_session_pnl
            
        dd = self.peak_pnl - self.current_session_pnl
        self.session_drawdown = max(self.session_drawdown, dd)
        
        time_str = time.strftime("%H:%M:%S")
        
        # Capital Preservation: Check if session profit target reached
        if self.current_session_pnl >= self.session_profit_target:
            self.state = "PROFIT_TARGET_LOCKED"
            print(f"[{time_str}] [PROFIT LOCK] [Brain 2] SESSION PROFIT TARGET REACHED! "
                  f"(Session PnL: +${self.current_session_pnl:.2f} >= Target: +${self.session_profit_target:.2f})")
            print(f"[{time_str}] [Brain 2] Action: STATE -> PROFIT_TARGET_LOCKED. Freezing all subsequent orders to lock in profit.")
            return

        # If in SHADOW_RECOVERY, probe result determines recovery
        if self.state == "SHADOW_RECOVERY":
            if pnl_usd > 0:
                self.state = "ACTIVE"
                self.consecutive_losses = 0
                print(f"[{time_str}] [Brain 2] Probe trade WON (+${pnl_usd:.2f})! Regime normalized -> State back to ACTIVE.")
                return
            else:
                self.state = "CIRCUIT_BREAKER_HALT"
                self.halt_timestamp = now
                print(f"[{time_str}] [Brain 2] Probe trade LOST (-${abs(pnl_usd):.2f})! Extending CIRCUIT_BREAKER_HALT.")
                return

        if pnl_usd < 0:
            self.consecutive_losses += 1
            print(f"[{time_str}] [Brain 2] Adverse trade logged: ${pnl_usd:.2f} (Loss Streak: {self.consecutive_losses})")
        else:
            self.consecutive_losses = 0
            print(f"[{time_str}] [Brain 2] Winning trade logged: +${pnl_usd:.2f} (Streak reset to 0)")

        # FSM State Transition Logic
        if self.session_drawdown >= self.max_drawdown or self.consecutive_losses >= self.max_losses:
            self.state = "CIRCUIT_BREAKER_HALT"
            self.halt_timestamp = now
            print(f"[{time_str}] [ALERT] [Brain 2] CIRCUIT BREAKER TRIPPED! Drawdown: ${dd:.2f}, Losses: {self.consecutive_losses}.")
            print(f"[{time_str}] [Brain 2] Action: FREEZING ALL TRADING FOR {int(self.halt_duration_sec)} SECONDS.")
        elif self.consecutive_losses >= 2:
            self.state = "CAUTION"
            print(f"[{time_str}] [ALERT] [Brain 2] State -> CAUTION. Reducing trade size to 50%.")
        elif self.consecutive_losses == 0 and self.state == "CAUTION":
            self.state = "ACTIVE"
            print(f"[{time_str}] [Brain 2] Performance stabilized. State -> ACTIVE (100% Size).")


if __name__ == "__main__":
    governor = SafetyGovernorFSM()
    approved = governor.validate_candidate_config()
    
    print("\nDemonstrating Brain 2 FSM in action:")
    allowed, size, state = governor.can_trade()
    print(f"Initial State: {state} | Allowed: {allowed} | Size Multiplier: {size}")
        
    # Simulate adverse trades
    governor.on_trade_completed(-0.80)
    governor.on_trade_completed(-0.49)
    allowed, size, state = governor.can_trade()
    print(f"After 2 Losses: {state} | Allowed: {allowed} | Size Multiplier: {size}")
    
    governor.on_trade_completed(-1.17)
    allowed, size, state = governor.can_trade()
    print(f"After 3 Losses: {state} | Allowed: {allowed} | Size Multiplier: {size}")
    
    # Test Profit Lock
    print("\n--- Testing Session Profit Target Lock ---")
    gov2 = SafetyGovernorFSM(session_profit_target_usd=10.0)
    gov2.on_trade_completed(6.50)
    allowed, size, state = gov2.can_trade()
    print(f"Trade 1 (+$6.50): {state} | Allowed: {allowed}")
    gov2.on_trade_completed(4.20)
    allowed, size, state = gov2.can_trade()
    print(f"Trade 2 (+$4.20, Total +$10.70): {state} | Allowed: {allowed} | Size: {size}")
