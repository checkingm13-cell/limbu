# 07 — Backtesting Hygiene & Evaluation

> **Chunk**: VALIDATION. Message: *"Backtest no kaam profit batavvano nathi — strategy ne **mari nakhvano** che. Je bachi jay e j live jay."*
> Mindset flip: sundar equity curve = **suspicion**, celebration nahi.

---

## 1. WHY

Backtest ma 3 jutha bolay che, ane traney tamne sara dekhaay che:
1. **Lookahead** — bhavishya ni khabar past ma leak thai
2. **Overfitting** — noise ne rule mani lidhu
3. **Optimistic execution** — fills je reality ma na thaay

Traney remove karo, to 90% "profitable" strategies flat ke negative thai jay che. **Aa normal che.** Je bache e real che.

---

## 2. Lookahead Bias — 7 jagya e chhupay che

```
   ❌ WRONG                              ✅ RIGHT
   ─────────────────────────────────────────────────────────
   signal = f(close[t])                  signal = f(close[t])
   fill   at close[t]                    fill   at open[t+1] + slippage
                                          
   "Bar band thaya pachhi eij bar na close par fill" = TIME TRAVEL
```

| # | Leak | Kem thay | Fix |
|---|---|---|---|
| 1 | Same-bar fill | Close par signal, close par fill | Next bar open par fill |
| 2 | `df.mean()` / `.std()` full series par | Aakha dataset ni stats | Fakt `.rolling()`/expanding |
| 3 | Scaler `fit()` on full data | Test set ni info train ma | `fit` on train only |
| 4 | `dropna()`/`fillna(method='bfill')` | Bfill = future value pachal | Fakt ffill, ane careful (File 02) |
| 5 | Adjusted prices | Split factor future ma announce thayo | PIT adjustment factors |
| 6 | Index membership aaj ni | Survivorship | PIT membership table |
| 7 | Fundamentals report-date vs period-date | Q3 data 31-Dec par stamped | PIT fundamentals |

**Detection technique — shifting test:**
```python
# Signals ne EK bar aagal shift karo. Performance thodo ghato joie.
# Jo performance NATHI ghatto → signal future ma dekhata hato.
# Jo performance TABAH thai jay → strategy 1-bar edge par depend che
#    (= microstructure/latency ma khovai jase, live ma survive nahi kare)
sig_shifted = signal.shift(1)
```
Aa 2-line test ek baar chalavo, ghana "amazing" strategies exposed thai jase.

### Event-driven vs Vectorized

```
VECTORIZED (pandas)                EVENT-DRIVEN
  fast (seconds)                     slow (minutes)
  research/screening mate            production validation mate
  ⚠️ lookahead invite kare che       ⚠️ lookahead structurally impossible
  
  for whole df: signal = ...         for bar in bars:         ← ek j bar visible
                                         strategy.on_bar(bar)
                                         risk.check()
                                         broker.process_orders()
```
> **Industry standard:** research ma vectorized thi screen karo, pan **je strategy live jase e event-driven engine ma re-validate thay j.** Ane e engine no interface live engine sathe **identical** hovo joie — same `on_bar()`, same risk module, same order router (DRY_RUN mode ma). Tyare "backtest ma chaltu hatu pan live ma nahi" no aakho category eliminate thai jay.

---

## 3. Overfitting / Data Snooping

```
  Sharpe
   3.0 ┤                    ╭─╮  ← ahiya tame optimize karyu
       │                   ╱   ╲    (in-sample peak)
   2.0 ┤              ╭───╯     ╲
       │         ╭────╯          ╲
   1.0 ┤    ╭────╯                ╲___  ← out-of-sample reality
       │────╯                          
       └──────────────────────────────────►
         parameter (e.g. lookback window)
         
   Peak par sit karvu = noise par sit karvu.
   ✅ BROAD PLATEAU shodho, sharp peak nahi.
   Parameter ±25% badlo ane Sharpe 40% padi jay → e fake che.
```

### Multiple testing problem (statistics je ignore thay che)
```
1 strategy test karo, 5% significance → 5% chance ke luck che
100 strategies test karo → expected 5 "significant" fakt luck thi
1,000 combos try karo → 50 beautiful backtests, badha noise
```
**Fix:**
- **Deflated Sharpe Ratio** — number of trials ne adjust kare che (Bailey & López de Prado)
- Trials count **lakho**. "Me 200 combos try karya" honestly record karo.
- Simple hypothesis pehla, parameters pachhi. **Economic reason vagar nu pattern = noise.**

### Validation protocols

```
A) SIMPLE SPLIT
   ├──────── TRAIN 70% ────────┤├─ TEST 30% ─┤
   ⚠️ Test ek j vaar vaparo. Test jovu → tune karvu → e train thai gayu.

B) WALK-FORWARD (✅ time series mate saheb)
   ├─train─┤├t┤
       ├─train─┤├t┤
           ├─train─┤├t┤
               ├─train─┤├t┤
   Har window ma re-optimize, next window ma test. Stitched OOS curve = honest.

C) PURGED K-FOLD with EMBARGO (institutional)
   Train | PURGE | Test | EMBARGO | Train
   Purge  = overlapping-label leakage kaadho
   Embargo= serial correlation leakage kaadho
```

```python
def walk_forward(data, train_bars, test_bars, optimize_fn, run_fn):
    results, i = [], 0
    while i + train_bars + test_bars <= len(data):
        train = data.iloc[i : i+train_bars]
        test  = data.iloc[i+train_bars : i+train_bars+test_bars]
        best  = optimize_fn(train)                  # in-sample tuning
        results.append(run_fn(test, best))          # out-of-sample only
        i += test_bars                              # roll forward
    return results
```

### Overfitting na red flags

```
🚩 Sharpe > 3 (retail data ane retail latency sathe: ~impossible)
🚩 Win rate > 80% sathe positive expectancy
🚩 Equity curve ekdam straight line
🚩 Parameter ±20% badlo → performance collapse
🚩 Sub-period ma (2020 COVID, 2022 bear) breakdown
🚩 5+ parameters
🚩 Trade count < 100 (statistically meaningless)
🚩 Top 5 trades kadhi nakho → strategy dead
```

> **Aa last vali test roz karo:** `pnl.nlargest(5).sum() / pnl.sum()`. Jo > 50% hoy, to tame strategy nahi, **5 lucky events** shodhya che.

---

## 4. Evaluation Metrics

### Sharpe Ratio
```
              E[R] − Rf
   Sharpe = ─────────────  × √(periods per year)
                σ(R)
```
```python
import numpy as np
def sharpe(returns, rf_annual=0.065, periods=252):
    excess = returns - rf_annual/periods
    if excess.std() == 0: return 0.0
    return np.sqrt(periods) * excess.mean() / excess.std()
```
| Sharpe | Verdict |
|---|---|
| < 0.5 | Kaam nu nahi |
| 0.5–1.0 | Marginal (costs khai jase) |
| 1.0–2.0 | ✅ Good, realistic retail target |
| 2.0–3.0 | Excellent — verify twice |
| > 3.0 | 🚩 Bug ke lookahead. (HFT ma legit, tya trade count lakhs ma hoy) |

⚠️ **India specific:** risk-free 6–7% che (US ma 4–5%). Aa subtract karo, nahi to Sharpe artificially uncho dekhase.
⚠️ **Sharpe volatility ne punish kare che — upar ni volatility ne pan.** Ek strategy je kadi-kadi +15% kare, e punish thay che. Etle:

### Sortino — fakt downside punish
```
   Sortino = (E[R] − Rf) / σ_downside      (fakt negative returns no std)
```
Momentum strategies (right-skewed, moti wins) mate **Sortino vadhare fair** che.

### Max Drawdown
```python
def max_drawdown(equity):
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return dd.min(), dd.idxmin()     # depth ane kyare
```
Sathe **drawdown duration** pan kadho — 6 mahina underwater rehvu psychologically 20% dip karta harder che. Aaj karan che ke loko system band kari de che.

**Calmar Ratio = CAGR / |MaxDD|.** > 1 saru, > 2 excellent. Aa "capital efficiency" no sacho measure che.

### Profit Factor vs Win Rate

```
                 Σ wins
   Profit Factor = ────────       > 1.5 good,  > 2.0 excellent
                 Σ |losses|

   Expectancy = (W × avg_win) − (L × avg_loss)      ← per trade ₹
```
```
   Strategy A: 80% win rate, PF 0.9  →  LOSS MAKING ❌
               (nano nano wins, ek moto loss)
   Strategy B: 35% win rate, PF 2.1  →  PROFITABLE ✅
               (Turtle/momentum profile)
```
> **Win rate vanity metric che.** PF ane expectancy ej matter kare che. Win rate fakt **psychology** mate matter kare che — 35% win rate system par tik rehvu ghanu mushkel hoy che, ane ej karan che ke loko sara system chhodi de che.

### Minimum credible report
```
Period, bars, symbols        |  Trade count (>100)
CAGR                         |  Sharpe / Sortino / Calmar
Max DD (%) + duration (days) |  Profit Factor, Expectancy ₹
Win rate, avg win/loss (R)   |  Turnover ane TOTAL COSTS ₹
Exposure % of time           |  Best/worst month
Top-5-trades removed result  |  Parameter sensitivity heatmap
Benchmark (NIFTY) comparison |  Number of trials tested
```

---

## 5. Realistic backtest engine — must-haves

```python
class BacktestBroker:
    """Live router sathe IDENTICAL interface. Aaj key design decision che."""
    def __init__(self, cost_model, slippage_bps=5, fill_policy="next_open"):
        ...
    def submit(self, order, bar_index):
        # 1. fill NEXT bar par, current bar par nahi
        # 2. slippage adverse direction ma umero
        # 3. liquidity cap: qty <= participation_rate × bar_volume
        # 4. gap handling: SL-M gap par gap price e fill thay, SL price e nahi
        # 5. costs subtract karo (File 01)
        # 6. rejects simulate karo (margin, circuit, freeze qty)
```

**Slippage model — na bhulo:**
```
conservative: 5–10 bps liquid largecap, 20–50 bps midcap
better: spread_estimate/2 + impact_coefficient × (qty / avg_volume)^0.5
```
> Backtest ma cost/slippage ne "optional flag" na banavo. **Default ON, aggressive values sathe.** Pessimistic backtest ma survive kare e j strategy live ma survive kare.

---

## 6. FAILURE MODES

| Failure | Lakshan | Detection |
|---|---|---|
| Same-bar fill | Backtest amazing, live nil | Shift test |
| Full-series scaler | Perfect ML predictions | Pipeline audit, fit-on-train only |
| Test set repeatedly vaparyu | OOS pan overfit | Final holdout ek j vaar, lock karo |
| Costs off | 20 trades/day "profitable" | Costs mandatory in engine |
| Trade count 30 | Sharpe meaningless | Min 100 trades, ideally 300+ |
| Regime luck | 2021 bull ma badhu kaam kare | Sub-period breakdown (bull/bear/chop) |
| Backtest ≠ live code | Untraceable divergence | Same modules, DRY_RUN switch |
| Survivorship | Sharpe +0.5 free | PIT universe |

---

## 7. Go/No-Go checklist — live jatra pehla

```
□ Event-driven engine ma test thayu (vectorized-only nahi)
□ Next-bar fill + slippage + full Indian cost model
□ Walk-forward OOS Sharpe > 1.0
□ Trade count > 100, 2+ varsh, 2+ market regimes
□ Parameter ±25% ma Sharpe stable (plateau)
□ Top-5 trades kaadhya pachhi pan profitable
□ Max DD tamara risk limit ni andar
□ Shift test pass
□ Number of trials documented
□ Live code path == backtest code path
□ 1 mahino paper trading, slippage tracked (File 08)
```
**Ek pan box khali → live paisa nahi.**

---

## Margin Questions
1. Shift test shu batave che ane be alag results no arth?
2. Purged k-fold ma purge ane embargo kem joie?
3. Sharpe > 3 par shu suspicion?
4. Sortino kyare Sharpe karta better che?
5. 80% win rate sathe loss-making kem shakya che?
6. Multiple testing problem ne kem handle karvo?
7. Backtest broker ane live broker ek j interface kem hovu joie?
