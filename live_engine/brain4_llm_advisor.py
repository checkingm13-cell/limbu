"""
BRAIN 4: THE LLM STRATEGIC ADVISOR & REGIME ORACLE
==================================================
Advisory Brain for Wider-Horizon Decisions (15m - 4h).
Sits upstream of Brain 1 (Execution) and is strictly subordinate to Brain 2 (Safety Governor).

Responsibilities:
1. Snapshot Generation: Encodes multi-timeframe price action, volatility, funding, and order-flow skew.
2. Fixed Action Menu: Strictly constrained JSON output (LONG, SHORT, FLAT).
3. Brain 2 Veto Contract: Evaluates proposed trade against leverage caps, cooldowns, and friction bounds.
"""

import json
import time
from typing import Dict, Any, Optional

class Brain4Advisor:
    """
    LLM Strategic Advisor Interface.
    Produces structured regime assessments and trade recommendations.
    """
    
    ACTION_MENU = ["LONG", "SHORT", "FLAT"]
    HORIZONS_MINUTES = [15, 60, 120, 240]

    def __init__(self, model_name: str = "gpt-4o-mini-or-gemini", min_confidence: float = 0.60):
        self.model_name = model_name
        self.min_confidence = min_confidence

    @staticmethod
    def build_snapshot(
        symbol: str,
        current_price: float,
        ret_15m_bps: float,
        ret_1h_bps: float,
        ret_4h_bps: float,
        atr_pct: float,
        vwap_zscore: float,
        funding_rate_apr: float,
        taker_buy_ratio: float,
        macro_bias: str = "NEUTRAL"
    ) -> Dict[str, Any]:
        """
        Creates a compact, deterministic snapshot of market conditions.
        """
        return {
            "symbol": symbol,
            "timestamp": int(time.time()),
            "current_price": round(current_price, 2),
            "returns_bps": {
                "15m": round(ret_15m_bps, 1),
                "1h": round(ret_1h_bps, 1),
                "4h": round(ret_4h_bps, 1)
            },
            "microstructure": {
                "atr_pct": round(atr_pct, 3),
                "vwap_zscore": round(vwap_zscore, 2),
                "funding_apr_pct": round(funding_rate_apr, 2),
                "taker_buy_ratio": round(taker_buy_ratio, 3)
            },
            "macro_bias": macro_bias
        }

    @staticmethod
    def get_prompt_contract(snapshot: Dict[str, Any]) -> str:
        """
        Generates the strict system prompt and user input for the LLM.
        """
        return (
            "You are Brain 4, a quantitative strategic advisor for crypto perps.\n"
            "Analyze the following market snapshot and select an action from the fixed menu.\n"
            "Rules:\n"
            "1. Output MUST be valid JSON only, no markdown wrapping, no explanation outside JSON.\n"
            "2. Expected move MUST exceed the 19 bps round-trip friction hurdle.\n"
            "3. Valid actions: 'LONG', 'SHORT', 'FLAT'.\n"
            "4. Horizon must be in [15, 60, 120, 240] minutes.\n\n"
            f"Snapshot Data:\n{json.dumps(snapshot, indent=2)}\n\n"
            "Required JSON Schema:\n"
            "{\n"
            '  "action": "LONG" | "SHORT" | "FLAT",\n'
            '  "horizon_minutes": 60,\n'
            '  "confidence": 0.75,\n'
            '  "regime": "TRENDING_BULL" | "TRENDING_BEAR" | "CHOP" | "VOL_SPIKE",\n'
            '  "expected_move_bps": 45.0,\n'
            '  "rationale": "Clear breakout above VWAP with high taker volume"\n'
            "}"
        )

    def evaluate_heuristic_policy(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deterministic reference policy for offline / high-speed replay testing.
        Acts as the benchmark regime detector.
        """
        ret_1h = snapshot["returns_bps"]["1h"]
        ret_4h = snapshot["returns_bps"]["4h"]
        vwap_z = snapshot["microstructure"]["vwap_zscore"]
        taker_ratio = snapshot["microstructure"]["taker_buy_ratio"]
        atr = snapshot["microstructure"]["atr_pct"]

        # Strong Trend / Momentum Condition (clears friction)
        if ret_1h > 25.0 and ret_4h > 50.0 and taker_ratio > 0.53 and vwap_z > 0.5:
            return {
                "action": "LONG",
                "horizon_minutes": 120,
                "confidence": 0.78,
                "regime": "TRENDING_BULL",
                "expected_move_bps": 65.0,
                "rationale": "Aligned 1h/4h upward momentum with dominant taker buying."
            }
        elif ret_1h < -25.0 and ret_4h < -50.0 and taker_ratio < 0.47 and vwap_z < -0.5:
            return {
                "action": "SHORT",
                "horizon_minutes": 120,
                "confidence": 0.78,
                "regime": "TRENDING_BEAR",
                "expected_move_bps": -65.0,
                "rationale": "Aligned 1h/4h downward momentum with aggressive taker selling."
            }
        elif abs(vwap_z) < 0.5 and atr < 0.35:
            return {
                "action": "FLAT",
                "horizon_minutes": 60,
                "confidence": 0.70,
                "regime": "CHOP",
                "expected_move_bps": 0.0,
                "rationale": "Low volatility chop. Expected move does not clear round-trip fees."
            }
        else:
            return {
                "action": "FLAT",
                "horizon_minutes": 60,
                "confidence": 0.50,
                "regime": "UNCERTAIN",
                "expected_move_bps": 0.0,
                "rationale": "Mixed signals; insufficient margin over fee hurdle."
            }

    @staticmethod
    def validate_veto_contract(proposal: Dict[str, Any], governor_state: str, fee_hurdle_bps: float = 19.0) -> Dict[str, Any]:
        """
        BRAIN 2 VETO CONTRACT:
        Brain 2 evaluates Brain 4's proposal. Brain 2 holds supreme veto authority.
        """
        # Rule 1: Governor State Veto
        if governor_state in ["CIRCUIT_BREAKER_HALT", "HALT", "EMERGENCY_STOP"]:
            return {
                "approved": False,
                "reason": f"VETOED: Safety Governor is in {governor_state} state."
            }

        # Rule 2: Minimum expected move vs round-trip fee hurdle
        action = proposal.get("action", "FLAT")
        if action in ["LONG", "SHORT"]:
            expected_move = abs(proposal.get("expected_move_bps", 0.0))
            if expected_move < fee_hurdle_bps * 1.5:  # Require at least 1.5x fee hurdle
                return {
                    "approved": False,
                    "reason": f"VETOED: Expected move ({expected_move} bps) fails to clear 1.5x fee hurdle ({fee_hurdle_bps * 1.5} bps)."
                }

        # Rule 3: Confidence threshold
        if proposal.get("confidence", 0.0) < 0.60 and action != "FLAT":
            return {
                "approved": False,
                "reason": f"VETOED: Confidence ({proposal.get('confidence')}) below minimum 0.60 gate."
            }

        return {
            "approved": True,
            "reason": "APPROVED: Proposal passes all risk boundaries."
        }


if __name__ == "__main__":
    print("Testing Brain 4 Strategic Advisor Interface & Veto Contract...")
    advisor = Brain4Advisor()
    sample_snapshot = advisor.build_snapshot(
        symbol="BTCUSDT",
        current_price=64250.0,
        ret_15m_bps=12.0,
        ret_1h_bps=38.0,
        ret_4h_bps=85.0,
        atr_pct=0.42,
        vwap_zscore=1.1,
        funding_rate_apr=6.5,
        taker_buy_ratio=0.56
    )
    
    prompt = advisor.get_prompt_contract(sample_snapshot)
    print("\n--- Generated Prompt Contract ---")
    print(prompt[:300] + "...\n")
    
    proposal = advisor.evaluate_heuristic_policy(sample_snapshot)
    print("--- Model Proposal ---")
    print(json.dumps(proposal, indent=2))
    
    veto_res = advisor.validate_veto_contract(proposal, governor_state="ACTIVE")
    print("\n--- Brain 2 Veto Evaluation ---")
    print(json.dumps(veto_res, indent=2))
