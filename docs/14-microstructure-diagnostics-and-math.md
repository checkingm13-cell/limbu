---
title: "Quantitative Microstructure Diagnostics: Timescale Mismatch, ADF, Hurst & OU Half-Life"
tags:
  - quant
  - mathematics
  - statistics
  - microstructure
  - mean-reversion
  - obsidian
date: 2026-09-28
status: production
---

# Quantitative Microstructure Diagnostics

> [!NOTE] Fundamental Microstructure Principle
> **The same numerical Z-score does NOT represent the same market condition across different sampling frequencies.**
> On 1-minute bars, $Z > +2.0$ represents an institutional overextension that reverts over 10–15 minutes.  
> On 100-millisecond raw ticks, $Z > +2.0$ represents aggressive aggressive order-flow momentum that pumps higher.

---

## 1. The Timescale Mismatch Discovery

During initial live testing on Binance WebSocket ticks (`btcusdt@trade`), the live bot produced:
- **31 trades in 5 minutes**
- **Win Rate:** $19.4\%$
- **Net Return:** $-\$10.99$

### The Root Cause: Frequency Inversion

```text
BACKTEST (Profitable)
1-minute bars
14-period EMA ≈ 14 minutes of trend info
5 trades / 16 hours
Z > 2.0 = Real institutional overextension → REVERTS

LIVE EXECUTION (Unprofitable Churn)
100-ms raw ticks
15-tick EMA ≈ 1.5 seconds of trend info
31 trades / 5 minutes
Z > 2.0 = Momentum breakout / aggressive market buy sweep → CONTINUES PUMPING
```

---

## 2. Empirical Forward Return Decay (Alpha Attribution)

By analyzing $10,678$ live ticks recorded during the session, Brain 3 measured the **conditional forward return** of price following every $Z > +2.0$ trigger:

| Horizon | Observations | Avg Price Change ($\Delta P$) | Empirical Behavior | Short Trade Result |
|---|---|---|---|---|
| **5 seconds** | 10 events | $\mathbf{+\$8.56}$ | Momentum continuation | **LOSS** |
| **15 seconds** | 10 events | $\mathbf{+\$10.82}$ | Upward expansion | **LOSS** |
| **30 seconds** | 10 events | $\mathbf{+\$13.45}$ | Upward expansion | **LOSS** |
| **60 seconds** | 10 events | $\mathbf{+\$19.89}$ | Strong trend breakout | **LOSS** |
| **120 seconds** | 10 events | $\mathbf{+\$40.96}$ | Regime pump | **CATASTROPHIC LOSS** |

> [!WARNING] Empirical Conclusion
> Shorting raw ticks at $Z > +2.0$ during an active session is **shorting into an order-flow pump**. The bot was acting as liquidity for momentum sweepers.

---

## 3. Mathematical Microstructure Battery

To replace guessing with mathematical certainty, [[13-three-brain-architecture#Brain 3: Autonomous AI Research Scientist (Minutes / Hours)|Brain 3]] implements three pure-NumPy statistical routines:

### A. Augmented Dickey-Fuller (ADF) Unit Root Test
Tests whether the spread series $y_t = P_t - \text{VWAP}_t$ is stationary (mean-reverting) or non-stationary (random walk / unit root).

#### Regression Model:
$$\Delta y_t = \alpha + \beta y_{t-1} + \sum_{i=1}^p \gamma_i \Delta y_{t-i} + \epsilon_t$$

- **Null Hypothesis ($H_0$):** $\beta = 0$ (Unit root present; series is non-stationary).
- **Alternative ($H_1$):** $\beta < 0$ (Stationary; mean-reverting).
- **Test Statistic:**
  $$t_{\text{ADF}} = \frac{\hat{\beta}}{\text{SE}(\hat{\beta})}$$

#### MacKinnon Critical Value Thresholds ($N > 500$):
- **$1\%$ Significance:** $t < -3.43 \implies p < 0.01$ (Strong Mean Reversion)
- **$5\%$ Significance:** $t < -2.86 \implies p < 0.05$ (Moderate Mean Reversion)
- **$10\%$ Significance:** $t < -2.57 \implies p < 0.10$ (Weak Mean Reversion)

**Live BTC Result on 65,811 ticks:**  
$$t_{\text{ADF}} = \mathbf{-11.851} \ll -3.43 \implies \mathbf{p < 0.001}$$
*The spread between price and cumulative VWAP is unconditionally stationary over an hour horizon.*

---

### B. Hurst Exponent ($H$) via Rescaled Range ($R/S$) Analysis
Measures the long-term memory and fractal persistence of the series.

#### Algorithm:
1. Divide series $X$ into sub-periods of length $\tau \in \{4, 8, 16, 32, 64, 128, 256, 512\}$.
2. For each chunk:
   - Demean: $Y_t = X_t - \bar{X}$
   - Cumulative deviation: $Z_t = \sum_{i=1}^t Y_i$
   - Range: $R(\tau) = \max(Z) - \min(Z)$
   - Standard deviation: $S(\tau) = \sqrt{\frac{1}{\tau}\sum (X_i - \bar{X})^2}$
3. Regress $\log(R/S)$ against $\log(\tau)$:
   $$\log(R/S) = H \cdot \log(\tau) + c$$

#### Regime Interpretation:
- $\mathbf{H < 0.45}$: **Anti-Persistent / Mean-Reverting** (Price reversals dominate).
- $\mathbf{0.45 \le H \le 0.55}$: **Geometric Brownian Motion** (Random walk, zero predictability).
- $\mathbf{H > 0.55}$: **Persistent / Momentum** (Price trends in same direction).

**Live BTC Result:**
- Raw Price: $H = \mathbf{0.989}$ (Extreme persistent trending momentum).
- Sub-second Spread: $H = \mathbf{0.983}$ (Microsecond tick clustering acts as momentum).

---

### C. Ornstein-Uhlenbeck (OU) Mean Reversion Half-Life ($\tau_{1/2}$)
Models the spread as a continuous mean-reverting stochastic differential equation:

$$dx_t = \theta (\mu - x_t) dt + \sigma dW_t$$

Where:
- $\theta$: Speed of mean reversion ($\text{time}^{-1}$).
- $\mu$: Long-term mean (VWAP $\to 0$).
- $\sigma$: Volatility parameter.
- $W_t$: Standard Brownian motion.

#### Discrete Estimation via AR(1) OLS:
$$\Delta x_t = x_t - x_{t-1} = \alpha + \beta x_{t-1} + \epsilon_t$$

Relating continuous $\theta$ to discrete slope $\beta$:
$$\beta = -\theta \Delta t \implies \theta = -\frac{\beta}{\Delta t}$$

#### Analytical Derivation of Half-Life:
Taking expectations of the SDE:
$$\mathbb{E}[x_t - \mu] = (x_0 - \mu) e^{-\theta t}$$

The half-life $\tau_{1/2}$ is the exact time required for an excursion $(x_0 - \mu)$ to decay to half its magnitude:
$$\frac{\mathbb{E}[x_{\tau_{1/2}} - \mu]}{x_0 - \mu} = \frac{1}{2} \implies e^{-\theta \tau_{1/2}} = \frac{1}{2}$$

$$-\theta \tau_{1/2} = \ln\left(\frac{1}{2}\right) = -\ln(2)$$

$$\tau_{1/2} = \frac{\ln(2)}{\theta} = -\frac{\ln(2)}{\beta} \cdot \Delta t$$

---

## 4. The Mathematical Proof of Strategy Failure

During live execution, the AI Agent measured:
- **Measured Ornstein-Uhlenbeck Half-Life:** $\tau_{1/2} = \mathbf{53.1\text{ to }77.5\text{ seconds}}$ ($\approx 440\text{ to }559\text{ ticks}$).
- **Actual Average Trade Duration in Live Log:** $\bar{T} = \mathbf{3.5\text{ seconds}}$ ($\approx 25\text{ ticks}$).

> [!CAUTION] The Core Mathematical Insight
> Because the trade was exiting or stopping out in **$3.5\text{ seconds}$**, but the physical mean-reversion process requires **$53.1\text{ seconds}$** to decay by $50\%$:
> $$\bar{T}_{\text{holding}} \ll \tau_{1/2}$$
> **The live bot was exiting before the physical mean reversion process could even begin.** High-frequency micro-momentum carried the price forward through the stop-loss every time.

---

## 5. The Solution: Multi-Timescale Resampling & Cooldown

When Brain 3 aggregated ticks into **1.0-second candles** and enforced a **15-second cooldown** matching the lower bound of the OU half-life:

```text
Trade Count:      40 trades → 4 trades
Win Rate:         17.5%    → 75.0%
Net PnL:          -$15.38  → +$7.94
Profit Factor:    0.09     → 8.21
Max Drawdown:     $15.38   → $1.10
```

---

## 6. Related Vault Documents
- [[13-three-brain-architecture|13: Three-Brain Architecture: Microsecond Hot Path, Governor & AI]]
- [[04-mean-reversion|04: Mean Reversion Strategies & Envelope Trading]]
- [[15-live-operations-and-self-healing-runbook|15: Live Operations & Autonomous Self-Healing Runbook]]
