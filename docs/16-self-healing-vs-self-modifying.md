---
title: "Self-Healing vs. Self-Modifying: The Institutional Safety Boundary"
tags:
  - quant
  - architecture
  - risk-management
  - self-healing
  - obsidian
date: 2026-09-28
status: production
---

# Self-Healing vs. Self-Modifying Architecture

> [!CAUTION] The Golden Quant Rule
> **Self-Healing is NOT Self-Modifying.**
> - **Self-Modifying (Dangerous):** Market Noise $\to$ Real-Time Half-Life Calculation $\to$ Mutate Cooldown / Z-Score $\to$ Live Trade $\to$ **Live Overfitting Trap**.
> - **Self-Healing (Institutional):** Market Anomaly $\to$ **Deterministic Safe Mode (Halt / Reduce Size)** $\to$ Offline AI Diagnosis $\to$ Walk-Forward / OOS Validation $\to$ Risk Governor Audit $\to$ Versioned Config $\to$ **Live Promotion**.

---

## 1. The Core Architecture

```mermaid
flowchart TD
    subgraph LIVE_CORE["RUST / FAST CONTROL PLANE (Microseconds to Milliseconds)"]
        direction TB
        Ticks["Market Data (Ticks / Bars)"] --> Ring["In-Memory Ring Buffers"]
        Ring --> Regime["Regime Engine\n(Hurst, ADX, EMA Slope, VWAP)"]
        Regime --> Strategy["Strategy Selector\n(Mean Reversion vs. Momentum)"]
        Strategy --> Signal["Signal Generated\n(Buy / Sell / Flat)"]
        
        Signal --> RiskVeto{"Hard Risk Engine / VETO\n(Position size, ATR stops,\ncircuit breakers, feed health)"}
        
        RiskVeto -->|REJECT| Drop["Drop Signal\n(Log Veto Reason)"]
        RiskVeto -->|APPROVE| OrderRouter["Order Router\n(Exchange / Broker API)"]
        
        Ring --> Telemetry["Fast Telemetry Worker\n(Streaming metrics, not raw 70k CSVs)"]
    end

    subgraph OFFLINE_RESEARCH["BRAIN 3: SLOW RESEARCH PLANE (Python + LLM)"]
        direction TB
        Telemetry --> MetricsStore[("Research Store / Telemetry Log")]
        MetricsStore --> Diag["AI Post-Mortem Diagnosis"]
        Diag --> Stats["Statistical Battery\n(ADF, Hurst, OU Half-Life)"]
        Stats --> Backtest["Walk-Forward Optimization (WFO) & OOS"]
        Backtest --> CandConfig["Candidate Config\n(strategy_config.json)"]
    end

    subgraph GOVERNOR["BRAIN 2: RISK GOVERNOR GATEKEEPER"]
        CandConfig --> Audit{"Deterministic 5-Point Audit\n(Stop loss, entry hurdle, win rate viability)"}
        Audit -->|PASS| ApprConfig["Promote to active_config.json\n(Versioned, Immutable)"]
        Audit -->|FAIL| Rejection["Reject to Research Ledger"]
    end

    ApprConfig -.->|Dynamic Hot-Reload| LIVE_CORE
```

---

## 2. The Three Cardinal Separations

### 1. Strategy $\ne$ Risk (File 06 Compliance)
- The Strategy Engine **proposes** a trade (`Signal`).
- The Strategy Engine has **zero authority** to route orders to an exchange.
- The Risk Service acts as an independent execution gatekeeper with **unconditional VETO power**.
- If a strategy bug triggers 100 buy orders in 1 second, the Risk Engine drops 97 of them at the gate.

### 2. Telemetry $\ne$ Research
- **Fast Telemetry (Hot Path):** Pre-computes and pushes structured metrics ($Z$, VWAP, EMA slope, execution slippage) from the in-memory ring buffer.
- **Slow Research (Cold Path):** Ingests telemetry offline. Runs heavy mathematical regressions (ADF unit root, Hurst exponent, OU half-life decay, parameter grid sweeps, LLM macro sentiment) over minutes or hours.

### 3. Anomaly Response $\ne$ Parameter Mutation
- When performance degrades (e.g. 3 consecutive losses or session drawdown limit):
  - The live engine **does not guess new parameters on the fly**.
  - The live engine **drops risk** (`ACTIVE` $\to$ `CAUTION` $\to$ `CIRCUIT_BREAKER_HALT`).
  - Parameter changes require the full **WFO $\to$ OOS $\to$ Risk Governor Audit** pipeline.

---

## 3. Files 05–11 Institutional Mapping

| File | Architectural Role | Hot Path vs. Cold Path |
|---|---|---|
| [[05-momentum-and-ai-features|05]] | Momentum Alpha & Async LLM Worker | **Cold:** LLM scores news asynchronously into Redis; **Hot:** Strategy reads latest cached float. |
| [[06-risk-engine|06]] | Hard Risk Guardrails & Independent Veto | **Hot:** Position sizing, ATR stops, hard dollar stops, and kill-switches. |
| [[07-backtesting-hygiene|07]] | Validation, WFO & OOS Testing | **Cold:** Prevents lookahead leaks, p-hacking, and overfitted parameter sweeps. |
| [[08-paper-trading-and-live-ops|08]] | Paper Trading, Reconciliation & Ops | **Hot/Cold:** Mock router (`DRY_RUN = True`), state reconciliation, and crash recovery. |
| [[09-industry-stack.md|09]] | Technology & Horizon Calibration | Calibration: Competing at seconds-to-hours intraday horizon. |
| [[10-system-design-playbook.md|10]] | 7-Layer Blueprint & Build Order | Architecture reference for layer boundaries. |
| [[11-chart-cheatsheet.md|11]] | Human Live-Session Battlecard | Operator situational awareness. |

---

## 4. Vault Navigation
- [[13-three-brain-architecture|13: Three-Brain Quantitative Architecture]]
- [[14-microstructure-diagnostics-and-math|14: Quantitative Microstructure Diagnostics & Math]]
- [[15-live-operations-and-self-healing-runbook|15: Live Operations & Self-Healing Runbook]]
- [[00-START-HERE|00: Master Vault Index]]
