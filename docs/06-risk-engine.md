# 06 — Risk Engine (Hard Guardrails)

> **Chunk**: SURVIVAL. Message: *"Alpha optional che. Risk engine nathi."*
> Aa file ni ek j line yaad rakho: **Risk engine ne strategy par VETO power hovo joie, ane e strategy code thi alag process/module ma hovu joie.**

---

## 1. WHY — ganit je debate nathi

```
   DRAWDOWN            RECOVERY JOIE
   ──────────────────────────────────
     −10%      →        +11.1%
     −20%      →        +25.0%
     −33%      →        +50.0%
     −50%      →       +100.0%
     −75%      →       +300.0%
     −90%      →      +900.0%   ← game over. Aa recover nathi thatu.
```

**Asymmetry brutal che.** Etle #1 kaam profit kamavvu nathi, **moti drawdown ne impossible banavvi** che.

### Risk of Ruin ni feel

| Risk/trade | Win rate | 20 consecutive losses ni asar |
|---|---|---|
| 1% | 50% | capital 82% bache |
| 2% | 50% | capital 67% bache |
| 5% | 50% | capital 36% bache |
| 10% | 50% | capital 12% bache ⚠️ |

50% win-rate strategy ma 20-loss streak **hamesha** aavse — question kyare no che, ke no nahi.
**Etle 1% (max 2%) per trade standard che.** Aa conservative nathi, aa arithmetic che.

---

## 2. Position Sizing — sauthi important formula

> Loko indicator par mahina gale che. **Actual performance difference sizing ma che.** Same signals, be alag sizing → ek account 30% up, biju wiped.

### The core equation

```
                    Capital × Risk%
   Quantity  =  ────────────────────────
                 Entry Price − Stop Price
   
   (denominator = "risk per share" = stop distance)
```

**Ex:**
```
Capital      = ₹5,00,000
Risk         = 1%  →  ₹5,000   ← aa amount tame KHOVA taiyar cho
Entry        = ₹2,450 (RELIANCE)
ATR(14)      = ₹25
Stop         = 2450 − 2×25 = ₹2,400
Risk/share   = ₹50

Quantity     = 5,000 / 50 = 100 shares
Position val = 100 × 2450 = ₹2,45,000  (capital no 49% — leverage/margin check!)
```

> **Notice:** position value 49% che pan **risk fakt 1%** che. Loko aa be ne confuse kare che. "Capital no 49% laga didho" ≠ "49% risk". Risk = stop distance × qty.

### Fixed vs Fractional

```
FIXED CAPITAL RISK — risk base = STARTING capital (₹5L kayam)
   ✔ predictable, simple
   ✘ profit ma compound nahi thay; loss ma bhi risk ghatto nahi ⚠️

FRACTIONAL RISK — risk base = CURRENT equity
   equity 5L → risk 5,000
   equity 6L → risk 6,000   (compounding up)
   equity 4L → risk 4,000   (natural de-risking down) ✅
   
   ✔ Geometric growth, automatic defense in drawdown
   ✔ Mathematically ruin impossible (theoretically)
   → ✅ DEFAULT AA VAPARO
```

```python
from dataclasses import dataclass

@dataclass
class RiskConfig:
    risk_per_trade: float = 0.01
    max_position_pct: float = 0.25     # single scrip ma capital cap
    max_gross_exposure: float = 2.0    # leverage cap
    max_positions: int = 5
    daily_loss_limit: float = 0.03     # 3% → kill switch
    max_drawdown_limit: float = 0.15   # 15% peak thi → full stop
    min_atr_multiple: float = 1.5

class PositionSizer:
    def __init__(self, cfg): self.cfg = cfg

    def size(self, equity, entry, stop, lot_size=1, min_qty=1):
        risk_amt   = equity * self.cfg.risk_per_trade
        per_share  = abs(entry - stop)
        if per_share <= 0:
            return 0, "INVALID_STOP"

        qty = int(risk_amt / per_share)

        # cap 1: single position value
        max_val = equity * self.cfg.max_position_pct
        qty = min(qty, int(max_val / entry))

        # cap 2: lot size (F&O) / round lots
        qty = (qty // lot_size) * lot_size

        if qty < min_qty:
            return 0, "SIZE_TOO_SMALL"      # ⚠️ skip trade — force na karo
        return qty, "OK"
```

> **Sauthi common ane sauthi mongho bug:** `qty < min_qty` thay tyare loko `qty = 1` kari de che. E moment par tamaru risk model **maru gayu** — tame hve ₹5,000 nahi, kadach ₹40,000 risk kari rahya cho. **Trade skip karo. Hamesha.**

### Kelly — kem full Kelly kadi na vaparvi

```
   f* = W − (1−W)/R      W = win rate, R = avg_win/avg_loss

   W=0.55, R=1.5  →  f* = 0.55 − 0.45/1.5 = 0.25  (25% per trade!)
```
Full Kelly theoretically optimal growth aape che pan **50%+ drawdowns** sathe, ane e assume kare che ke tame W ane R **exactly** jano cho. Tame nathi janta — estimate error sathe Kelly over-bets kare che.
**Industry practice: quarter-Kelly (0.25×) ke ochhu.** Ane retail mate: simple 1% fixed-fractional Kelly karta safer ane sane che.

---

## 3. Volatility-Based Stops

```
   Entry 2450, ATR 25
   
   2500 ┤
   2450 ┼━━━●ENTRY ─────────────────────────────
   2425 ┤   ╎ 1×ATR  → noise ma hit thase ❌
   2400 ┤   ╎ 2×ATR  → ✅ standard intraday
   2375 ┤   ╎ 3×ATR  → swing/positional
        └───┴────────────────────────────►
```

| Multiple | Kyare | Trade-off |
|---|---|---|
| 1.0–1.5 | Scalping, very liquid | Uchu stop-out rate |
| **2.0–2.5** | **Intraday default** | Balanced |
| 3.0–4.0 | Swing / trend following | Ochha stops, moti per-trade loss |

**Kem ATR ane % nahi** — File 05 ma covered, pan ek line ma: ATR stop *market ne puchhe che* ke "normal noise ketlu che", % stop *tamne* puchhe che. Market vadhare jaane che.

### Stop types

```python
class StopManager:
    def __init__(self, atr_mult=2.0, trail_mult=3.0, breakeven_at=1.0):
        self.am, self.tm, self.be = atr_mult, trail_mult, breakeven_at

    def initial(self, entry, atr, side):
        return entry - side * self.am * atr

    def update(self, side, entry, atr, cur_stop, extreme_since_entry, price):
        # 1. move to breakeven after 1R profit
        r = self.am * atr
        if side * (price - entry) > self.be * r:
            cur_stop = max(cur_stop, entry) if side > 0 else min(cur_stop, entry)
        # 2. chandelier trail
        trail = extreme_since_entry - side * self.tm * atr
        cur_stop = max(cur_stop, trail) if side > 0 else min(cur_stop, trail)
        return cur_stop     # ⚠️ RATCHET: stop KADI loosen na thay
```

> **Iron rule:** stop **kadi** widen na thay. "Thodu vadhare space aapu" = aakhu risk model void. Code ma `max()`/`min()` thi enforce karo — discipline par bharoso na rakho, **code par rakho.**

### Time stop (underrated)
```python
if bars_held > max_hold_bars and pnl_r < 0.3:
    exit("TIME_STOP")
```
Trade tamaro thesis 2×half-life ma prove na kare, to thesis khoti hati. Capital free karo. **Mean reversion ma aa sauthi valuable exit che.**

---

## 4. Circuit Breakers — layered kill switches

```
┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 1 — PER TRADE            1% equity        → stop-loss     │
├─────────────────────────────────────────────────────────────────┤
│ LEVEL 2 — CONSECUTIVE LOSSES   3 in a row       → 30 min cool-off│
├─────────────────────────────────────────────────────────────────┤
│ LEVEL 3 — DAILY LOSS           3% equity        → FLATTEN ALL,  │
│                                                   din band      │
├─────────────────────────────────────────────────────────────────┤
│ LEVEL 4 — WEEKLY LOSS          6% equity        → week off,     │
│                                                   review        │
├─────────────────────────────────────────────────────────────────┤
│ LEVEL 5 — MAX DRAWDOWN         15% from peak    → SYSTEM HALT,  │
│                                                   manual restart │
├─────────────────────────────────────────────────────────────────┤
│ LEVEL 6 — OPERATIONAL          feed stale / recon mismatch /    │
│                                unknown position → HALT + ALERT  │
└─────────────────────────────────────────────────────────────────┘
```

```python
import time
from enum import Enum

class TradingState(Enum):
    ACTIVE = "active"; COOLDOWN = "cooldown"
    HALTED_DAY = "halted_day"; HALTED_PERMANENT = "halted_permanent"

class CircuitBreaker:
    def __init__(self, cfg, start_equity):
        self.cfg = cfg
        self.peak = start_equity
        self.day_start = start_equity
        self.consec_losses = 0
        self.state = TradingState.ACTIVE
        self.cooldown_until = 0.0

    def on_fill(self, pnl):
        self.consec_losses = self.consec_losses + 1 if pnl < 0 else 0
        if self.consec_losses >= 3:
            self.state = TradingState.COOLDOWN
            self.cooldown_until = time.time() + 1800

    def check(self, equity, feed_healthy=True, recon_ok=True):
        self.peak = max(self.peak, equity)

        if not (feed_healthy and recon_ok):
            return TradingState.HALTED_DAY, "OPERATIONAL"

        dd = (self.peak - equity) / self.peak
        if dd >= self.cfg.max_drawdown_limit:
            self.state = TradingState.HALTED_PERMANENT
            return self.state, f"MAX_DD {dd:.1%}"

        day_loss = (self.day_start - equity) / self.day_start
        if day_loss >= self.cfg.daily_loss_limit:
            self.state = TradingState.HALTED_DAY
            return self.state, f"DAILY_LOSS {day_loss:.1%}"

        if self.state == TradingState.COOLDOWN and time.time() > self.cooldown_until:
            self.state = TradingState.ACTIVE
        return self.state, "OK"

    def can_open(self):
        return self.state == TradingState.ACTIVE
```

> **HALTED_PERMANENT ma auto-resume NAHI hovu joie.** Manual restart = insaan ne vichaarvani faraj pade che. 15% drawdown pachhi je system jate pachho chalu thai jay, e 40% sudhi jase.

---

## 5. Pre-Trade Gate — order mokalta pehla badhu ahiya thi pass thay

```
   SIGNAL
     │
     ▼
   ┌──────────────────────────────────────────────┐
   │ 1. Circuit breaker ACTIVE?            ❌→DROP │
   │ 2. Feed healthy (<10s)?               ❌→DROP │
   │ 3. Position recon clean?              ❌→DROP │
   │ 4. Already in this symbol?            ❌→DROP │
   │ 5. max_positions reached?             ❌→DROP │
   │ 6. Gross exposure < limit?            ❌→DROP │
   │ 7. Margin available (REST check)?     ❌→DROP │
   │ 8. qty >= min_qty after sizing?       ❌→DROP │
   │ 9. Liquidity: qty <= 10% of depth?    ❌→DROP │
   │10. Time window ok (09:20–15:10)?      ❌→DROP │
   │11. Expected move > 3× cost?           ❌→DROP │
   │12. Duplicate order guard (SETNX)?     ❌→DROP │
   └──────────────┬───────────────────────────────┘
                  ✅ ORDER
```

**Time window kem:** 09:15–09:20 ma spread pagal, price discovery chalu, gap fill chaos. 15:10 pachhi square-off pressure. Ghana desk 09:20–15:00 j trade kare che.

---

## 6. Portfolio-level risk (multi-symbol ma mandatory)

**Trap:** 5 positions × 1% = 5% risk? **Na.** Jo badha bank stocks hoy, to correlation ≈ 0.9, effective risk ≈ 4.5% ek j bet par.

```
Effective portfolio risk ≈ Σ risk_i × avg_correlation

Guards:
  • Max 2 positions per sector
  • Rolling correlation matrix; pairwise ρ > 0.7 → dusri position ne 50% size
  • Total gross exposure cap (2× equity intraday)
  • Net directional exposure cap (badha long = index bet che, e admit karo)
```

---

## 7. FAILURE MODES

| Failure | Result | Guard |
|---|---|---|
| Stop widen karvo | Ek trade = 10 trades no loss | Ratchet in code, manual override ban |
| Averaging down | Ruin no fastest rasto | Add-to-loser code ma exist j na hovu joie |
| `qty=1` fallback | Silent risk model death | `SIZE_TOO_SMALL` → skip |
| Correlated positions | 5% risk ≈ 1 bet | Sector/correlation cap |
| Daily limit soft | "aaje special case che" | Automated flatten, human se nahi |
| Margin shortfall | Broker auto-square-off worst price par | Pre-trade REST margin check |
| Gap beyond stop | Stop level meaningless | Overnight position size ghatadvo, ke intraday-only |
| Halt pachhi auto-resume | 15% → 40% | Manual restart mandatory |
| Risk engine strategy ni andar | Strategy bug = risk bug | **Alag module/process** |

---

## 8. Config template

```yaml
risk:
  risk_per_trade: 0.01
  sizing_mode: fractional        # fixed | fractional
  max_position_pct: 0.25
  max_gross_exposure: 2.0
  max_positions: 5
  max_per_sector: 2

stops:
  initial_atr_mult: 2.0
  trail_atr_mult: 3.0
  breakeven_at_r: 1.0
  max_hold_bars: 60

circuit_breakers:
  consecutive_losses: 3
  cooldown_minutes: 30
  daily_loss_limit: 0.03
  weekly_loss_limit: 0.06
  max_drawdown_limit: 0.15
  auto_resume_after_halt: false

session:
  entry_window: ["09:20", "15:00"]
  force_square_off: "15:15"
```
> **Risk parameters KADI code ma hardcode na karo.** Config ma rakho, version control ma rakho, change no audit log rakho. Change karo to *kem* lakho.

---

## Margin Questions
1. −50% drawdown pachhi recovery mate ketlu joie ane e kem matter kare?
2. "Position value 49%" ane "risk 1%" ma faraq?
3. Fixed vs fractional sizing — drawdown ma kayu automatically bachave?
4. `qty < min_qty` par trade force karvu kem fatal che?
5. Stop ratchet no meaning ane code ma kem enforce karvu?
6. 5 positions × 1% = 5% risk kem khotu che?
7. Max-DD halt pachhi auto-resume kem na hovu joie?
