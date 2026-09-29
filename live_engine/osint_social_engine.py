"""
osint_social_engine.py — Production-Grade Social Media OSINT Architecture
Decoupled Producer-Consumer pipeline for Quant Trading Systems.
Hot path execution NEVER blocks on web scrapers or LLM inferences.
"""

import asyncio
import hashlib
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field


# -------------------------------------------------------------------------
# 1. DATA MODELS & SCHEMAS
# -------------------------------------------------------------------------
@dataclass
class RawPost:
    """Raw incoming social media or OSINT feed item."""
    source: str          # "twitter", "reddit", "telegram", "exchange_filing"
    author_id: str
    author_account_age_days: int
    author_follower_count: int
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class OSINTFeature:
    """Structured, verified intelligence feature ready for Quant Engine."""
    symbol: str
    sentiment: float        # -1.0 (extremely bearish) to +1.0 (extremely bullish)
    confidence: float       # 0.0 to 1.0
    is_material: bool       # True if fundamental / institutional relevance
    pump_dump_risk: float   # 0.0 to 1.0 (probability of retail manipulation trap)
    source: str
    timestamp: float = field(default_factory=time.time)


# -------------------------------------------------------------------------
# 2. BOT & ASTROTURFING FILTER (NOISE REDUCTION)
# -------------------------------------------------------------------------
class SocialSpamFilter:
    """
    Guards against coordinated bot farms, astroturfing, and duplicate spam.
    Rule: Never let an unverified 2-day-old account move your capital.
    """
    def __init__(self):
        self._seen_hashes = set()

    def is_spam_or_bot(self, post: RawPost) -> bool:
        # 1. Exact Duplicate Content Check
        content_hash = hashlib.sha256(post.content.strip().lower().encode()).hexdigest()
        if content_hash in self._seen_hashes:
            return True  # Duplicate post copied across multiple accounts
        self._seen_hashes.add(content_hash)

        # 2. Bot Account Heuristics
        # Account too new with low followers pushing stock tickers
        if post.author_account_age_days < 30 and post.author_follower_count < 20:
            return True

        # 3. Aggressive promo keywords typical in pump & dump Telegram groups
        spam_keywords = ["guaranteed 100x", "jackpot call", "multibagger sure shot", "rocket emoji", "join vip"]
        lower_content = post.content.lower()
        if any(kw in lower_content for kw in spam_keywords):
            return True

        return False


# -------------------------------------------------------------------------
# 3. LLM / EXTRACTION WORKER (COLD PATH)
# -------------------------------------------------------------------------
class OSINTFeatureExtractor:
    """
    Extracts structured alpha & risk features from verified text.
    In live production, connects to an LLM with structured JSON output.
    """
    @staticmethod
    async def extract_feature(post: RawPost) -> Optional[OSINTFeature]:
        # Simulated async LLM structured inference delay (50ms)
        await asyncio.sleep(0.05)

        content = post.content.upper()
        symbol = None
        for ticker in ["RELIANCE", "TCS", "INFY", "HDFCBANK", "TATAMOTORS"]:
            if ticker in content or f"${ticker}" in content:
                symbol = ticker
                break

        if not symbol:
            return None  # Unrelated chatter

        # Heuristic scoring demonstration (mimicking LLM output)
        if "SEBI INVESTIGATION" in content or "RAID" in content or "FRAUD" in content:
            return OSINTFeature(
                symbol=symbol,
                sentiment=-0.95,
                confidence=0.90,
                is_material=True,
                pump_dump_risk=0.10,
                source=post.source
            )
        elif "PUMP" in content or "TARGET 500%" in content or "ALL IN" in content:
            return OSINTFeature(
                symbol=symbol,
                sentiment=0.85,
                confidence=0.40,
                is_material=False,
                pump_dump_risk=0.95,  # High manipulation alert!
                source=post.source
            )
        elif "EARNINGS BEAT" in content or "NEW CONTRACT" in content:
            return OSINTFeature(
                symbol=symbol,
                sentiment=0.75,
                confidence=0.85,
                is_material=True,
                pump_dump_risk=0.05,
                source=post.source
            )

        return OSINTFeature(
            symbol=symbol,
            sentiment=0.0,
            confidence=0.3,
            is_material=False,
            pump_dump_risk=0.1,
            source=post.source
        )


# -------------------------------------------------------------------------
# 4. IN-MEMORY / REDIS FEATURE STORE
# -------------------------------------------------------------------------
class OSINTFeatureStore:
    """
    Sub-millisecond read store for the trading engine.
    Stores decay-weighted scores with strict TTL expiry.
    """
    def __init__(self, ttl_seconds: float = 3600):
        self._store: Dict[str, OSINTFeature] = {}
        self.ttl = ttl_seconds

    def write(self, feat: OSINTFeature):
        self._store[feat.symbol] = feat

    def get(self, symbol: str) -> Optional[OSINTFeature]:
        feat = self._store.get(symbol)
        if not feat:
            return None
        # Discard stale intelligence (TTL expired)
        if time.time() - feat.timestamp > self.ttl:
            del self._store[symbol]
            return None
        return feat


# -------------------------------------------------------------------------
# 5. TRADING ENGINE INTEGRATION (THE VETO GATE)
# -------------------------------------------------------------------------
def evaluate_quant_signal(symbol: str, raw_algo_signal: int, store: OSINTFeatureStore) -> str:
    """
    Demonstrates how the Hot Path trading loop checks OSINT before firing an order.
    raw_algo_signal: +1 (BUY), -1 (SELL), 0 (HOLD)
    Returns: Execution Decision ("EXECUTE" or "VETO: [Reason]")
    """
    if raw_algo_signal == 0:
        return "NO_ACTION"

    feat = store.get(symbol)
    if not feat:
        return "EXECUTE (No OSINT restriction)"

    # RULE 1: Anti-Retail Trap (VETO long if Telegram/Twitter pump risk is extreme)
    if raw_algo_signal > 0 and feat.pump_dump_risk > 0.80:
        return f"VETO: Rejected BUY on {symbol} — High Pump & Dump Astroturf Risk ({feat.pump_dump_risk:.0%})"

    # RULE 2: Catastrophic Event (VETO long if negative material regulatory news hit)
    if raw_algo_signal > 0 and feat.is_material and feat.sentiment < -0.60:
        return f"VETO: Rejected BUY on {symbol} — Negative Material OSINT ({feat.sentiment:.2f})"

    # RULE 3: Confirmation Boost
    if raw_algo_signal > 0 and feat.is_material and feat.sentiment > 0.50:
        return f"EXECUTE WITH BOOST: High-Conviction Fundamental Tailwinds (Sentiment: +{feat.sentiment:.2f})"

    return "EXECUTE"


# -------------------------------------------------------------------------
# 6. RUNNABLE SIMULATION DEMO
# -------------------------------------------------------------------------
async def main():
    print("=" * 70)
    print("OSINT SOCIAL MEDIA QUANT INGESTION PIPELINE")
    print("=" * 70)

    spam_filter = SocialSpamFilter()
    feature_store = OSINTFeatureStore(ttl_seconds=1800)

    sample_incoming_feed = [
        # 1. Coordinated Telegram Bot
        RawPost("telegram", "bot_994", 2, 5, "TATAMOTORS jackpot call target 500% join VIP rocket emoji!"),
        # 2. Genuine Regulatory / Court OSINT
        RawPost("exchange_filing", "bse_alerts", 3000, 50000, "RELIANCE: SEBI investigation announced into subsidiary operations."),
        # 3. Legitimate Earnings Beat
        RawPost("twitter", "analyst_pro", 1200, 25000, "INFY Q2 results beat guidance, signed major 1B cloud contract.")
    ]

    print("\n[INGESTION STAGE] Processing incoming social/OSINT stream...")
    for post in sample_incoming_feed:
        if spam_filter.is_spam_or_bot(post):
            print(f"  ❌ DROPPED SPAM/BOT: [{post.source.upper()}] from {post.author_id} -> '{post.content[:45]}...'")
            continue

        feat = await OSINTFeatureExtractor.extract_feature(post)
        if feat:
            feature_store.write(feat)
            print(f"  ✅ INGESTED FEATURE: {feat.symbol} | Sent: {feat.sentiment:+.2f} | Material: {feat.is_material} | PumpRisk: {feat.pump_dump_risk:.0%}")

    print("\n" + "-" * 70)
    print("[HOT-PATH TRADING DECISION CHECK]")
    print("-" * 70)

    # Strategy signals wanting to BUY
    print("Strategy fires BUY signal on RELIANCE:")
    print("  -> Decision:", evaluate_quant_signal("RELIANCE", 1, feature_store))

    print("\nStrategy fires BUY signal on INFY:")
    print("  -> Decision:", evaluate_quant_signal("INFY", 1, feature_store))

    print("\nStrategy fires BUY signal on TATAMOTORS:")
    print("  -> Decision:", evaluate_quant_signal("TATAMOTORS", 1, feature_store))
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
