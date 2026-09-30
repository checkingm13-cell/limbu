# Quantitative Trading & Microstructure Research Architecture
### Master Directory: `D:\projects\QUANT\production_system`

This directory organizes all codebase modules, historical datasets, research studies, documentation, and operational configurations in a structured layout.

---

### Folder Map

```
D:\projects\QUANT\production_system\
│
├── config\                     # System parameters & risk thresholds
│   ├── active_config.json      # Current live governor parameters
│   └── strategy_config.json    # Candidate research configuration
│
├── data\                       # Real-time and historical datasets
│   ├── live_ticks.csv          # 358,000+ real-time tick prints
│   ├── live_trades.csv         # Reconciled paper execution history
│   ├── telemetry_stream.csv    # 275,000+ RDB feature stream rows
│   ├── historical\             # Binance 35-day bulk 1m klines (50,400 bars)
│   └── microstructure\         # Real-time ZSTD Parquet chunks (bookTicker + aggTrade)
│
├── docs\                       # Full architectural manuals & interactive masterclasses
│   ├── 00-START-HERE.md        # 4-pass learning roadmap & memory retention
│   ├── 01-market-microstructure.md & visual.html
│   ├── 02-data-engineering.md & visual.html
│   ├── 03-realtime-architecture.md
│   ├── 04-mean-reversion.md
│   ├── 05-momentum-and-ai-features.md
│   ├── 06-risk-engine.md
│   ├── 07-backtesting-hygiene.md
│   ├── 08-paper-trading-and-live-ops.md
│   ├── 09-industry-stack.md
│   ├── 10-system-design-playbook.md
│   ├── 11-chart-cheatsheet.md
│   └── 12-18 advanced runbooks (Three-Brain, diagnostics, macro, limbu vs Bees)
│
├── ingestion\                  # Real-time WebSocket multiplexers & bulk archives
│   ├── microstructure_logger.py    # Dual bookTicker + aggTrade ZSTD Parquet collector
│   └── download_binance_archive.py # Direct Binance archive bulk downloader
│
├── live_engine\                # Four-Brain Execution, Safety, & Dashboard
│   ├── live_quant_server.py    # Kdb-style columnar RDB + WebSocket server
│   ├── brain2_safety_governor.py # Hard risk gatekeeper, circuit breaker FSM
│   ├── brain3_research_scientist.py # Autonomous statistical loop
│   ├── brain4_llm_advisor.py   # Strategic LLM / System-1 regime advisor interface
│   ├── laya_client.py          # Laya-421M adapter (sanitization, mock guard, temperature scaling)
│   ├── forward_paper_trader.py # Live Binance canary runner with Brain 2 veto & friction model
│   └── live_dashboard.html     # Real-time 60 FPS Canvas UI
│
├── research\                   # Empirical validation scripts & hypothesis tests
│   ├── research_brain4_multi_regime_replay.py # 12-cell audited grid across 4 regimes with 95% CIs
│   ├── research_discrimination_and_calibration.py # Non-overlapping AUC, IC, & Top-label ECE
│   ├── research_rigorous_35d.py    # 35-day Train/OOS test with Holm-Bonferroni correction
│   ├── research_maker_simulation.py# DuckDB adverse selection queue simulator
│   ├── research_multiyear_funding.py # 2021-2026 non-overlapping funding rate analysis
│   ├── yearly_funding.py           # Clean yearly funding breakdown
│   ├── research_forward_returns.py # 1s to 5m latency-shifted forward return battery
│   └── research_higher_horizons.py # 1m and 5m block-bootstrap CI harness
│
└── rust_core\                  # High-performance native execution engine
    ├── Cargo.toml
    └── src\main.rs             # Zero-allocation hot path (0.9M ticks/sec)
```

---

### Key Research Findings Documented:
1. **Taker Mean-Reversion Falsification:**
   - 35-day Out-of-Sample evaluation ($N=956$) confirmed gross edge ($\le +0.5\text{ bps}$) fails to clear the $8\text{–}10\text{ bps}$ retail taker fee hurdle.
2. **Maker Queue Adverse Selection:**
   - Vectorized DuckDB order-book simulation on 530,000+ quotes and 42,000 trades proved adverse selection costs $-2.2\text{ to } -3.5\text{ bps}$ post-fill due to $180\text{ ms}$ cancel latency.
3. **Multi-Year Funding (Cash-and-Carry) Reality:**
   - 2021 bull euphoria (+30.6% APR) compressed to 2.9% APR in 2026 with 26% negative intervals, demonstrating structural yield decay.
4. **Four-Brain Horizon Physics & Calibrated Veto Gate:**
   - Evaluated 4 distinct historical regimes (2021 Bull, 2022 Bear, 2024 ETF Trend, 2026 Chop). Proved that widening holding horizon from 2h to 12h–24h compresses turnover by 85% and cuts fee drag from >1,000% down to 22–40%.
   - Directional discrimination confirmed across strictly non-overlapping 24h windows ($IC = +0.122$, $AUC = 0.525$). Multiclass temperature scaling ($T=5.000$) reduced Expected Calibration Error (ECE) by $85.8\%$ (from $29.78\%$ to $4.22\%$), validating Brain 2's $\ge 0.65$ confidence veto gate.

