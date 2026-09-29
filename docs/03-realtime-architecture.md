# 03 — Real-Time Architecture: WebSocket, REST, Buffers

> **Chunk**: TRANSPORT + STATE. Message: *"Data ne pakadvu alag skill che, data ne yaad rakhvu alag."*
> Tamara Redis/distributed-systems background ma aa file sauthi jaldi click thase.

---

## 1. WHY

Strategy ne har tick par 20,000-row DataFrame par `.rolling(20).mean()` mangvu nathi. E 40ms lese, ane 200 symbols ma tame permanently pachhal rahi jaso.

Real-time system nu core problem: **bounded memory + bounded latency ma unbounded stream handle karvi.**

---

## 2. WebSocket vs REST — decision, opinion nahi

```
   ┌──────────────── PUSH (WebSocket) ────────────────┐
   │  Broker ──tick──► You    (exchange nakki kare    │
   │         ──tick──►         ke kyare)              │
   │  latency: 20–80ms | bandwidth efficient          │
   │  pan: connection state manage karvi pade,        │
   │       reconnect, sequence gaps, backpressure     │
   └──────────────────────────────────────────────────┘

   ┌──────────────── PULL (REST poll) ────────────────┐
   │  You ──GET /quote──► Broker   (tame nakki karo)  │
   │      ◄──snapshot────                             │
   │  latency: 200ms–2s | rate limited | stateless    │
   │  pan: simple, debug easy, idempotent             │
   └──────────────────────────────────────────────────┘
```

| Kaam | Kayu vaparvu | Kem |
|---|---|---|
| Live ticks / LTP | **WebSocket** | Push, low latency, no rate limit per-tick |
| Order book depth | **WebSocket** | Update frequency uchi |
| Order placement | **REST** | Idempotency, explicit response, retry semantics |
| Order status / fills | **WebSocket (postback) + REST reconcile** | WS fast, REST = truth |
| Historical bars | **REST** | Bulk, cached, paginated |
| Positions / margin | **REST poll (30–60s)** | Slow-changing, must be authoritative |
| Instrument master | **REST, din ma 1 vaar** | Token↔symbol mapping roz badlay che |

> **Golden rule:** **WebSocket = speed. REST = truth.**
> Strategy WS thi chale, pan **reconciliation hamesha REST thi** thay. WS message drop thay to khabar nahi pade; REST snapshot kadi juthu nahi bole.

---

## 3. WebSocket ni reality — 6 vastu handle karvi j padse

```
┌──────────────────────────────────────────────────────────────┐
│ 1. RECONNECT with exponential backoff + jitter               │
│      1s → 2s → 4s → 8s → 16s → cap 30s   (+ random 0-1s)     │
│      Jitter vagar: 500 clients ek saathe reconnect = storm    │
│                                                               │
│ 2. HEARTBEAT / STALE DETECTION                                │
│      Connection "open" hovu ≠ data aavvu.                     │
│      if now - last_tick_ts > 10s  → state = STALE             │
│      if now - last_tick_ts > 30s  → HALT TRADING + alert      │
│                                                               │
│ 3. RESUBSCRIBE on reconnect                                   │
│      Naya socket = khali subscription list. Broker yaad       │
│      nathi rakhto. Subscription state tamari pase rakho.      │
│                                                               │
│ 4. BINARY PARSING                                             │
│      Indian brokers binary packets mokle che (struct.unpack). │
│      Prices paisa ma integer hoy → /100. Debug ma bhulaay che.│
│                                                               │
│ 5. BACKPRESSURE                                               │
│      Opening 5 min ma tick rate 10x. Consumer slow thay to    │
│      queue grow → OOM. Bounded queue + drop-oldest policy.    │
│      Quote data mate old tick DROP karvo safe che.            │
│      Order/fill data mate KADI drop na karvu.                 │
│                                                               │
│ 6. GAP DETECTION                                              │
│      Sequence number hoy to track karo. Gap → REST snapshot   │
│      thi state rebuild karo.                                  │
└──────────────────────────────────────────────────────────────┘
```

```python
import asyncio, time, random

class FeedClient:
    def __init__(self, symbols, queue: asyncio.Queue):
        self.symbols, self.q = symbols, queue
        self.last_tick = 0.0
        self.state = "DISCONNECTED"

    async def run(self):
        delay = 1.0
        while True:
            try:
                await self._connect()
                await self._subscribe(self.symbols)   # reconnect par phari
                self.state, delay = "LIVE", 1.0       # backoff reset
                await self._consume()
            except Exception as e:
                self.state = "DISCONNECTED"
                await asyncio.sleep(delay + random.random())
                delay = min(delay * 2, 30)            # exponential + cap

    async def _on_tick(self, tick):
        self.last_tick = time.time()
        try:
            self.q.put_nowait(tick)
        except asyncio.QueueFull:
            _ = self.q.get_nowait()        # drop oldest quote
            self.q.put_nowait(tick)

    def is_healthy(self):
        return self.state == "LIVE" and (time.time() - self.last_tick) < 10
```

> **Aa `is_healthy()` ne risk engine sathe jodo.** False thay to nava order block. Aa ek 5-line function tamne ek din bachavse.

---

## 4. Ring Buffer — O(1) rolling computation

### Problem
```
Har tick par: df.append(tick); df.rolling(20).mean()
   → O(n) memory grow, O(n) recompute, GC pressure
   → 6 kalak pachhi process 4GB, latency 200ms
```

### Solution: fixed-size circular buffer + incremental stats

```
      capacity = 8                head (next write)
                                      │
      ┌────┬────┬────┬────┬────┬────┬─▼──┬────┐
      │ t1 │ t2 │ t3 │ t4 │ t5 │ t6 │ t7 │ t8 │
      └────┴────┴────┴────┴────┴────┴────┴────┘
        ▲
        └─ tail (oldest). t9 aavse → t1 overwrite thase.
           Memory KAYAM 8 slots. Allocation ZERO.
```

```python
import numpy as np

class RollingWindow:
    """O(1) push, O(1) mean/std. Welford-style incremental."""
    def __init__(self, size: int):
        self.size = size
        self.buf  = np.zeros(size, dtype=np.float64)
        self.n    = 0
        self.head = 0
        self._sum = 0.0
        self._sumsq = 0.0

    def push(self, x: float):
        if self.n == self.size:                 # full → evict oldest
            old = self.buf[self.head]
            self._sum   -= old
            self._sumsq -= old * old
        else:
            self.n += 1
        self.buf[self.head] = x
        self._sum   += x
        self._sumsq += x * x
        self.head = (self.head + 1) % self.size

    @property
    def is_full(self): return self.n == self.size

    def mean(self): return self._sum / self.n if self.n else float("nan")

    def std(self):
        if self.n < 2: return float("nan")
        var = (self._sumsq - self._sum**2 / self.n) / (self.n - 1)
        return np.sqrt(max(var, 0.0))          # max() = float error guard

    def zscore(self, x):
        s = self.std()
        return (x - self.mean()) / s if s and s > 0 else 0.0
```

> ⚠️ **Numerical stability:** `sumsq − sum²/n` catastrophic cancellation kari shake che jyare values moti ane variance nani hoy (RELIANCE 2450 ± 2). Production ma **Welford's online algorithm** vaparo. Ahiya `max(var, 0)` guard minimum protection che.

**Per-symbol state:**
```python
class SymbolState:
    def __init__(self):
        self.ret_20   = RollingWindow(20)     # z-score mate
        self.atr_14   = RollingWindow(14)
        self.vwap_num = 0.0                   # Σ price×qty  (day cumulative)
        self.vwap_den = 0.0                   # Σ qty
        self.last_bar = None

    def vwap(self):
        return self.vwap_num / self.vwap_den if self.vwap_den else None
```
200 symbols × ~2KB = 400KB. Aakhu RAM ma, zero DB hit.

---

## 5. Kyare Redis joie (ane kyare nahi)

```
┌─────────────────────────────────────────────────────────────┐
│ SINGLE PROCESS?  →  in-process ring buffer. Redis NAHI.     │
│    Redis call = 0.2–1ms network hop + serialization.        │
│    Local numpy array = 50 nanoseconds. 10,000x faster.      │
│    "Redis fast che" — pan RAM karta nahi.                   │
├─────────────────────────────────────────────────────────────┤
│ MULTI PROCESS / MULTI SERVICE?  →  Redis joie.              │
│    Ingestion, strategy, risk, execution alag process ma     │
│    → shared state joie                                       │
└─────────────────────────────────────────────────────────────┘
```

### Redis structures — kayu kaam mate

| Structure | Use case | Command |
|---|---|---|
| **String/Hash** | Latest quote snapshot | `HSET quote:RELIANCE ltp 2450 ts ...` |
| **Streams** | Tick/event bus, consumer groups, replay | `XADD ticks:RELIANCE * ...` |
| **Sorted Set** | Time-indexed recent bars | `ZADD bars:RELIANCE <ts> <json>` |
| **List (capped)** | Simple recent-N buffer | `LPUSH` + `LTRIM key 0 99` |
| **Pub/Sub** | Fire-and-forget signal broadcast | `PUBLISH signals ...` |
| **SETNX + TTL** | Distributed lock (duplicate order guard) | `SET lock:ord NX EX 5` |

> **Streams vs Pub/Sub — aa interview ma pucchay che:**
> Pub/Sub ma consumer down hoy to message **kayam mate gayu**. Stream ma message persist rahe che, consumer group offset track kare che, crash pachhi replay thay. **Order/fill events mate hamesha Streams.** Quote broadcast mate Pub/Sub thi chali jay.

```python
# Capped stream — memory bounded rakho
r.xadd("ticks:RELIANCE", {"ltp": 2450.0, "qty": 50, "ts": ts},
       maxlen=10_000, approximate=True)   # approximate=True → O(1) trim

# Consumer group: crash-safe processing
r.xgroup_create("ticks:RELIANCE", "strategy-grp", id="0", mkstream=True)
msgs = r.xreadgroup("strategy-grp", "worker-1",
                    {"ticks:RELIANCE": ">"}, count=100, block=50)
# process... then:
r.xack("ticks:RELIANCE", "strategy-grp", msg_id)   # ACK vagar = redelivery
```

**⚠️ Redis persistence:** Default config ma RDB snapshot. Crash thay to last few seconds gum. **Positions/orders Redis ma *only* na rakho** — Postgres/SQLite = source of truth, Redis = cache/bus.

---

## 6. Process architecture — 3 stage evolution

```
STAGE 1: MONOLITH (ahiya thi shuru karo)
┌────────────────────────────────────────────┐
│  asyncio single process                    │
│  feed_task ─► queue ─► strategy_task ─►    │
│                        risk ─► executor    │
│  state: in-memory dicts + SQLite           │
└────────────────────────────────────────────┘
✔ <20 symbols, debug easy, no network hops
✘ ek bug = badhu down

STAGE 2: SPLIT BY CONCERN (Redis bus)
┌──────────┐  Stream   ┌──────────┐  Stream  ┌──────────┐
│ INGESTOR │──ticks───►│ STRATEGY │──signals►│ EXECUTOR │
└──────────┘           └──────────┘          └────┬─────┘
      │                                           │
      └─────────► Redis (state) ◄─────────────────┘
                       │
                 Postgres (truth: orders, fills, positions)
✔ independent restart, strategy crash ≠ position orphan
✔ ingestor restart kar shako without losing positions

STAGE 3: INSTITUTIONAL
  Feed handlers (C++/Rust) → normalized bus (Kafka/Aeron)
  → Alpha containers (many) → Portfolio/risk server (single, authoritative)
  → Smart Order Router → venues
  + separate historical tick store (kdb+/ClickHouse/Arctic)
```

> **Tame Stage 1 thi shuru karo.** Stage 2 jyare symbols > 25 thay athva jyare "strategy restart karvu che pan position hold karvi che" evi jarurat pade. Stage 3 fakt team ane capital sathe.

---

## 7. Event loop discipline (Python specific)

```python
# ❌ ONE blocking call = aakho feed pachhal
async def on_tick(tick):
    requests.post(url, json=order)      # 200ms BLOCK — badhi ticks queue ma
    pd.read_csv("big.csv")              # blocking I/O
    df.rolling(200).mean()              # CPU heavy

# ✅ 
async def on_tick(tick):
    state.update(tick)                          # O(1), pure CPU, microseconds
    if sig := strategy.check(state):
        asyncio.create_task(executor.send(sig)) # fire & forget, don't await
```
**Rule:** hot path ma **koi network call nahi, koi disk I/O nahi, koi pandas nahi.** Pandas backtesting mate che, live loop mate nahi. Live ma plain floats ane numpy scalars.

---

## 8. FAILURE MODES

| Failure | Shu thay | Guard |
|---|---|---|
| WS "open" pan data frozen | Stale price par trade | Heartbeat < 10s check, pre-order gate |
| Reconnect pachhi resubscribe bhulaya | Chup-chaap koi data nahi | Resubscribe + first-tick-received assert |
| Unbounded queue | OOM kill, positions orphan | `maxsize` queue, drop-oldest quotes |
| Reconnect storm | Broker ban/rate-limit | Exponential backoff + jitter |
| Redis restart | Cached state gayu | Startup par REST thi rebuild, Postgres = truth |
| Duplicate order (retry) | 2x position | Client order ID + Redis `SETNX` idempotency |
| Blocking call in loop | Latency spike 2s | Hot path ma network/disk ban, profile karo |
| Instrument token badlayo | Wrong symbol ma trade | Roz sakaale instrument master refresh |

---

## Margin Questions
1. "WebSocket = speed, REST = truth" no practical meaning shu?
2. Ring buffer O(1) kem che ane sumsq approach ma numerical risk shu?
3. Redis Streams vs Pub/Sub — order events mate kayu ane kem?
4. Backpressure ma quote drop karvu safe kem, fill drop karvu kem nahi?
5. Single process ma Redis vaparvu kem slower che?
6. Exponential backoff ma jitter kem joie?
