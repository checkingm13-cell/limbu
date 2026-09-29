# 05 — Momentum, Trend & AI Feature Layer

> **Chunk**: ALPHA-2. Message: *"Mean reversion ma tame 'kem' puchho cho. Momentum ma tame 'kem' puchhata nathi — tame fakt follow karo cho, ane loss jaldi kapo cho."*

---

## 1. WHY — be alpha families ek j system ma

```
   MEAN REVERSION                  MOMENTUM / TREND
   ───────────────                 ────────────────
   Win rate  : 60–75%              Win rate  : 30–40%
   Avg win   : nano                Avg win   : moto
   Avg loss  : moto  ⚠️            Avg loss  : nano
   Kills you : ek tail event       Kills you : chop/sideways ma 20 nana cuts
   Works in  : range/sideways      Works in  : trending regime
```
**Banne ek j regime ma na chale.** Etle regime detection (File 04 nu Hurst/ADF) fakt filter nathi — **e j nakki kare che ke aaje kayu engine on karvu.**

---

## 2. EMA — exponentially weighted memory

```
   EMA_t = α · P_t + (1 − α) · EMA_{t−1}

              2
   α  =  ──────────         (span = N periods)
           N + 1
```

**SMA vs EMA — ek line ma:** SMA ma 20 pehla no bhav ane kaal no bhav same weight; EMA ma kaal no bhav 2x-3x weight. Etle EMA responsive, pan noisy.

```
   weight
    │ █                       EMA: exponential decay, INFINITE memory
    │ █▇                      SMA: flat weight, HARD cutoff
    │ █▇▆
    │ █▇▆▅▄▃▂▁▁▁
    └──────────────────► age of data
```

**O(1) streaming implementation:**
```python
class EMA:
    def __init__(self, span):
        self.alpha = 2.0 / (span + 1.0)
        self.value = None
        self.n = 0
    def update(self, x):
        self.n += 1
        self.value = x if self.value is None else \
                     self.alpha * x + (1 - self.alpha) * self.value
        return self.value
    @property
    def ready(self):
        return self.n >= int(2 / self.alpha)   # ~span*2 warm-up
```
> **Live vs backtest mismatch no classic source:** pandas `df.ewm(span=20, adjust=True)` (default!) shuruat ma bias-corrected weights vapare che, streaming EMA nahi. Backtest ma `adjust=False` set karo, nahi to pehla ~40 bars ma values match nahi thay ane tame bug shodhta rehso.

### EMA Crossover — ane eni honest reality

```
   Price
        │              ╭────────  fast EMA (9)  ── responsive
        │         ╭────╯
        │    ╭────╯  ▲
        │────╯       │ GOLDEN CROSS (fast > slow) → LONG
        │   ─────────┼───────────  slow EMA (21) ── stable
        │            │
        │  DEATH CROSS (fast < slow) → SHORT/EXIT
```

```python
def ema_signal(fast: EMA, slow: EMA, prev_state):
    if not (fast.ready and slow.ready): return 0, prev_state
    now = 1 if fast.value > slow.value else -1
    crossed = (prev_state != 0 and now != prev_state)
    return (now if crossed else 0), now
```

⚠️ **Naked EMA cross ~random che.** Sideways market ma whipsaw: 15 crosses, 15 losses, costs sathe −4%. **Har production momentum system ma 3 filter hoy che:**

```
  FILTER 1 — TREND STRENGTH   : ADX > 22, ke slope(slow EMA) > threshold
  FILTER 2 — VOLATILITY       : ATR percentile 30–85 vachche (bahu shant/bahu pagal nahi)
  FILTER 3 — CONFIRMATION     : volume > 1.5 × avg, ke price > prior swing high
```
Filters vagar EMA cross = cost generator.

---

## 3. ATR — volatility nu universal unit

**True Range** gap ne handle kare che, `high-low` nahi kare:
```
TR_t = max(  high − low,
             |high − prev_close|,      ← gap up
             |low  − prev_close|  )    ← gap down

ATR = Wilder's smoothed average of TR (period 14 standard)
ATR_t = (ATR_{t−1} × (n−1) + TR_t) / n
```

```python
class ATR:
    def __init__(self, period=14):
        self.p = period; self.value = None; self.prev_close = None; self.n = 0
    def update(self, high, low, close):
        tr = (high - low) if self.prev_close is None else max(
            high - low, abs(high - self.prev_close), abs(low - self.prev_close))
        self.n += 1
        self.value = tr if self.value is None else \
                     (self.value * (self.p - 1) + tr) / self.p
        self.prev_close = close
        return self.value
    @property
    def ready(self): return self.n >= self.p * 2
```

### ATR kem system no backbone che — 5 use

```
┌───────────────────────────────────────────────────────────────┐
│ 1. STOP-LOSS       stop = entry − 2×ATR   (fixed % nahi)      │
│ 2. POSITION SIZE   qty = risk_₹ / (2×ATR)  ← File 06 no core  │
│ 3. TARGET          target = entry + 3×ATR  (R:R normalize)    │
│ 4. REGIME FILTER   ATR/price percentile → trade karvu ke nahi │
│ 5. BREAKOUT FILTER move > 0.5×ATR hoy to j "real" ganvu       │
└───────────────────────────────────────────────────────────────┘
```

**Kem fixed % kharab che:**
```
   RELIANCE   daily ATR ≈ 1.2%  → 2% stop = 1.7 ATR  (tight-ish, ok)
   YESBANK    daily ATR ≈ 4.5%  → 2% stop = 0.44 ATR (noise ma instant hit)
   
   Same 2% stop, be tadd alag risk. ATR multiple = APPLES TO APPLES.
```
> **Aa insight ek j che je retail ane systematic trader ne alag pade che.** Badhu ATR units ma vichaaro — stop, target, size, expectancy. Tyare tame cross-symbol, cross-regime comparable thai jao.

---

## 4. Donchian Channels & Breakout Logic

```
   Upper = highest HIGH of last N bars
   Lower = lowest  LOW  of last N bars
   Mid   = (Upper + Lower) / 2

   Price
   2480 ┤ ══════════════════════════●  ← BREAKOUT: close > Upper(20)
        │                          ╱      → LONG
   2460 ┤ Upper(20) ───────────────
        │        ╭──╮    ╭───╮ ╭──╯
   2440 ┤   ╭────╯  ╰────╯   ╰─╯
        │───╯
   2420 ┤ Lower(20) ─────────────────  ← exit for long (Donchian trailing)
```

```python
class Donchian:
    def __init__(self, n):
        self.hi = RollingWindow(n); self.lo = RollingWindow(n)
    def update(self, high, low):
        self.hi.push(high); self.lo.push(low)
    @property
    def upper(self): return self.hi.buf[:self.hi.n].max()
    @property
    def lower(self): return self.lo.buf[:self.lo.n].min()
```

> **Historical note — Turtle Traders (1983):** Richard Dennis e beginners ne fakt Donchian breakout + ATR sizing + hard stop shikhavyu. Kai discretion nahi. Group e ~4 varsh ma 100M+ kamaya. **Lesson: edge rules ma nahi, rule follow karva ni consistency + sizing ma hati.**

**Breakout confirmation — false breakout j main enemy che:**
```python
def is_valid_breakout(bar, donch, atr, vol_ma, prev_upper):
    return all([
        bar.close > donch.upper,                    # 1. level break
        bar.close > prev_upper + 0.25 * atr.value,  # 2. meaningful margin
        bar.volume > 1.5 * vol_ma,                  # 3. participation
        (bar.close - bar.low) / max(bar.high - bar.low, 1e-9) > 0.6,  # 4. strong close
    ])
```
Aa 4 conditions false-breakout rate ne roughly half kari nakhe che (cost: ochha signals, ane ketlak sacha breakout miss).

### Trailing exit — momentum ma exit j alpha che
```
Chandelier Stop:  stop = highest_high_since_entry − 3 × ATR
   → trend sathe uper khase, kadi niche nahi ave
   → "let winners run, cut losers fast" nu mechanical form
```

---

## 5. AI / LLM Feature Layer (optional, pan design carefully)

> **Positioning:** LLM ne **trader** na banavo. **Feature extractor** banavo. LLM ne "buy ke sell?" puchhvu = unbacktestable, non-deterministic, latency-heavy garbage. LLM ne "aa news ma guidance cut che ke nahi, 0–1 ma?" puchhvu = structured numeric feature.

### Architecture — hot path thi BAHAR

```
   ┌──────────────┐
   │ NEWS SOURCES │ RSS · exchange filings · broker feeds
   └──────┬───────┘
          │ async worker (alag process)
   ┌──────▼──────────────────────────────┐
   │ DEDUPE  →  RELEVANCE (symbol match) │
   └──────┬──────────────────────────────┘
          │
   ┌──────▼──────────────┐
   │ LLM  (structured)   │  Pydantic schema, temperature=0
   │ → sentiment −1..+1  │  cache by content hash
   │ → impact_horizon    │
   │ → confidence        │
   └──────┬──────────────┘
          │ write
   ┌──────▼──────────────┐         ┌──────────────────────┐
   │ Redis: feat:SYMBOL  │◄────────│ STRATEGY (hot path)   │
   │ {score, ts, conf}   │  READ   │ O(1) lookup, never    │
   │ TTL = 4 hours       │  ONLY   │ blocks on LLM         │
   └─────────────────────┘         └──────────────────────┘
```

**Non-negotiable:** strategy loop **kadi** LLM call na kare. Fakt Redis mathi last computed value vanche, ane e stale hoy to score = 0 gane.

```python
from pydantic import BaseModel, Field
from typing import Literal

class NewsSignal(BaseModel):
    sentiment: float = Field(..., ge=-1.0, le=1.0,
        description="-1 strongly bearish for the stock, +1 strongly bullish, 0 neutral")
    category: Literal["earnings","guidance","regulatory","mna",
                      "management","macro","operational","noise"]
    horizon: Literal["intraday","days","weeks","structural"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_material: bool = Field(..., description="Would a professional trader act on this?")
    reasoning: str = Field(..., max_length=200)

SYSTEM = """You are a sell-side equity analyst scoring news for an Indian
equities trading system. Score sentiment ONLY from the perspective of the
named stock's next price move. Rewritten wire copy, routine disclosures and
opinion pieces are 'noise' with is_material=false. Return JSON only."""
```

```python
import asyncio, hashlib, json

class SentimentWorker:
    def __init__(self, redis, llm, concurrency=5):
        self.r, self.llm = redis, llm
        self.sem = asyncio.Semaphore(concurrency)     # rate limit guard

    async def score(self, symbol: str, headline: str, body: str = ""):
        key = "llm:" + hashlib.sha256((symbol+headline).encode()).hexdigest()[:16]
        if cached := self.r.get(key):                 # dedupe: same story 6 wires par
            return NewsSignal(**json.loads(cached))
        async with self.sem:
            try:
                sig = await self.llm.structured(SYSTEM, f"{symbol}\n{headline}\n{body}",
                                                schema=NewsSignal, temperature=0)
            except Exception:
                return None                            # ⚠️ fail → NO feature, not a guess
        self.r.setex(key, 14400, sig.model_dump_json())
        self.r.hset(f"feat:{symbol}", mapping={
            "sent": sig.sentiment if sig.is_material else 0.0,
            "conf": sig.confidence, "ts": time.time()})
        return sig
```

### Feature ne strategy ma kem vaparvi — **gate, driver nahi**

```python
def apply_news_gate(base_signal: int, symbol, r, max_age=1800):
    f = r.hgetall(f"feat:{symbol}")
    if not f or time.time() - float(f["ts"]) > max_age:
        return base_signal                          # stale → ignore, no penalty
    s = float(f["sent"]) * float(f["conf"])
    if base_signal > 0 and s < -0.4: return 0       # VETO: long vs bad news
    if base_signal < 0 and s > +0.4: return 0       # VETO: short vs good news
    return base_signal
```

> **Kem gate ane driver nahi:** news-driven entry ma tame institutional flow sathe race ma cho ane 200ms latency sathe haaro cho. News-based **veto** ma tame fakt ek kharab trade avoid karo cho — e race nathi, e risk management che. Aaj ma asymmetry che.

### Backtesting problem (honest ho)
- **Point-in-time news joie** — aaje ni news article ma later edits hoy che
- **LLM ne pachhal thi knowledge hoy che** — 2023 nu headline scoring karso to model ne khabar che ke pachhi shu thayu = **lookahead bias via model weights**. Aa tamne dekhase nahi, pan backtest inflate karse.
- Fix: fakt **forward test** karo aa layer ne, ke strictly pre-cutoff models vaparo. Historical LLM sentiment backtest ne skeptically jovo.

**Cost:** ~₹0.5–2 per article. 200 articles/day ≈ ₹300/day. Cache/dedupe vagar 5x.

---

## 6. FAILURE MODES

| Failure | Shu thay | Guard |
|---|---|---|
| Naked EMA cross | Whipsaw, 15 losses sideways ma | ADX/slope + vol + volume filters |
| `ewm(adjust=True)` | Live ≠ backtest pehla 40 bars | `adjust=False` |
| Fixed % stop | Volatile scrip ma instant hit | ATR multiple |
| False breakout | Buy at top, revert | 4-condition confirmation |
| Trend exit late | Aakho profit pachho aapyo | Chandelier trailing stop |
| LLM in hot path | Loop 2s block, ticks pile | Async worker + Redis read-only |
| LLM as decision maker | Unbacktestable, non-deterministic | Feature/veto only |
| LLM hallucinated score | Garbage feature | Pydantic validation + `is_material` + confidence weight |
| Both engines saathe on | Self-conflicting orders | Regime switch, ek j active |

---

## Margin Questions
1. Momentum ane mean reversion ni win-rate/avg-loss profile ulti kem che?
2. ATR na 5 use kaya?
3. Fixed % stop vs ATR stop — YESBANK example ma shu thay?
4. Breakout confirmation na 4 condition?
5. LLM ne "driver" nahi "gate" kem banavvu?
6. LLM sentiment backtest ma chhupelo lookahead bias kaya thi ave che?
