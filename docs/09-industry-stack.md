# 09 — Industry Reality: Big Firms Kya Vapare Che

> Aa file no purpose: **calibration.** Tame kaya level par competing cho, kona sathe, ane kya tamari pase realistic edge che e samajvu.
> ⚠️ Firms trade secrets publish nathi karta. Ahiya je che e public talks, papers, job postings, open-source releases ane industry-standard practice thi che. Details badlaay che — structure stable rahe che.

---

## 1. Frequency Spectrum — tame kya cho

```
 HOLDING PERIOD          WHO                      EDGE KYA THI AVE
 ───────────────────────────────────────────────────────────────────────
 nanoseconds   ┤  FPGA HFT market makers     │ hardware, co-location
 microseconds  ┤  Jump, Tower, Optiver,      │ speed, queue position
               │  Jane Street, IMC, Citadel  │
 milliseconds  ┤  Stat arb / latency arb     │ speed + short-term models
 seconds-min   ┤  Mid-freq systematic        │ microstructure + ML
 minutes-hours ┤  Intraday systematic        │ ⬅ ETLU TAMARU ZONE
 days-weeks    ┤  Quant equity, CTA/managed  │ factors, trend, risk mgmt
               │  futures (AQR, Man AHL,     │
               │  Winton, Two Sigma)         │
 months-years  ┤  Quant value, risk premia   │ economics + patience
 ───────────────────────────────────────────────────────────────────────
```

> **Sauthi important realization:** HFT space ma tame compete nathi kari shakta — tya edge ₹ crores na hardware ane exchange co-location ma che. **Pan tya thi ek level niche (minutes-hours), speed matter nathi karti — model quality, risk discipline ane cost control matter kare che.** Tya retail/small-fund honest rite compete kari shake che.

---

## 2. Firm Archetypes

| Firm | Kevi rite paisa kamay | Signature |
|---|---|---|
| **Renaissance (Medallion)** | Short-horizon statistical patterns, massive data, extreme leverage on tiny edges | Physicists/mathematicians, **zero finance-background hiring**, hermetic secrecy |
| **Two Sigma / D.E. Shaw** | ML + alternative data + distributed systems at scale | Tech-company culture, huge data eng teams |
| **Citadel Securities** | Market making — spread capture, retail order flow | Scale + technology + risk systems |
| **Jane Street** | ETF arbitrage, options market making | OCaml everywhere, functional programming, famous interviews |
| **Jump / Tower / Optiver / IMC** | Latency-sensitive MM ane arb | FPGA, custom kernels, microwave links |
| **AQR / Man AHL / Winton** | Factor investing, trend following, risk parity | Academic, published research, longer horizon |
| **Indian prop desks** (Alpha Grep, Graviton, Quadeye, Dolat, Tower Research India, iRage, QuantBox) | NSE/BSE ma MM, F&O arb, latency arb | NSE co-location, C++ core, strong campus hiring |

### Common thread — badha ma je same che
```
1. Alpha short-lived che. Research PIPELINE bharyu joie, ek strategy nahi.
2. Risk management strategy karta MOTU department che.
3. Data infrastructure ma 70% investment.
4. Execution quality = alpha ni barabar. Bad execution good alpha ne khai jay.
5. Backtest par distrust — deployed strategy pehla months forward-test thay.
```

---

## 3. Actual Technology Stack

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER            INSTITUTIONAL             TAMARU (realistic)      │
├─────────────────────────────────────────────────────────────────────┤
│  Feed handler     C++/Rust, kernel bypass   Python asyncio +        │
│                   (Solarflare/Onload),      broker WebSocket SDK    │
│                   FPGA (HFT), FIX/ITCH      (File 03)               │
├─────────────────────────────────────────────────────────────────────┤
│  Message bus      Aeron, Chronicle Queue,   Redis Streams           │
│                   ZeroMQ, Kafka (slower     asyncio.Queue           │
│                   path), shared memory                              │
├─────────────────────────────────────────────────────────────────────┤
│  Tick store       kdb+/q (industry std),    Parquet + DuckDB        │
│                   ClickHouse, Arctic/       TimescaleDB             │
│                   MongoDB (Man AHL OSS),    ClickHouse (scale ma)   │
│                   QuestDB, Arrow/Parquet                            │
├─────────────────────────────────────────────────────────────────────┤
│  Research         Python: numpy, pandas,    ⬅ SAME. Aa layer ma     │
│                   polars, scipy,               koi gap nathi.        │
│                   statsmodels, sklearn,        Tamari pase          │
│                   PyTorch, cvxpy               institutional-grade   │
│                   Jupyter + internal libs      tools free ma che.    │
├─────────────────────────────────────────────────────────────────────┤
│  Backtest         Internal event-driven     Custom event-driven,    │
│                   engines (almost never     vectorbt, backtrader,   │
│                   open-source)              nautilus_trader         │
├─────────────────────────────────────────────────────────────────────┤
│  Execution        Internal SOR, FIX 4.2/    Broker REST API         │
│                   4.4, algo suite (TWAP/    (Kite/Dhan/Fyers/       │
│                   VWAP/IS/POV), IOC/FOK     Upstox/AliceBlue)       │
├─────────────────────────────────────────────────────────────────────┤
│  Risk             Real-time pre-trade risk  Pre-trade gate module   │
│                   server (separate, C++),   (File 06)               │
│                   VaR/stress/scenario                               │
├─────────────────────────────────────────────────────────────────────┤
│  Infra            Co-location (NSE co-lo),  Mumbai VPS, Docker,     │
│                   bare metal, CPU pinning,  systemd                 │
│                   NUMA, kernel tuning                               │
├─────────────────────────────────────────────────────────────────────┤
│  Monitoring       Internal + Grafana/       Grafana + Prometheus,   │
│                   Prometheus, PagerDuty     Telegram alerts         │
└─────────────────────────────────────────────────────────────────────┘
```

> **Notice research row.** Institutional research stack ane tamaro research stack **almost identical** che. Gap execution/infra layer ma che, **idea layer ma nahi.** Etle tamaro leverage: aisi strategies shodho je *slow* hoy (latency-insensitive) pan *statistically sound* hoy.

### Language reality
```
C++   — HFT core, feed handlers, matching, order gateways
Rust  — nava systems ma C++ ne replace karta (memory safety)
Python— research, backtesting, orchestration, ML  (90% of quant work)
Java  — bank/institutional OMS, risk systems
q/kdb+— time-series data, bahu jagya e aajey standard
OCaml — Jane Street (unique)
```

---

## 4. Institutional Reference Architecture

```
  MARKET DATA                 EXECUTION                    RESEARCH
  ───────────                 ─────────                    ────────
  Exchange multicast          Smart Order Router           Tick DB (kdb+)
        │                            ▲                          │
        ▼                            │                          ▼
  Feed Handler (C++)          Algo Engine                 Feature Store
   normalize/arbitrate         TWAP/VWAP/POV/IS                 │
        │                            ▲                          ▼
        ▼                            │                     Backtest Farm
  ┌──────────────────┐         ┌─────┴────────┐          (parallel, cluster)
  │  NORMALIZED BUS  │────────►│ PORTFOLIO &  │                 │
  │  (Aeron/shm)     │         │ RISK SERVER  │◄────────────────┘
  └────────┬─────────┘         │  (single,    │          model deployment
           │                   │  authoritative)
           ▼                   └─────▲────────┘
  ┌──────────────────┐               │
  │ ALPHA CONTAINERS │───signals─────┘
  │  α1  α2  α3 ...  │
  │  (many, isolated)│  ← ek alpha crash thay to biju chalu rahe
  └──────────────────┘
```

**Aa diagram ma 4 design lessons je tame copy kari shako:**
1. **Alphas ne isolate karo.** Har strategy alag module/process. Ek nu crash badhu na pade.
2. **Risk/portfolio server EK ane authoritative.** Badha alphas tya thi pass thay. Distributed risk = no risk.
3. **Signal generation ane execution alag.** Alpha "shu joie" kahe, execution "kevi rite levu" nakki kare.
4. **Research ane production ek j feature code vapare.** Feature store = training-serving skew no antidote.

---

## 5. Strategy Families — kayo kya vapare che

| Family | Horizon | Kon | Retail viable? |
|---|---|---|---|
| Market making | ms | Citadel Sec, Optiver, iRage | ❌ speed + inventory risk |
| Latency arb | µs | HFT firms | ❌ |
| Statistical arb / pairs | min–days | RenTech, Millennium pods | ✅ **ha** (crowded pan possible) |
| Index/ETF arb | s–min | Jane Street, Indian prop | ⚠️ capital + speed |
| Cash-futures basis | min–days | Indian prop desks | ⚠️ capital intensive, thin spread |
| Options vol arb | days | Optiver, IMC, Quadeye | ⚠️ advanced, greeks discipline |
| Trend following (CTA) | weeks–months | AHL, Winton, Aspect | ✅ **ha, sauthi accessible** |
| Cross-sectional factors | months | AQR, quant MFs | ✅ ha (screening-based) |
| Event/news driven | min–days | pods, some funds | ⚠️ data cost uncho |
| Intraday microstructure | min | prop desks | ✅ ha, careful costs sathe |

> **Retail mate sauthi realistic 3:** (1) trend following on liquid futures, (2) intraday mean reversion on liquid equities, (3) cross-sectional relative-value on a small universe. Traney latency-insensitive che.

---

## 6. Alpha Lifecycle — process je tame copy karva jevo che

```
IDEA (economic rationale hovu J joie)
  │  "Kem aa paisa exist kare che? Kon loss ma che ane kem?"
  │  Aa question no jawab na hoy → e pattern noise che. STOP.
  ▼
QUICK SCREEN  (vectorized, dirty, hours)
  │  Signal ma information che kharu? IC/hit-rate jovo.
  ▼
PROPER BACKTEST  (event-driven, costs, walk-forward, days-weeks)
  ▼
RISK REVIEW  (capacity, correlation with existing book, worst-case)
  ▼
PAPER / SHADOW  (weeks-months — institutional ma pan!)
  ▼
LIVE SMALL  (10% size)
  ▼
SCALE UP  (gradual, metrics gate par)
  ▼
MONITOR & DECAY  (performance degrade → retire. Alpha marse J.)
```

**Institutional expectation:** 100 ideas ma ~10 backtest survive kare, ~3 paper survive kare, ~1 live scale thay, ane e 1 pan 1–3 varsh ma decay thase. **Aa failure rate normal che.** Retail loko ek strategy fail thay tyare game chhodi de che — ej sauthi moti mistake.

---

## 7. Institutional Risk Practice

```
PRE-TRADE (microseconds ma, order pehla)
  fat-finger limits · max order value · price collar
  self-trade prevention · symbol restrictions · per-strategy limits

INTRADAY (continuous)
  position limits per symbol/sector/strategy
  greeks (delta/gamma/vega) limits for options books
  real-time P&L ane drawdown monitors
  concentration ane liquidity-adjusted exposure

END OF DAY
  VaR (95%/99%), Expected Shortfall
  Stress tests: 2008, 2020-Mar, 2016 demonetisation, flash crash
  Scenario analysis, capital allocation review

ORGANIZATIONAL
  Risk team traders thi INDEPENDENT reporting kare che
  Kill switch authority risk pase, trader pase nahi
  Post-mortem on every limit breach
```
> **Tame ekla cho to pan aa separation simulate karo:** risk config file ne "bija" ni property manavo. Market hours ma e file edit karvani KADI nahi. Limit change fakt weekend par, likhit reason sathe.

---

## 8. Reading list (actually useful)

**Books**
- *Advances in Financial Machine Learning* — López de Prado (labeling, purged CV, dollar bars, deflated Sharpe) — **aa folder na File 02/07 nu deep version**
- *Algorithmic Trading* ane *Machine Trading* — Ernest Chan (mean reversion/momentum, practical, code sathe)
- *Trading and Exchanges* — Larry Harris (**microstructure ni bible**, File 01 no full version)
- *Quantitative Trading* — Chan (starter)
- *Option Volatility and Pricing* — Natenberg (options jaso to)
- *Inside the Black Box* — Narang (institutional structure no overview)

**Papers/topics**
- Lopez de Prado — "The Deflated Sharpe Ratio", "Backtest Overfitting"
- Avellaneda & Stoikov — market making framework
- Almgren–Chriss — optimal execution / market impact
- Fama-French factor literature (cross-sectional base)

**Open source jovu**
- `nautilus_trader` — production-grade event-driven architecture (Rust+Python). **Aa codebase vanchvi = ek course.**
- `vectorbt` — fast vectorized research
- `arctic` (Man AHL) — tick storage patterns
- `qlib` (Microsoft) — ML pipeline structure

**India specific**
- NSE circulars (charges, freeze qty, circuit limits) — bookmark karo
- Broker API docs: Zerodha Kite Connect, Dhan, Fyers, Upstox, AliceBlue
- SEBI algo trading framework — retail algo regulation evolve thai rahyu che, **track karo**

---

## 9. Honest gap analysis — tame vs them

| Dimension | Them | You | Verdict |
|---|---|---|---|
| Latency | µs | 150ms | ❌ compete na karo |
| Data | tick, alt-data, ₹crores | broker feed | ⚠️ manageable |
| Capital | ₹1000cr+ | limited | ⚠️ **actually advantage** — small size = zero market impact, tame aisi opportunities le shako je fund mate too small che |
| Research tools | internal | open source | ✅ ~parity |
| Talent | 100 PhDs | tame | ❌ pan tame ek j strategy par focus kari shako |
| Costs | rock-bottom | retail rates | ❌ real disadvantage — frequency low rakho |
| Regulation/compliance | heavy | light | ✅ advantage, faster iteration |
| Speed of change | slow, committees | tame | ✅ advantage |

> **Strategy: tame speed ane data ma haaro cho, pan *nimbleness* ane *size* ma jito cho.** Aisi edges par focus karo je: (a) latency-insensitive, (b) capacity-limited (fund ne interest nathi), (c) economically justified. Ej realistic playing field che.

---

## Margin Questions
1. Tamaru realistic frequency zone kayu ane kem?
2. Research stack ma institutional gap kem nathi?
3. Alpha containers ane risk server ne alag rakhvano lesson kayo?
4. 100 ideas mathi ketli live jay che — ane aa number kem yaad rakhvo?
5. Small capital kaya kaya rite advantage che?
6. Institutional risk team traders thi independent kem che?
