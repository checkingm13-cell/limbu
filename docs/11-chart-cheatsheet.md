# 11 — Chart Cheatsheet (screen ni samne)

> **Aa file ma vichaarvanu nathi, fakt check karvanu che.** Design mode ahiya nahi — e File 10 ma che.
> Print karo ke second monitor par rakho.

---

## 1. Market kholta pehla — 60 second scan

```
□ System health: feed live? recon clean? circuit breaker ACTIVE?
□ Aaje event che? (RBI policy, Fed, expiry, budget, results day)
□ Gap? SGX/GIFT Nifty vs yesterday close
□ India VIX level
     < 12  → range/mean-reversion favourable
     12-18 → normal
     > 20  → wide stops, HALF SIZE, ke off
□ Aaje kayo regime? (Hurst / EMA slope / ATR percentile)
     → MEAN REVERSION mode  ya  MOMENTUM mode  — EK J
□ Equity aaje ketli? Risk per trade = equity × 1%
□ Aagli 3 trades: loss streak par cooldown active che?
```

> **09:15–09:20 ma kai j nahi.** Price discovery, spread pagal, gap fill chaos.

---

## 2. Regime — pehla aa nakki karo

```
   ┌─────────────────────────────────────────────────────────┐
   │  TRENDING                    RANGING                    │
   │  ────────                    ───────                    │
   │  Higher highs + higher lows  Horizontal band            │
   │  EMA9 > EMA21, slope steep   EMAs flat, intertwined     │
   │  ADX > 25                    ADX < 20                   │
   │  Hurst > 0.55                Hurst < 0.45               │
   │  Price VWAP ni ek baaju      Price VWAP ne cross kare   │
   │  rahe che                    vaar vaar                  │
   │                                                          │
   │  → MOMENTUM engine           → MEAN REVERSION engine    │
   │  → breakout, trail stop      → VWAP bands, z-score      │
   └─────────────────────────────────────────────────────────┘
   
   ⚠️ Confused cho? = e j "chop" che. CHOP MA TRADE NAHI.
      Unclear regime ma banne strategy loss kare che.
```

---

## 3. Mean Reversion — entry checklist

```
□ Regime = RANGING confirmed (ADX < 20, Hurst < 0.5)
□ VWAP calculated ane window full (warm-up done)
□ |Z-score| > 2.0
□ Aa scrip par ADF p < 0.05 (roz sakaale computed)
□ Half-life 5–30 bars ma
□ Expected move (2σ ₹) > 3 × total cost
□ Volume normal (dried up nathi)
□ Koi news/event nathi (structural break risk)
□ Sector ma already 2 position nathi
─────────────────────────────────────
ENTRY   : limit order at band, market nahi
STOP    : entry ∓ 2×ATR  (HARD, ratchet only)
TARGET  : |z| < 0.5  (mean touch ni raah na jovo)
TIME    : 2 × half-life pachhi force exit
SIZE    : (equity × 1%) / (2 × ATR)
```

---

## 4. Momentum / Breakout — entry checklist

```
□ Regime = TRENDING confirmed (ADX > 25, EMA aligned)
□ Price > Donchian(20) upper  [long]
□ Break margin > 0.25 × ATR (marginal break nahi)
□ Volume > 1.5 × 20-bar average
□ Close bar ni upper 40% ma (strong close)
□ Higher timeframe sathe aligned (15m trend, 5m entry)
□ Resistance ni najik nahi (prior swing high, round number)
─────────────────────────────────────
ENTRY   : market ke stop-limit above break
STOP    : entry − 2×ATR, ke Donchian(10) lower
TARGET  : trail only — Chandelier (extreme − 3×ATR)
BREAKEVEN: +1R par stop ne entry par khesedo
SIZE    : (equity × 1%) / (2 × ATR)
```

---

## 5. Trade lene pehla — 8 second gate

```
   1. Regime match?          ── nahi → SKIP
   2. Setup rules ma 100%?   ── partially → SKIP
   3. Stop kya che? (number) ── khabar nathi → SKIP
   4. Size formula thi?      ── "feel" thi → SKIP
   5. R:R >= 1.5?            ── nahi → SKIP
   6. Cost cover thase?      ── nahi → SKIP
   7. Correlated position?   ── ha → half size ke SKIP
   8. Daily loss limit door? ── najik → SKIP
```

> **Aa 8 ma ek pan "nahi" → trade nahi.** "Pan aa vakhte..." — ej line che je account khatam kare che.

---

## 6. Position ma cho tyare

```
   ✅ KARO                        ❌ NA KARO
   ───────────────────────────────────────────────────────
   Stop ne rules mujab trail      Stop widen — KADI NAHI
   Time stop honor karo           Loser ma add — KADI NAHI
   Target hit → exit              "Thodu vadhare" — plan badlvo
   Plan mujab exit                Chart ne 5 min ma refresh karvu
   Reason log karo                Revenge trade after loss
```

**Aa 3 line roz vancho:**
```
1. Mari pase edge signals ma nathi — ENA MA che ke hu rules follow karu chu.
2. Ek trade nu outcome kai j nathi kehtu. 100 trades kahe che.
3. Capital bachavvu kamavva karta vadhare important che.
```

---

## 7. Din ma — red flags

```
🔴 3 consecutive losses      → 30 min break, FORCED
🔴 Daily loss 3%             → flatten all, din band
🔴 "Aaje recover karvu che"  → aa thought = stop trading, aaje
🔴 Rules break karva nu man  → position half karo ke band karo
🔴 Feed lag / recon mismatch → manual check, trading halt
🔴 Size vadharvani ichha     → performance nahi, emotion bole che
🔴 Screen par 6 kalak stare  → tamari system automated hovi joie,
                                tame nahi
```

---

## 8. Reading a chart — layer order

```
   STEP 1  HIGHER TIMEFRAME       Daily/60m — overall trend kayo?
   STEP 2  KEY LEVELS             PDH/PDL, today's high/low,
                                   round numbers, VWAP
   STEP 3  REGIME                 Trending ke ranging? (Section 2)
   STEP 4  VOLATILITY             ATR — stop ketlo pahoro joie
   STEP 5  VOLUME                 Participation che? Move genuine?
   STEP 6  SETUP                  Mara rules ma fit thay che?
   STEP 7  RISK                   Stop kya, size ketlu, R:R?
   
   ⚠️ Loko STEP 6 thi shuru kare che. Etle 1-5 ni information
      vagar trade lae che ane pachhi "market unpredictable" kahe che.
```

---

## 9. Numbers je heart ma hovva joie

```
Break-even round trip (intraday equity)   ≈ 0.12%  (costs + slippage)
Risk per trade                            = 1% of equity
Max positions                             = 5
Max per sector                            = 2
Initial stop                              = 2 × ATR(14)
Trailing stop                             = 3 × ATR from extreme
Breakeven shift                           = +1R
Daily loss limit                          = 3%
Max drawdown halt                         = 15%
Entry window                              = 09:20 – 15:00
Square off                                = 15:15
Half-life sweet spot                      = 5–30 bars
Z entry / exit                            = 2.0 / 0.5
ADX trend threshold                       = 25
Min R:R                                   = 1.5
```

---

## 10. EOD — 5 minute review

```
□ Trades log: har trade nu reason lakhyu?
□ Rules follow thaya? (outcome nahi, PROCESS jovo)
□ Koi trade rules ni bahar? → kem? pattern che?
□ Slippage assumption ni andar?
□ Signals backtest sathe match thaya?
□ Errors/rejects/alerts review
□ Equity, drawdown, streak update
□ Aaje shu shikhya — ek line
```

> **Weekly:** exec_quality query chalavo (File 08), worst symbols/hours kaadho.
> **Monthly:** metrics vs backtest compare. Live Sharpe < backtest × 0.5 → size ghatadvo ane investigate.

---

## Ek j vaakya ma aakhu system

> **Clean data → validated signal → risk-approved size → disciplined execution → honest measurement → feedback.**
> Aa chain ma je sauthi weak link che, ej tamara returns nakki kare che. Strategy nahi.
