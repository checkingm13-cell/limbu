# 01 — Market Microstructure & Order Execution

> **Chunk**: EXECUTION. Aa file no ek j sandesh — *"chart par je price dekhay che, e price tamne male nahi."* Gap ne samajvu = microstructure.

---

## 1. WHY — a layer na samje to shu tute?

Backtest ma strategy 40% CAGR aape che. Live ma -8%. Code same che, data same che.
Difference: backtest ma tame assume karyu ke **close price par fill thai jase**. Reality ma:

- Order queue ma 400 ma number par hato → fill j na thayo
- Fill thayo pan 0.12% uper → 200 trades ma 24% gayu
- STT + brokerage + GST + stamp duty → biju 0.4%
- Market order thick spread ma nakhyo → instant 0.3% loss

**Retail algo 90% aa layer ma marse che, strategy ma nahi.**

---

## 2. Order Book — market no actual dhancho

Exchange ni matching engine ek j kaam kare che: **price-time priority** thi buyers ane sellers ne match karvu.

```
        RELIANCE  —  LIVE ORDER BOOK (Depth of Market)

          BID SIDE (kharidnara)        ASK SIDE (vechnara)
        ┌────────────┬──────────┐    ┌──────────┬────────────┐
        │  Qty       │  Price   │    │  Price   │  Qty       │
        ├────────────┼──────────┤    ├──────────┼────────────┤
  L1    │    850     │ 2449.80  │    │ 2450.00  │   1,200    │  L1  ◄── BEST
  L2    │  2,300     │ 2449.75  │    │ 2450.05  │     900    │  L2
  L3    │  1,100     │ 2449.70  │    │ 2450.10  │   3,400    │  L3
  L4    │  5,000     │ 2449.60  │    │ 2450.25  │     600    │  L4
  L5    │    400     │ 2449.50  │    │ 2450.40  │   8,000    │  L5
        └────────────┴──────────┘    └──────────┴────────────┘
                     ▲         ▲      ▲
                     │         └──────┘
                     │          SPREAD = 2450.00 - 2449.80 = ₹0.20
                     │                 = 0.008%  (liquid stock)
                     │
             MID PRICE = (2449.80 + 2450.00)/2 = 2449.90
```

**Vocabulary (aa 6 word kayam kaam avse):**

| Term | Meaning | Kem matter kare |
|------|---------|-----------------|
| **Bid** | Sauthi uncho buy price | Tame vecho to *ahiya* fill thase |
| **Ask / Offer** | Sauthi nicho sell price | Tame kharido to *ahiya* fill thase |
| **Spread** | Ask − Bid | Har round-trip no minimum cost |
| **Depth** | Har level ni quantity | Tamari size absorb thase ke nahi |
| **Mid** | (Bid+Ask)/2 | "Fair" price — research ma aaj vaparo |
| **LTP** | Last traded price | ⚠️ Stale hoy shake. Signal aa par na banavo |

> **Trap #1:** Retail charts LTP batave che. LTP = *bhut kaal*. Tamaro execution price bid/ask thi nakki thay che, LTP thi nahi. Backtest ma close price vaparo cho to tame ek non-existent price par trade kari rahya cho.

---

## 3. Order Types — kyare kayo

```
┌─────────────────────────────────────────────────────────────────┐
│ MARKET ORDER — "gme te bhave, pan atyare"                       │
│   ✔ Fill guaranteed        ✘ Price guaranteed NAHI              │
│   Book ne uperthi khaay che: L1 → L2 → L3 ... jya sudhi qty pure│
│   Use: exit/stop-loss, ultra-liquid scrip, emergency flatten    │
├─────────────────────────────────────────────────────────────────┤
│ LIMIT ORDER — "aa bhave ke better, nahi to no thanks"           │
│   ✔ Price guaranteed       ✘ Fill guaranteed NAHI               │
│   Queue ma ubhu rahe (price-time priority)                      │
│   Use: entries, mean-reversion, illiquid scrip, passive alpha   │
├─────────────────────────────────────────────────────────────────┤
│ SL / SL-M — trigger price hit thay tyare activate thay          │
│   SL  = trigger pachhi LIMIT order nakhe  (gap ma fill na thay!)│
│   SL-M= trigger pachhi MARKET order nakhe (fill pakku, price na)│
│   ⚠️ Stop-loss ma SL-M vaparo. SL vaparso to gap-down ma order  │
│      pending rahi jase ane loss unlimited thai jase.            │
├─────────────────────────────────────────────────────────────────┤
│ BRACKET ORDER (BO) — entry + target + SL, ek j packet ma        │
│   Broker side par OCO (One-Cancels-Other) logic chale           │
│   ✔ Network/process crash thay to pan SL broker pase safe       │
│   ✘ Flexibility ochhi, intraday only, broker-dependent          │
│   ⚠️ 2020 pachhi ghana Indian brokers e BO band/limit karyu che │
│      → potana OMS ma OCO jate handle karvo pade (File 08)       │
└─────────────────────────────────────────────────────────────────┘
```

### Market order book ne kem "khaay" che — walk the book

100 share joiye → L1 ma 1,200 padya che → badha 2450.00 ma fill. Simple.
**5,000 share joiye to:**

```
  1,200 @ 2450.00  = 29,40,000
    900 @ 2450.05  =  22,05,045
  2,900 @ 2450.10  =  71,05,290   (3,400 mathi 2,900 lidha)
  ─────────────────────────────
  5,000 shares     = ₹1,22,50,335
  Average fill     = 2450.067
  Expected (L1)    = 2450.000
  SLIPPAGE         = ₹0.067/share = 0.0027%  ← aane "market impact" kahe che
```

Illiquid smallcap ma aej 5,000 qty 1.5% impact kari de. **Size vs depth** — always check.

---

## 4. Slippage — 4 alag source

```
Decision Price  ──────────────────────────────────►  Actual Fill
     2450.00                                            2451.10
        │                                                   ▲
        ├─► (a) SIGNAL LAG        bar close → compute    +0.05
        ├─► (b) NETWORK LATENCY   you → broker → exch    +0.15
        ├─► (c) SPREAD COST       bid/ask cross          +0.20
        └─► (d) MARKET IMPACT     book walk / adverse    +0.70
                                                       ───────
                                            TOTAL SLIPPAGE ₹1.10
```

| Source | Typical (liquid NSE) | Kem ghatadvu |
|--------|---------------------|--------------|
| Signal lag | 50–300 ms | Incremental computation, no full-df recompute |
| Network latency | 20–80 ms retail / 5–15 ms co-lo | Broker co-location, region-matched VPS |
| Spread | 0.01–0.05% | Limit orders, liquid hours ma trade |
| Impact | size-dependent | Order slicing (TWAP/VWAP), participation cap |

**Latency budget — retail algo ni reality:**
```
tick exchange par     t=0
broker feed           t≈ 20-60ms
tamaro process        t≈ 60-90ms
strategy compute      t≈ 90-95ms
order broker par      t≈ 115-150ms
exchange par ack      t≈ 150-200ms
─────────────────────────────────
ROUND TRIP ≈ 150–250 ms
```
> **Aa number pachhi tame HFT nahi kari shako.** 200ms ma HFT firm 40 vaar trade kari chuki hoy. Etle tamari edge **timing** ma nahi, **logic/holding period** ma hovi joie. Strategy ni holding period >= 5 minutes rakho to latency noise ma dabai jase.

---

## 5. Transaction Friction — India specific (aa math kharekhar kharo che)

**Equity Intraday** (order value = qty × price)

| Charge | Rate | Kona par |
|--------|------|----------|
| Brokerage | ₹20 or 0.03% (je ochhu) | per executed order |
| STT | 0.025% | **sell side only** |
| Exchange txn charge (NSE) | ~0.00297% | both sides |
| SEBI charges | 0.0001% | both sides |
| Stamp duty | 0.003% (max ₹300/day) | **buy side only** |
| **GST** | **18%** | on (brokerage + txn + SEBI) |
| DP charges | — | intraday ma nahi (delivery ma lage) |

**Equity Delivery**: STT 0.1% *banne* side, stamp duty 0.015% buy side, DP charge ~₹13-16 per sell scrip.
**F&O (Options)**: STT 0.1% on **premium, sell side**; brokerage flat ₹20/order → % ma ghanu ochhu.

> ⚠️ Rates SEBI/Exchange circulars thi badlaay che. Code ma **config file** ma rakho, hardcode nahi. Quarterly verify karo.

### Break-even calculation — a number rozz kaam avse

```python
def intraday_costs(buy_price, sell_price, qty,
                   brokerage_rate=0.0003, brokerage_cap=20.0):
    buy_val, sell_val = buy_price*qty, sell_price*qty
    turnover = buy_val + sell_val

    brokerage = min(buy_val*brokerage_rate, brokerage_cap) \
              + min(sell_val*brokerage_rate, brokerage_cap)
    stt       = sell_val * 0.00025           # sell side only
    txn       = turnover * 0.0000297
    sebi      = turnover * 0.000001
    stamp     = min(buy_val * 0.00003, 300)  # buy side only
    gst       = 0.18 * (brokerage + txn + sebi)

    total = brokerage + stt + txn + sebi + stamp + gst
    gross = sell_val - buy_val
    return {"gross": gross, "costs": total, "net": gross - total,
            "cost_pct": total / buy_val * 100}

# RELIANCE: 100 qty, 2450 → 2455
# gross ₹500 | costs ≈ ₹123 | net ≈ ₹377 | cost ≈ 0.050% of capital
```

**Break-even move (round trip, intraday equity) ≈ 0.055–0.09%** depending on brokerage cap hitting.
Slippage 0.05% umero → **realistic hurdle ≈ 0.12%**.

> **Aa ek line ghadi lo:** Strategy ni *average* winning trade 0.12% thi nani hoy, to e strategy mathematically dead che — win-rate ketlo pan sundar hoy.

**Frequency no killer effect:**

| Trades/day | Cost/trade | Daily drag | **Yearly drag (250 days)** |
|---|---|---|---|
| 2 | 0.10% | 0.20% | 50% |
| 5 | 0.10% | 0.50% | 125% |
| 20 | 0.10% | 2.00% | 500% |

Aaj karan che ke retail HFT impossible che ane **holding period = risk management** che.

---

## 6. FAILURE MODES — live ma shu tute

| Failure | Lakshan | Fix |
|---|---|---|
| Backtest ma close-price fill | Live P&L backtest thi hamesha nichu | Bar close par signal, **next bar open** par fill assume karo + slippage model |
| SL order gap-down ma pending | Loss expected thi 5x | SL-M vaparo; ane portfolio-level kill switch (File 06) |
| Illiquid scrip ma size | Fill price sharam-jank | Pre-trade check: `qty <= 0.1 × avg_top5_depth` |
| Freeze quantity breach | Order exchange reject kare | NSE freeze limits check karo, order slice karo |
| Circuit limit hit | Order pending, exit nahi thay | Positions ma per-scrip circuit distance monitor karo |
| Costs ignore | Paper profit, real loss | Costs ne backtest engine ma **hardcode** karo, optional na rakho |

---

## Margin Questions (jate answer lakho, file band kari ne)
1. LTP par signal banavvu kem khatarnak che?
2. SL ane SL-M ma exact difference ane kyare kayo?
3. 20 trades/day nu yearly cost drag ketlu?
4. Market impact ane spread cost ma faraq shu?
5. Retail algo ni round-trip latency ketli, ane ena thi strategy design ma shu constraint ave?
