# 00 — START HERE

> આ folder no use 3 alag alag moment ma thay che:
> 1. **Learning mode** — pehli var vanchva mate (01 → 08 sequence)
> 2. **Design mode** — system architect karti vakhte (10-system-design-playbook)
> 3. **Chart mode** — live screen ni samne besi ne (11-chart-cheatsheet)
>
> Ek j vaar vanchi ne badhu yaad rehse nahi. Retention no method file na ant ma che — **e part sauthi pehla vancho.**

---

## File Map

| # | File | Kyare kholvi |
|---|------|--------------|
| 01 | `01-market-microstructure.md` | Order types, order book, slippage, cost math |
| 02 | `02-data-engineering.md` | Tick→bar, log returns, splits/dividends, survivorship |
| 03 | `03-realtime-architecture.md` | WebSocket vs REST, ring buffer, Redis, reconnect logic |
| 04 | `04-mean-reversion.md` | VWAP bands, Z-score, ADF, half-life |
| 05 | `05-momentum-and-ai-features.md` | EMA cross, ATR, Donchian, LLM sentiment layer |
| 06 | `06-risk-engine.md` | Position sizing, ATR stops, circuit breakers |
| 07 | `07-backtesting-hygiene.md` | Lookahead, overfitting, Sharpe/Sortino/MDD/PF |
| 08 | `08-paper-trading-and-live-ops.md` | DRY_RUN router, state reconciliation, slippage tracking |
| 09 | `09-industry-stack.md` | HFT firms / prop desks / funds actually kya use kare che |
| 10 | `10-system-design-playbook.md` | End-to-end blueprint, diagrams, decision tables |
| 11 | `11-chart-cheatsheet.md` | Live chart ni samne — 1 page |
| 12 | `12-market-evolution-and-data-physics.md` | Ticker tape to UDP multicast, 3 eras, data physics |
| 13 | `13-three-brain-architecture.md` | Three-Brain system: Microsecond hot path, Risk Governor, AI loop |
| 14 | `14-microstructure-diagnostics-and-math.md` | Timescale mismatch, ADF unit root, Hurst exponent, OU half-life math |
| 15 | `15-live-operations-and-self-healing-runbook.md` | Live server, Web terminal, hot reloading, circuit breakers & runbook |
| 16 | `16-self-healing-vs-self-modifying.md` | Self-Healing vs Self-Modifying: Safe mode vs live mutation, Risk Veto boundary |

---

## આખી picture — ek j diagram ma

```
                    ┌──────────────────────────────────────────┐
                    │        EXCHANGE (NSE / BSE)              │
                    │   Matching Engine · Order Book           │
                    └───────────────┬──────────────────────────┘
                                    │ ticks (UDP multicast → broker)
                    ┌───────────────▼──────────────────────────┐
  FILE 01, 03  ───► │  BROKER API   (WebSocket stream + REST)  │
                    └───────────────┬──────────────────────────┘
                                    │
                    ┌───────────────▼──────────────────────────┐
  FILE 02, 03  ───► │  INGESTION    normalize → validate →     │
                    │               ring buffer → resample     │
                    └───────────────┬──────────────────────────┘
                                    │ clean bars
                    ┌───────────────▼──────────────────────────┐
  FILE 02      ───► │  FEATURE ENGINE  log returns, VWAP,      │
  FILE 04,05        │                  Z-score, ATR, EMA, LLM  │
                    └───────────────┬──────────────────────────┘
                                    │ features
                    ┌───────────────▼──────────────────────────┐
  FILE 04, 05  ───► │  STRATEGY / ALPHA   signal ∈ {-1,0,+1}   │
                    └───────────────┬──────────────────────────┘
                                    │ desired position
                    ┌───────────────▼──────────────────────────┐
  FILE 06      ───► │  RISK ENGINE  sizing · stops · kill-switch│  ◄── VETO POWER
                    └───────────────┬──────────────────────────┘
                                    │ approved order
                    ┌───────────────▼──────────────────────────┐
  FILE 08      ───► │  EXECUTION ROUTER   DRY_RUN | LIVE       │
                    └───────────────┬──────────────────────────┘
                                    │ fills
                    ┌───────────────▼──────────────────────────┐
  FILE 08      ───► │  STATE / OMS   positions · P&L · recon   │
                    └───────────────┬──────────────────────────┘
                                    │
                    ┌───────────────▼──────────────────────────┐
  FILE 07      ───► │  ANALYTICS   backtest vs live · metrics  │
                    └──────────────────────────────────────────┘
```

**Ek rule je આખા folder ma repeat thase:**
> Data layer ane Strategy layer ne alag rakho. Strategy ne khabar j na hovi joie ke data live che ke historical. Ej ek design decision che je backtest ne live sathe match karave che.

---

## Memory Retention — kem yaad rakhvu

તમારો સવાલ: *"vachu to badhu khbr padi jay... pan yaad kem rahe?"*
Problem vanchvaano nathi — **retrieval practice no abhav** che. Vanchva thi "familiarity" male che, "recall" nahi. Exam ma aej difference blank cause kare.

### The 4-Pass System (per file)

```
PASS 1  — SKIM (5 min)
          Fakt headings + diagrams. Kai pan samajvaani koshish nahi.
          Purpose: brain ne "map" male, details pachhi hook thase.

PASS 2  — READ + MARGIN QUESTION (30 min)
          Har section pachhi margin ma EK question lakho — answer nahi.
          "Slippage kem vadhe che thin book ma?"
          Questions banavvi = active encoding. Highlight karvu = passive, useless.

PASS 3  — BLANK PAGE (next day, 15 min)
          File band karo. Blank page par aakho flow aap-meli lakho.
          Je bhulai gayu — ej tamaru actual weak spot che. Khali ej part re-read karo.

PASS 4  — BUILD IT (same week)
          Concept ne 20-line code ma convert karo. Compile na thay to samjaya nathi.
          Code > notes. Hamesha.
```

### Spaced Repetition schedule

| Kyare | Shu karvu |
|-------|-----------|
| Day 0 | Read + margin questions |
| Day 1 | Blank-page recall (10 min) |
| Day 3 | Fakt diagrams jovo, mathi flow bolo |
| Day 7 | Ek strategy end-to-end code karo |
| Day 21 | Bija ne samjavo (ke rubber duck ne) |

### Kem kaam kare che (mechanism)
- **Retrieval > Review.** Brain mathi kadhvu = memory strengthen. Aankho thi vanchvu = feeling of knowing, e alag vastu.
- **Chunking.** 60 concepts yaad nahi rahe. 6 chunks (Data → Feature → Signal → Risk → Execution → Analytics) yaad rahi jase, ane dareki chunk ma 10 concepts hook thai jase.
- **Interleaving.** Ek j din ma fakt mean-reversion na vancho. Mean-reversion + risk + microstructure mix karo. Harder feel thase, better stick thase.

---

## Note file kem lakhvi — format je kaam ave

Aa folder ni dareki file aa 6-block structure follow kare che. Tamari potani notes pan aaj structure ma lakho:

```markdown
# Concept Name

## 1. WHY   — a concept na hot to kai break thaat?
   (problem first. solution pachhi. brain problem ne yaad rakhe che.)

## 2. WHAT  — 3 line definition, jargon vagar

## 3. DIAGRAM — ASCII / mermaid. Text vagar samjai jay evu.

## 4. MATH  — formula + har symbol no meaning + ek numerical example
   (real numbers nakho. RELIANCE @ 2450, na ke "asset X @ P")

## 5. CODE  — 20-40 line runnable snippet, comments sathe

## 6. FAILURE MODES — a concept live ma kem tute che
   (aa block sauthi valuable che. interview ane P&L, banne ahiya nakki thay)
```

**Do NOT do:**
- Slides jevi bullet-only notes — context gum thai jay, 3 mahina pachhi nakama
- Copy-paste formulas symbols samjaya vagar
- Failure modes chhodi devi — production ma 80% time aej kaam ave

**Naming convention:** `NN-topic-name.md`, numbered so ke sequence khovai nahi. Ek file = ek mental chunk. 500 line thi moti file = badly chunked.

---

## Design mode vs Chart mode — be alag brain

| | System design karti vakhte | Chart ni samne |
|---|---|---|
| Question | "Aa failure state ma shu thase?" | "Aa setup mara rules ma fit thay che?" |
| File | `10-system-design-playbook.md` | `11-chart-cheatsheet.md` |
| Time | Hours, deliberate | Seconds, checklist |
| Output | Architecture decision + tradeoff note | Yes/No + size |

Aa be ne mix na karo. Chart ni samne architecture vichaarso to trade bagdi jase; design karti vakhte "aaje market shu karse" vicharso to system bagdi jase.
