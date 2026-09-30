"""
JEV OPENROUTER CLIENT & ADAPTER (BRAIN 4 ENGINE)
===============================================
Interfaces with TypeSafe's Jev model via OpenRouter API.
Loads credentials automatically from D:/projects/QUANT/production_system/.env.

Provides:
- Sanitized market snapshot payload.
- Real live API calls to typesafe/jev-router.
- JSON response parsing with confidence and expected move.
- Fallback/mock safety.
"""

import os
import sys
import json
import urllib.request
from typing import Dict, Any, Optional

# Configure UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def load_env_config() -> Dict[str, str]:
    config = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
    return config


class JevClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, base_url: Optional[str] = None):
        cfg = load_env_config()
        self.api_key = api_key or cfg.get("OPENROUTER_API_KEY", "")
        self.model = model or cfg.get("JEV_MODEL", "typesafe/jev-router")
        self.base_url = base_url or cfg.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.is_live = bool(self.api_key and not self.api_key.startswith("your_"))

    def predict_decision(self, sanitized_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends snapshot to Jev on OpenRouter and returns structured decision.
        """
        if not self.is_live:
            # Fallback if no key configured
            return {
                "action": "FLAT",
                "confidence": 0.50,
                "expected_move_bps": 0.0,
                "regime": "STANDBY_NO_KEY",
                "is_mock": True
            }

        prompt = (
            "You are Brain 4, a quantitative crypto trading advisor. "
            "Analyze the following sanitized market snapshot and choose an action for a 12h horizon.\n\n"
            f"Snapshot:\n{json.dumps(sanitized_snapshot, indent=2)}\n\n"
            "Rules:\n"
            "1. Output MUST be valid JSON only, without commentary.\n"
            "2. Expected move MUST clear the 19 bps fee hurdle.\n"
            "Required JSON format:\n"
            "{\n"
            '  "action": "LONG" | "SHORT" | "FLAT",\n'
            '  "confidence": 0.0 to 1.0,\n'
            '  "probs": {"LONG": 0.0 to 1.0, "SHORT": 0.0 to 1.0, "FLAT": 0.0 to 1.0},\n'
            '  "expected_move_bps": float,\n'
            '  "regime": "TRENDING_BULL" | "TRENDING_BEAR" | "CHOP" | "VOL_SPIKE"\n'
            "}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=req_data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/checkingm13-cell/limbu",
                "X-Title": "Limbu Quant Engine"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                returned_model = result.get("model", self.model)
                content = result["choices"][0]["message"]["content"]
                
                # Clean markdown backticks if returned
                clean_content = content.strip()
                if clean_content.startswith("```json"):
                    clean_content = clean_content[7:]
                elif clean_content.startswith("```"):
                    clean_content = clean_content[3:]
                if clean_content.endswith("```"):
                    clean_content = clean_content[:-3]
                clean_content = clean_content.strip()

                parsed = json.loads(clean_content)
                parsed["is_mock"] = False
                parsed["model"] = returned_model
                
                # Ensure probability vector exists and normalizes properly
                if "probs" not in parsed or not isinstance(parsed["probs"], dict):
                    action = parsed.get("action", "FLAT")
                    conf = float(parsed.get("confidence", 0.50))
                    rem = max(1.0 - conf, 0.0) / 2.0
                    parsed["probs"] = {
                        "LONG": conf if action == "LONG" else rem,
                        "SHORT": conf if action == "SHORT" else rem,
                        "FLAT": conf if action == "FLAT" else rem
                    }
                return parsed

        except Exception as e:
            print(f"[JevClient] API Call warning ({e}), falling back safely to FLAT.")
            return {
                "action": "FLAT",
                "confidence": 0.50,
                "probs": {"LONG": 0.25, "SHORT": 0.25, "FLAT": 0.50},
                "expected_move_bps": 0.0,
                "regime": "API_TIMEOUT_OR_ERROR",
                "is_mock": True,
                "model": "fallback_flat"
            }


if __name__ == "__main__":
    print("Testing JevClient with OpenRouter key from .env...")
    client = JevClient()
    print("API Key loaded:", client.api_key[:15] + "..." if client.api_key else "NONE")
    print("Target Model:", client.model)

    test_snapshot = {
        "relative_returns_bps": {"r15m": 18.0, "r1h": 46.0, "r4h": 110.0},
        "categorical": {
            "momentum_1h": "strongly_positive",
            "momentum_4h": "strongly_bullish",
            "volatility": "normal",
            "order_flow": "aggressive_buying"
        },
        "microstructure": {"vwap_z": 1.3, "funding_apr": 7.5, "taker_ratio": 0.59}
    }

    res = client.predict_decision(test_snapshot)
    print("\n--- Live Jev Response ---")
    print(json.dumps(res, indent=2))
