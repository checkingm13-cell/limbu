# 08 — Paper Trading, State & Live Operations

> **Chunk**: OPERATIONS. Message: *"Backtest strategy test kare che. Paper trading **system** test kare che."*
> Aa file ma je bugs listed che, e badha tamne pehla mahina ma malse — guaranteed.

---

## 1. WHY — paper trading shu kharekhar test kare che

Loko samje che paper trading "strategy profitable che ke nahi" janva mate che. **Khotu.** E backtest e already kahi didhu.

Paper trading **aa** test kare che:
```
□ WebSocket 6 kalak sudhi reconnect vagar tike che?
□ Memory leak che? (6 kalak pachhi RAM jovo)
□ Timezone/session boundary bugs?
□ Broker rate limits hit thay che?
□ Instrument token mapping kharu che?
□ Order rejects gracefully handle thay che?
□ Crash pachhi state recover thay che?
□ Live signals backtest signals sathe match thay che?  ← SAUTHI IMPORTANT
□ Actual slippage modeled slippage sathe match thay che?
```

---

## 2. Mock Execution Router — `DRY_RUN = True`

**Design rule: ek j interface, be implementation.** Strategy ne khabar j na pade ke e live che ke paper.

```
                    ┌──────────────────┐
                    │    STRATEGY      │
                    └────────┬─────────┘
                             │  submit(Order)   ← identical call
                    ┌────────▼─────────┐
                    │  OrderRouter     │  (abstract)
                    └───┬─────────┬────┘
                        │         │
          ┌─────────────▼──┐   ┌──▼────────────────┐
          │  PaperRouter   │   │   LiveRouter      │
          │  simulate fill │   │   broker REST API │
          │  log to DB     │   │   log to DB       │
          └────────────────┘   └───────────────────┘
```

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import uuid, time

class OrderStatus(Enum):
    PENDING="PENDING"; OPEN="OPEN"; FILLED="FILLED"
    REJECTED="REJECTED"; CANCELLED="CANCELLED"; PARTIAL="PARTIAL"

@dataclass
class Order:
    symbol: str; side: str; qty: int
    order_type: str = "MARKET"       # MARKET | LIMIT | SL-M
    price: float | None = None
    trigger: float | None = None
    client_order_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    broker_order_id: str | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    avg_fill: float = 0.0
    intended_price: float = 0.0      # ⚠️ slippage measure karva mate — save karo!
    created_at: float = field(default_factory=time.time)

class OrderRouter(ABC):
    @abstractmethod
    def submit(self, order: Order) -> Order: ...
    @abstractmethod
    def cancel(self, order: Order) -> bool: ...
    @abstractmethod
    def positions(self) -> dict: ...


class PaperRouter(OrderRouter):
    def __init__(self, book_feed, db, slippage_bps=5, reject_rate=0.01):
        self.book, self.db = book_feed, db
        self.slip, self.reject_rate = slippage_bps / 10_000, reject_rate
        self._pos: dict[str, int] = {}

    def submit(self, o: Order) -> Order:
        bid, ask = self.book.best(o.symbol)
        if bid is None:
            o.status = OrderStatus.REJECTED; return self._persist(o)

        # realistic: bid/ask cross + slippage, mid nahi
        base = ask if o.side == "BUY" else bid
        sign = 1 if o.side == "BUY" else -1
        o.avg_fill   = base * (1 + sign * self.slip)
        o.filled_qty = o.qty
        o.status     = OrderStatus.FILLED
        o.broker_order_id = "PAPER-" + o.client_order_id

        self._pos[o.symbol] = self._pos.get(o.symbol, 0) + sign * o.qty
        return self._persist(o)

    def _persist(self, o):
        self.db.save_order(o)         # live sathe SAME table, mode column sathe
        return o
```

> **⚠️ Paper router ne bahu sharif na banavo.** Real router ma rejects, partial fills, latency ane requotes hoy che. Paper ma 100% instant fill hoy to tame ek **fantasy system** test kari rahya cho. Reject rate, random 100-300ms delay, ane occasional partial fill inject karo.

**Config par mode:**
```python
MODE = os.getenv("TRADING_MODE", "PAPER")   # PAPER | LIVE
router = LiveRouter(broker, db) if MODE == "LIVE" else PaperRouter(feed, db)

if MODE == "LIVE":
    assert os.getenv("I_UNDERSTAND_REAL_MONEY") == "yes"   # accidental live guard
    log.critical("🔴 LIVE MODE — REAL MONEY")
```

---

## 3. State Management — sauthi under-rated part

### Source of truth hierarchy

```
   ┌──────────────────────────────────────┐
   │ 1. BROKER / EXCHANGE   ← ABSOLUTE    │   REST thi vanchu
   ├──────────────────────────────────────┤
   │ 2. DATABASE (Postgres/SQLite)        │   durable, audit
   ├──────────────────────────────────────┤
   │ 3. REDIS cache                       │   fast, disposable
   ├──────────────────────────────────────┤
   │ 4. IN-MEMORY dicts                   │   fastest, volatile
   └──────────────────────────────────────┘
   
   Conflict ma HAMESHA upar vali jite. Kadi assume na karo ke
   tamaru memory state kharu che.
```

### Order lifecycle — badhi state handle karo

```
   PENDING ──submit──► OPEN ──┬──► FILLED
      │                       ├──► PARTIAL ──► FILLED / CANCELLED
      ├──► REJECTED           └──► CANCELLED
      │
      └──► ⚠️ UNKNOWN  (network timeout — order gayo? nathi gayo?)
```

> **UNKNOWN state j asli problem che.** Timeout thayo — order exchange par pahonchyo ke nahi, khabar nathi. **Retry KADI na karo blindly** → duplicate position.
> **Correct handling:** `client_order_id` sathe REST order-book query karo. Male to state adopt karo, na male to fresh submit karo.

```python
async def submit_safe(router, order, db):
    db.save_order(order)                       # ✅ submit PEHLA persist
    try:
        return await router.submit(order)
    except (TimeoutError, ConnectionError):
        order.status = OrderStatus.PENDING
        db.save_order(order)
        await asyncio.sleep(2)
        remote = await router.find_by_client_id(order.client_order_id)  # idempotency
        if remote:
            db.save_order(remote); return remote
        halt("UNKNOWN_ORDER_STATE")            # ⚠️ shanka ma HALT, guess nahi
```

### Idempotency
```python
# Redis distributed lock — duplicate signal guard
key = f"signal:{symbol}:{bar_ts}"
if not r.set(key, "1", nx=True, ex=300):
    return          # aa bar par already order gayo che
```

### Crash recovery — startup sequence
```
1. DB thi last known state load karo
2. Broker REST thi ACTUAL positions + orders fetch karo
3. COMPARE
4. Mismatch → HALT + alert (auto-fix NAHI)
5. Match → in-memory state rebuild, WS connect, resubscribe
6. Fakt tyare trading enable karo
```

---

## 4. Position Reconciliation

**Roz, ane din ma har 30 second.**

```python
def reconcile(local: dict, broker: dict, tol=0):
    issues = []
    for sym in set(local) | set(broker):
        l, b = local.get(sym, 0), broker.get(sym, 0)
        if abs(l - b) > tol:
            issues.append({
                "symbol": sym, "local": l, "broker": b, "diff": b - l,
                "severity": "CRITICAL" if (l == 0 or b == 0) else "WARNING"
            })
    return issues
```

| Scenario | Meaning | Action |
|---|---|---|
| local 0, broker 100 | **Orphan position** — fill maryo, system ne khabar nahi | 🔴 HALT, manual review |
| local 100, broker 0 | **Phantom** — order reject/cancel thayo | 🔴 HALT, local clear |
| local 100, broker 50 | **Partial fill** miss thayo | 🟡 Local ne broker sathe sync |
| Extra symbol broker ma | Manual trade ke old position | 🔴 HALT |

> **Rule: reconciliation mismatch par auto-correct NA karo.** Halt + alert. Auto-correct karso ane logic ulti hase to system potej position doubling kari nakhse. **Insaan ne jovva do.**

### End of day
```
15:15  square-off (intraday)
15:35  broker thi final positions + trades pull
15:40  DB reconcile, P&L compute (costs sathe)
15:45  slippage report (niche)
16:00  daily digest: trades, P&L, signals-vs-fills, errors, DD status
```

---

## 5. Live vs Backtest Slippage Tracking

**Aa loop j tamara backtest ne honest banave che.**

```
   BACKTEST          →  ek slippage assumption (5 bps)
       │                      ▲
       │                      │ UPDATE
       ▼                      │
   PAPER/LIVE        →  ACTUAL measured slippage
```

```python
def log_execution(order, decision_price, decision_ts, db):
    sign = 1 if order.side == "BUY" else -1
    slip_bps = sign * (order.avg_fill - decision_price) / decision_price * 10_000
    db.save_exec_quality({
        "symbol": order.symbol, "side": order.side, "qty": order.qty,
        "decision_price": decision_price, "fill_price": order.avg_fill,
        "slippage_bps": slip_bps,                         # +ve = tamne nukshan
        "latency_ms": (order.filled_at - decision_ts) * 1000,
        "hour": datetime.fromtimestamp(decision_ts).hour,
        "order_type": order.order_type,
    })
```

**Weekly analysis — aa cuts kaadho:**
```sql
SELECT symbol, order_type, hour,
       COUNT(*) n,
       AVG(slippage_bps) avg_slip,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY slippage_bps) p95,
       AVG(latency_ms) avg_latency
FROM exec_quality
GROUP BY symbol, order_type, hour
ORDER BY avg_slip DESC;
```

**Shu shodhvu:**
```
• Kayo symbol systematically kharab? → universe mathi kaadho
• 09:15–09:30 ma slippage 3x?         → entry window khesedo
• MARKET vs LIMIT no gap?             → order type badlo
• Size vadhe tyare slip vadhe?        → order slicing joie
• Actual p95 >> backtest assumption?  → BACKTEST UPDATE KARO, phari validate
```

> **Feedback loop mandatory che.** Measured slippage backtest ma pachhi nakho ane strategy re-run karo. Ghani strategies aa step pachhi marginal thai jay che — **e sacho jawab che**, khota sundar backtest karta.

### Signal reconciliation (backtest vs live)
Live ma je signals aavya, ej din nu backtest chalavo, compare karo:
```
Match rate < 95% → code paths diverge thaya che
Common causes: warm-up state, EMA adjust=True, session reset, rounding,
               missing bars, tick-vs-bar timing
```
Aa mismatch shodhvo j tamari sauthi valuable debugging exercise hase.

---

## 6. Monitoring — minimum viable

```
HEALTH (har 30s)
  ├── feed_lag_seconds           > 10  → WARN, > 30 → HALT
  ├── event_loop_lag_ms          > 100 → WARN
  ├── memory_mb                  growing linear → leak
  ├── open_orders_count          stuck > 5 min → alert
  ├── position_recon_status      mismatch → CRITICAL
  └── circuit_breaker_state      any halt → alert

TRADING (per event)
  ├── signals_generated / orders_sent / fills   (gap = problem)
  ├── reject_count + reason codes
  ├── realized + unrealized P&L
  └── current drawdown from peak

ALERTS → Telegram/WhatsApp bot. Email dhimo che.
  🔴 CRITICAL: halt, recon mismatch, unknown order, feed dead
  🟡 WARN:     high slippage, reject spike, lag
  🟢 INFO:     EOD summary
```

---

## 7. Deployment reality (India)

```
□ VPS Mumbai region ma (broker servers ni najik) — latency 40ms → 8ms
□ Systemd service, Restart=always, pan startup ma recon gate
□ Do NOT auto-resume trading pachhi crash — recon pass thaya pachhi j
□ Logs structured JSON, 90 din retention (audit + debugging)
□ Secrets env/vault ma, git ma KADI nahi
□ NTP time sync — clock drift = wrong bar boundaries
□ Kill switch: ek command je badhu flatten kare ane halt kare
□ Broker API rate limits: 3-10 orders/sec typical, respect karo
□ Access token roz sakaale expire thay — auto-refresh flow joie
```

### Paper → Live transition ladder
```
Week 1-4   PAPER, full system, roz recon
Week 5-6   LIVE with 10% of intended size     ← real fills, nano risk
Week 7-8   LIVE with 25%
Week 9-12  LIVE with 50%
Month 4+   Full size (jo metrics backtest range ma hoy)

Koi pan stage ma: live Sharpe < backtest Sharpe × 0.5  →  ek step pachho jao
```

---

## 8. FAILURE MODES

| Failure | Result | Guard |
|---|---|---|
| Paper router too perfect | False confidence | Reject/latency/partial inject karo |
| Timeout par blind retry | Duplicate position | client_order_id + query-before-retry |
| Recon auto-fix | Position doubling | Halt only, manual fix |
| State fakt memory ma | Crash = orphan position | DB first, then submit |
| Token expiry unhandled | Din ni vachche badhu band | Auto-refresh + alert |
| LIVE mode accidentally | Real paisa | Env guard + loud log |
| Slippage measure na karvu | Backtest kayam juthu rehse | exec_quality table, weekly review |
| Memory leak | 5 kalak pachhi OOM | RSS monitor, bounded structures |
| Clock drift | Bar boundaries khota | NTP |

---

## Margin Questions
1. Paper trading kharekhar shu test kare che (strategy nahi to shu)?
2. UNKNOWN order state ne kem handle karvu ane blind retry kem fatal?
3. Reconciliation mismatch par auto-fix kem na karvu?
4. Source-of-truth hierarchy ma broker sauthi upar kem?
5. Slippage feedback loop backtest ne kevi rite honest banave che?
6. Live vs backtest signal match rate < 95% hoy to kya jovu?
