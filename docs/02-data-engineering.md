# 02 — Financial Data Engineering

> **Chunk**: DATA. Message: *"Garbage in → confident garbage out."* Quant firms ma 70% headcount aa file par kaam kare che, strategy par nahi.

---

## 1. WHY

Strategy code 200 line nu hase. Data pipeline 2,000 line nu hase. Kem?
Karan ke market data **dirty by nature** che:

- Tick ma same timestamp par 4 trades
- Price 2450 → 245 (split, data ma adjust nathi thayu) → strategy "-90% crash" samje che
- Holiday par bar exist kare che (broker no bug)
- Bank Nifty expiry day par volume 20x → volatility feature explode
- Delisted company data ma thi gayab → backtest ma fakt winners rahi gaya

---

## 2. Time-Series Resampling — Tick → Bar

### Tick data kevu dekhay

```
timestamp                 ltp      qty   bid      ask
09:15:00.142   2450.00    50   2449.95  2450.00
09:15:00.147   2450.05   200   2450.00  2450.05
09:15:00.311   2450.05    10   2450.00  2450.05
09:15:00.998   2449.90   500   2449.85  2449.90
...  (ek din ma liquid scrip ma 2–8 lakh ticks)
```

### Bar banavvani rule

```
        TICKS within 09:15:00 – 09:15:59.999
        ●   ●●    ●      ●●●   ●    ●●
        │   ││    │      │││   │    ││
        ▼                                 ▼
   ┌────────────────────────────────────────┐
   │ OPEN   = first tick price              │
   │ HIGH   = max tick price                │
   │ LOW    = min tick price                │
   │ CLOSE  = last tick price               │
   │ VOLUME = sum(qty)                      │
   │ VWAP   = Σ(price×qty) / Σ(qty)         │
   │ n_ticks= count  ← liquidity proxy!     │
   └────────────────────────────────────────┘
        bar timestamp = 09:15:00 (LEFT label)
```

```python
import pandas as pd

def ticks_to_bars(ticks: pd.DataFrame, freq="1min") -> pd.DataFrame:
    """ticks: index=DatetimeIndex, cols=[price, qty]"""
    t = ticks.copy()
    t["pv"] = t["price"] * t["qty"]
    g = t.resample(freq, label="left", closed="left")

    bars = pd.DataFrame({
        "open":   g["price"].first(),
        "high":   g["price"].max(),
        "low":    g["price"].min(),
        "close":  g["price"].last(),
        "volume": g["qty"].sum(),
        "vwap":   g["pv"].sum() / g["qty"].sum(),
        "ticks":  g["price"].count(),
    })
    return bars.dropna(subset=["open"])   # ⚠️ ffill NAHI — File 6 jovo
```

### ⚠️ 3 trap je 90% loko fasay che

**(a) `label` ane `closed`**
`label="left", closed="left"` → 09:15 bar ma 09:15:00.000 thi 09:15:59.999 na ticks.
Jo `label="right"` karo, to 09:16 name na bar ma 09:15 no data avse → **tame bhavishya nu label lagavi didhu**. Lookahead bias ni sauthi common entry point.

**(b) Missing bars ne ffill karvu**
Illiquid scrip ma 09:32 ma koi trade nathi thayo. `ffill()` karso to fake bar bani jase — volume 0, OHLC badha same. Strategy ne lage ke "price stable che", kharekhar "koi trade j nathi". **Missing rakho, ke `volume=0, is_synthetic=True` flag sathe rakho.**

**(c) Timezone**
Badhu `Asia/Kolkata` ma. Broker UTC ma aape che, exchange IST ma. Ek j pipeline ma be tz mix thay to 5.5 hour no silent shift. **Rule: ingestion ni pehli line par tz-aware convert, ane pachhi kyay naked datetime nahi.**

### Bar types — time bars fakt ek option che

| Bar type | Kyare banave | Kem vaparvu |
|---|---|---|
| **Time bars** | Har 1/5/15 min | Simple, standard, pan volume uneven |
| **Tick bars** | Har N trades | Information-time, more normal returns |
| **Volume bars** | Har N shares | Activity ne normalize kare |
| **Dollar bars** | Har ₹N turnover | Sauthi stable statistical properties |

> **Industry note:** Lopez de Prado (*Advances in Financial ML*) show kare che ke dollar/volume bars na returns time bars karta vadhare Gaussian ane less heteroskedastic hoy che. Prop desks ghana volume bars vapare che. Retail almost badha time bars vapare che — kem ke chart platform ej batave che. **Aa ek real, cheap edge che.**

---

## 3. Non-Stationarity — Prices vs Returns

### Problem

```
   PRICE SERIES (non-stationary)          LOG RETURNS (≈ stationary)
   3000 ┤              ╭─╮                 0.03┤ │  ││   │  │
        │          ╭───╯ ╰╮                    │ ││ │ ││ ││ │ │
   2700 ┤      ╭───╯      ╰──╮             0.00┼─┼┼─┼─┼┼─┼┼─┼─┼─
        │  ╭───╯              ╰               │  ││  │  │ ││
   2400 ┤──╯                                -0.03┤     │     │
        └──────────────────────────►            └───────────────►
   mean badlay che, variance badlay che      mean≈0, variance≈const
```

**Non-stationary** = mean/variance time sathe badlay che.
Badha statistical tools (regression, Z-score, correlation, ML models) assume kare che ke distribution stable che. Price par sidha apply karso to **spurious results** male — 2 random walks vachche correlation 0.9 aavi jase.

### Log returns — ane kem log

```
Simple return:  r = (P_t / P_{t-1}) − 1
Log return:     l = ln(P_t / P_{t-1})
```

| Property | Kem matter kare |
|---|---|
| **Additive over time** | `ln(P2/P0) = ln(P2/P1) + ln(P1/P0)` → 1-min returns sum karo to 5-min return male. Simple returns ma multiply karvu pade. |
| **Symmetric** | +10% pachhi −10% simple ma −1% net; log ma +0.0953 −0.0953 = 0 |
| **≈ Normal-ish** | Stats/ML mate better behaved (fat tails toy pan rahe che) |
| **Small values ma ≈ same** | 1% thi nana move ma log ≈ simple |

```python
import numpy as np
df["log_ret"] = np.log(df["close"] / df["close"].shift(1))

# annualized volatility (intraday 1-min bars, NSE: 375 bars/day, 250 days)
bars_per_year = 375 * 250
ann_vol = df["log_ret"].std() * np.sqrt(bars_per_year)
```

> **Rule:** Modeling/features/stats ma **returns** vaparo. Position sizing, stops ane P&L ma **prices** vaparo. Banne ne mix na karo.

### Fractional differencing (advanced, pan industry ma vaparay che)
Full differencing (returns) stationary banave che pan **memory kharab kari nakhe** — price level ni information gum thai jay. Fractional differencing (d = 0.3–0.6) minimum differencing kare che je stationarity aape ane maximum memory bachave. Institutional ML pipelines ma standard step che.

---

## 4. Corporate Actions

### Kem — untreated action strategy ne mari nakhe

```
   MRF 1:10 SPLIT (illustrative)
   Raw feed:  ... 1,50,000 → 1,49,500 → [SPLIT] → 14,950 ...
                                          │
                                          ▼
   Strategy jue che:  log_ret = ln(14950/149500) = −2.30  (−90%!)
   → Momentum strategy: "massive crash, short karo"
   → Mean reversion:   "Z-score −45, all-in buy karo"
   BANNE TABAH.
```

### Adjustment math

**Split (ratio R, e.g. 1:10 → R=10):**
```
adjusted_price  = raw_price / R      (split pehla na badha bars)
adjusted_volume = raw_volume * R
```

**Dividend (amount D, ex-date par):**
```
factor = (close_before − D) / close_before
adjusted_price = raw_price × factor   (ex-date pehla na badha bars)
```

**Back-adjust karo — aage thi pachal taraf.** Latest price hamesha actual traded price rehvu joie, nahi to live orders wrong price par jase.

### Adjusted vs Unadjusted — kayu kyare

| Use case | Kayu data |
|---|---|
| Signal/features/backtest returns | **Adjusted** |
| Live order placement price | **Unadjusted (raw/LTP)** |
| P&L reporting | **Unadjusted** + separate dividend ledger |
| Volume/liquidity filters | **Adjusted volume** |

> **Production pattern:** be alag table rakho — `prices_raw` ane `adj_factors`. Adjusted price **query time par** compute karo. Historical table ne overwrite karso to ek naya corporate action aavya pachhi old backtest reproduce nahi thay. Reproducibility = audit requirement.

### Survivorship Bias

```
   2015 ma NIFTY 50 ni list        2026 ma tame backtest karo
   ┌──────────────────────┐        ┌──────────────────────┐
   │ 50 companies         │        │ TODAY ni 50 list      │
   │  — 12 delisted/      │  ────► │  lai ne 2015 thi run  │
   │    dropped thai      │        │                       │
   │  — 12 nava aavya     │        │ = fakt SURVIVORS      │
   └──────────────────────┘        │ = fake +3-5% CAGR     │
                                   └──────────────────────┘
```

**Fix:** *Point-in-time* index membership store karo:
```sql
CREATE TABLE index_membership (
  index_name TEXT, symbol TEXT,
  effective_from DATE, effective_to DATE  -- NULL = still member
);
-- backtest ma har din: WHERE effective_from <= d AND (effective_to IS NULL OR effective_to > d)
```

**Sathe sathe aa biases pan:**
- **Look-ahead in fundamentals** — Q3 results 25 Jan e publish thaya, pan database ma 31 Dec par stamp thayela. → *point-in-time* fundamentals joie.
- **Delisting return** — delist thayeli company nu return −100% gani ne include karvu pade, drop nahi karvu.
- **Restatement bias** — revised numbers original vale replace kari de che.

---

## 5. Data Quality Gate — ingestion par ej validation

```python
from dataclasses import dataclass

@dataclass
class TickValidator:
    max_jump_pct: float = 0.10       # single tick ma 10%+ = suspect
    circuit_pct:  float = 0.20

    def check(self, sym, price, qty, ts, last_price, prev_close):
        if price <= 0 or qty < 0:                       return "BAD_VALUE"
        if last_price and abs(price/last_price - 1) > self.max_jump_pct:
                                                        return "PRICE_SPIKE"
        if prev_close and abs(price/prev_close - 1) > self.circuit_pct:
                                                        return "OUT_OF_CIRCUIT"
        if not (ts.hour*60+ts.minute >= 555 and ts.hour*60+ts.minute <= 930):
                                                        return "OUT_OF_SESSION"  # 09:15–15:30
        return "OK"
```

**Rejected ticks ne delete na karo — quarantine table ma nakho.** Pattern dekhase: kayo symbol, kayo time, kayo broker feed problem kare che.

### Daily reconciliation job (production ma mandatory)
```
Raat 8 vage:
  1. Broker/exchange bhavcopy download
  2. Tamara bars vs official OHLCV compare
  3. Mismatch > 0.01% → alert + tamara bar ne official thi replace
  4. Corporate action feed check → adj_factors update
  5. Missing-bar report
```

---

## 6. FAILURE MODES

| Failure | Silent lakshan | Detection |
|---|---|---|
| Split unadjusted | Ek din ma −90% return | Daily `abs(log_ret) > 0.25` alert |
| Timezone mismatch | Signals 5.5 hr shifted | Bar count/day == 375 check |
| ffill par features | Backtest ma too-smooth equity curve | `volume==0` bar count monitor |
| Survivorship | Backtest Sharpe unrealistically ~2.5 | PIT membership use karo, phari testo |
| Right-labelled bars | Backtest amazing, live zero | Bar ni timestamp ane tick ni timestamp manually verify |
| Stale feed (ws alive, data frozen) | Position stuck | Heartbeat: 30s ma tick na ave → HALT (File 03) |

---

## Margin Questions
1. `label="right"` kem lookahead bias create kare che?
2. Log returns additive kem che ane e kyare kaam ave?
3. Adjusted price live order ma kem na vaparay?
4. Survivorship bias backtest Sharpe ne kai direction ma khese?
5. Missing bar ffill karvu kem khatarnak?
6. Dollar bars time bars karta kem better statistical properties aape che?
