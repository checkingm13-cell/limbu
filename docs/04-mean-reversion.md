# 04 — Mean Reversion Framework

> **Chunk**: ALPHA-1. Message: *"Price ne nahi, price na *deviation* ne trade karo — ane pehla prove karo ke deviation kharekhar reverts thay che."*

---

## 1. WHY

Mean reversion nu dhandho: "aa price potana fair value thi door gayo che, pachho avse."
**Danger:** trending market ma aaj thesis = falling knife pakadvi. Etle framework ma **be part** hoy che:
1. Deviation measure karvu (Z-score)
2. **Deviation kharekhar revert thase ke nahi e test karvu** (ADF, half-life)

Part 2 skip karso to strategy 4 mahina kaam karse ane 5ma mahine account safai thai jase.

---

## 2. VWAP — mean ni definition

**VWAP = Volume-Weighted Average Price** = aaje aa scrip ma *average paisa* kaya price par change thayo.

```
           Σ (price_i × volume_i)
VWAP_t =  ────────────────────────      (session start thi cumulative)
              Σ volume_i
```

**Simple MA karta kem better:**
```
   Price
   2455 ┤        ╭──╮        ← 09:45, volume 200 (koi nathi joyu)
   2450 ┤   ╭────╯  ╰───     
   2445 ┤───╯   
        │  ▲
        │  └─ 09:16, volume 50,000 (aakhu market ahiya trade thayu)
        └──────────────────►
   SMA  : banne ne saman weight aape  → misleading "average"
   VWAP : 09:16 ne 250x weight aape   → institutional reality
```

**Kem VWAP institutional benchmark che:** Mutual funds/FII ne ek din ma 5 lakh share kharidva hoy to e VWAP-or-better execution no target rakhe che. Etle price VWAP ni aaspaas **magnetic** behave kare che — ej mean reversion no structural karan che, statistical fluke nahi.

```python
class SessionVWAP:
    """Session boundary par reset THAY J JOIE."""
    def __init__(self):
        self.num = 0.0; self.den = 0.0
        self.dev_win = RollingWindow(20)     # File 03 mathi

    def reset(self): self.num = self.den = 0.0

    def update(self, price, volume):
        tp = price                        # ke typical price (h+l+c)/3
        self.num += tp * volume
        self.den += volume
        v = self.value()
        if v: self.dev_win.push(price - v)
        return v

    def value(self):
        return self.num / self.den if self.den > 0 else None
```

> ⚠️ **Sauthi common bug:** VWAP ne 09:15 par reset na karvu. Aagla din no data carry thay to VWAP frozen jevu thai jay ane Z-score meaningless.

### Standard Deviation Bands

```
   ┌──────────────────────────────────────────────────┐
   │      ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌  VWAP + 2σ   SHORT zone │
   │   ─────────────────────   VWAP + 1σ              │
   │   ═══════════════════════ VWAP        exit/mean  │
   │   ─────────────────────   VWAP − 1σ              │
   │      ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌  VWAP − 2σ   LONG zone  │
   └──────────────────────────────────────────────────┘
   σ = std of (price − VWAP) over rolling N bars
```

Bollinger Bands ma σ price par calculate thay che; ahiya **deviation par**. Aa better che kem ke deviation series stationary hovani vadhare shakyata che (File 02 yaad karo).

---

## 3. Z-Score — signal nu actual number

```
        x − μ          (current deviation) − (mean deviation)
  z =  ───────   =    ──────────────────────────────────────
          σ                 std of deviation
```

**Interpretation:**

| Z | Meaning | Action (untested) |
|---|---|---|
| > +2.5 | Extreme uchu | Short candidate |
| +1 to +2 | Mildly uchu | Wait |
| −1 to +1 | Noise zone | **Kai nahi** |
| −2 to −1 | Mildly nichu | Wait |
| < −2.5 | Extreme nichu | Long candidate |

**Entry/exit asymmetry — aa design decision matter kare che:**
```
   ENTRY at |z| > 2.0     EXIT at |z| < 0.5   (mean touch ni raah na jovo)
   
   z
  +3 ┤      ●ENTRY SHORT
  +2 ┼╌╌╌╌╌╌│╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  +1 ┤      │  ╲
   0 ┼──────│───╲──────────────── ← mean sudhi raah jota vaar full
  -1 ┤      │    ╲●EXIT (z=0.5)      reversal kharab thai jay
  -2 ┼╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
```
Reason: mean touch thava ni probability < partial reversion ni probability. Profit factor sudhare che.

```python
def zscore_signal(price, vwap_obj, entry=2.0, exit_=0.5):
    dev = price - vwap_obj.value()
    w = vwap_obj.dev_win
    if not w.is_full:                 # ⚠️ warm-up vagar signal NAHI
        return 0
    z = w.zscore(dev)
    if z >  entry: return -1          # short
    if z < -entry: return +1          # long
    if abs(z) < exit_: return 0       # flat
    return None                       # hold existing
```

### ⚠️ 3 trap

**(a) Warm-up.** 20-bar window ma 3 bar hoy tyare std garbage che → z = 8 → instant trade → disaster. `is_full` check mandatory.

**(b) Volatility regime shift.** Budget day ma σ 4x vadhi jay. Fixed threshold 2.0 tyare "normal" move par fire kare che. **Fix:** rolling σ vaparo (already che) *ane* additional regime filter (ATR percentile, File 05).

**(c) Z-score stationarity assume kare che.** Aa sauthi motu. Aaj file no next section ej solve kare che.

---

## 4. Stationarity Testing — "revert thase kharu?"

### ADF Test (Augmented Dickey-Fuller)

**Question:** aa series random walk che (revert nahi thay) ke mean-reverting che?

```
H₀ (null)      : unit root che → RANDOM WALK → mean reversion NAHI
H₁ (alternate) : stationary → MEAN REVERTING

p-value < 0.05 → H₀ reject → mean-reverting mani shakay
p-value > 0.05 → trade NAHI karo. Strategy aa scrip mate nathi.
```

```python
from statsmodels.tsa.stattools import adfuller

def is_mean_reverting(series, alpha=0.05):
    series = series.dropna()
    if len(series) < 100:
        return False, None                 # ochha data par test meaningless
    stat, pvalue, *_ = adfuller(series, autolag="AIC")
    return pvalue < alpha, pvalue

# ✔ deviation par test karo, price par nahi
dev = df["close"] - df["vwap"]
ok, p = is_mean_reverting(dev)
```

> **Realistic expectation:** Single stock nu price almost hamesha non-stationary hase (p > 0.05). Deviation-from-VWAP intraday ma ghana vaar stationary hoy che. **Pair spread** (File ni ant ma) sauthi vadhare reliably stationary hoy che.

### Half-Life — ketla var ma pachhu avse

Ornstein-Uhlenbeck process fit karo:
```
   Δy_t = λ · y_{t-1} + ε        (OLS regression)

                 ln(2)
   half-life = − ──────          (λ negative hovu joie)
                   λ
```

```python
import numpy as np, statsmodels.api as sm

def half_life(series):
    y = series.dropna()
    lag   = y.shift(1).dropna()
    delta = (y - y.shift(1)).dropna()
    lag, delta = lag.align(delta, join="inner")
    beta = sm.OLS(delta, sm.add_constant(lag)).fit().params.iloc[1]
    if beta >= 0:
        return np.inf                 # revert NATHI thatu → skip
    return -np.log(2) / beta
```

**Aa number sauthi practical output che:**

```
   half-life  →  shu kare
   ─────────────────────────────────────────────────────
   < 3 bars    → noise/microstructure. Costs khai jase.
   5–30 bars   → ✅ SWEET SPOT. Ahiya trade karo.
   > 100 bars  → bahu dhimu. Capital block thase, overnight risk.
   inf / neg   → trending. Mean reversion band karo, momentum jovo.
```

**Half-life ne directly parameters ma convert karo:**
```
lookback window   ≈ 2–3 × half-life
max holding time  ≈ 2 × half-life   → pachhi time-based exit (forced)
target bars       ≈ 1 × half-life
```
> Aa ek technique che je "random parameter tuning" ne "data-derived parameter" ma badle che. **Overfitting thi bachvano sauthi saras rasto** — parameter tame nahi, data nakki kare che.

### Hurst Exponent (quick regime check)
```
H < 0.5  → mean reverting
H ≈ 0.5  → random walk
H > 0.5  → trending
```
Har sakaale 30 din na data par compute karo → e din strategy mean-reversion mode ma chalavvi ke momentum mode ma, e nakki karo. **Regime switch = ek j system, be alag alpha.**

---

## 5. Pairs / Statistical Arbitrage (aa j level uper le jay che)

Single stock reversion weak che. **Spread** reversion structural che.

```
   HDFCBANK ────╮
                 ├──► spread = A − β·B   ◄── aa series par ADF + Z-score
   ICICIBANK ───╯
   
   β = hedge ratio (OLS ke Kalman filter thi)
```

```
Workflow:
  1. Same sector ma candidate pairs
  2. Engle-Granger / Johansen cointegration test (ADF > weak nathi)
  3. β estimate (rolling OLS ke Kalman — Kalman better, β badlay che)
  4. spread na Z-score par trade: z>2 → short A/long B
  5. Half-life thi holding period nakki
  6. Cointegration break thay (rolling p-value > 0.05) → EXIT + pair drop
```

> **Aa exact framework che je Renaissance/D.E. Shaw e 1980-90s ma vaparyo hato.** Aaje crowded che, pan structure samajvu essential — ane Indian mid-cap space ma pan ochho exploited che.

---

## 6. FAILURE MODES — mean reversion kem marse che

| Failure | Shu thay | Guard |
|---|---|---|
| **Regime change** | Trending market ma har entry loss | Hurst/ADF filter, EMA-slope veto |
| **No stop-loss** | Mean reversion "hamesha pachhu ave" delusion → 1 trade 40 trades no profit khai jay | **Hard ATR stop mandatory** (File 06) |
| Structural break | News/fraud/downgrade — mean j badlai gayo | Event calendar filter, rolling cointegration |
| Warm-up ignore | Day start ma fake z=8 | `is_full` gate |
| Costs > edge | Nani reversion, 0.12% hurdle | Expected move (2σ ₹) > 3× cost check |
| VWAP reset miss | Z-score garbage | Session boundary unit test |
| Averaging down | "z vadhare thayo, vadhare add karo" | Position size **fixed** at entry. Add karvu ban. |

> **Mean reversion ni fundamental asymmetry:** win rate uchu (60–70%), pan loss moti. Ek mota loss 10 wins khai jay. **Etle risk engine aa strategy mate optional nathi — e strategy no part che.**

---

## 7. Full loop — ek jagya e

```python
def on_bar(bar, st: SymbolState, cfg):
    vwap = st.vwap_obj.update(bar.close, bar.volume)
    if vwap is None or not st.vwap_obj.dev_win.is_full:
        return None                                   # warm-up

    # Regime gate — aa vagar strategy adhuri che
    if st.hurst > 0.55 or st.adf_p > 0.05:
        return None                                   # trending/non-stationary

    z = st.vwap_obj.dev_win.zscore(bar.close - vwap)

    if st.position == 0:
        if z < -cfg.entry: return ("BUY",  z)
        if z > +cfg.entry: return ("SELL", z)
    else:
        if abs(z) < cfg.exit:               return ("EXIT", "mean")
        if st.bars_held > 2 * st.half_life: return ("EXIT", "time")   # ⏱ important
        if st.adverse_atr > cfg.stop_atr:   return ("EXIT", "stop")
    return None
```

---

## Margin Questions
1. VWAP institutional benchmark hovathi mean reversion ne kem structural support male che?
2. ADF ma p > 0.05 male to shu karvu?
3. Half-life thi 3 parameters kaya derive thay che?
4. Entry |z|=2, exit |z|=0.5 — asymmetry kem?
5. Mean reversion ma stop-loss kem *vadhare* jaruri che momentum karta?
6. Z-score warm-up bug kem dangerous che?


## IMPORTANT
આપણે discuss કર્યું                    Fileમાં શું છે

RAW MARKET DATA
      ↓
OHLC / Volume / Tick             →    bar.close + bar.volume
      ↓
Mean calculate                    →    VWAP
      ↓
Deviation                         →    price - VWAP
      ↓
Standard deviation                →    rolling σ
      ↓
Z-score                           →    Z-score
      ↓
"revert થશે કે નહીં?"            →    ADF
      ↓
કેટલા bars લાગશે?                →    Half-life
      ↓
Trend vs mean-reversion          →    Hurst
      ↓
Signal                            →    BUY / SELL / EXIT
      ↓
Risk check                       →    ATR stop / time exit
      ↓
Order                             →    execution layer