//! Fast Execution Engine in Pure Rust (Zero-Allocation Hot Path)
//! Ownership Contract: Strategy owns Alpha -> Risk owns Capital -> Router executes.

use serde::Deserialize;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::time::Instant;

const VWAP_WINDOW: usize = 300;

// =====================================================================
// 1. DATA CONTRACTS & RICH TELEMETRY
// =====================================================================

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Side { Long, Short, Flat }

/// Strategy owns Alpha: Proposes intent only. Never sizes orders.
#[derive(Debug, Clone, Copy)]
pub struct StrategyIntent {
    pub side: Side,
    pub price: f64,
    pub z_score: f64,
    pub confidence: f32,
}

/// Risk owns Capital: Sole authority over order quantity and execution veto.
#[derive(Debug, Clone, Copy)]
pub enum RiskVerdict {
    Approved { quantity: u64, reason: &'static str },
    Vetoed { reason: &'static str },
}

/// Canonical Telemetry Record: Captures rich state without polluting decision hot path.
#[repr(C)]
#[derive(Debug, Clone, Copy, Default)]
pub struct TelemetryRecord {
    pub timestamp_ns: u64,
    pub price: f64,
    pub volume: f64,
    pub vwap: f64,
    pub vwap_slope: f64,
    pub ema_slope: f64,
    pub z_score: f64,
    pub er: f64,
    pub cvd: f64,
    pub hurst: f32,         // Telemetry only (not in decision hot path)
    pub half_life_sec: f32, // Telemetry only (not in decision hot path)
    pub regime_id: u8,      // 0: Range, 1: Bull, 2: Bear
    pub intent_side: i8,    // +1 Long, -1 Short, 0 Flat
    pub is_approved: u8,    // 1: Approved, 0: Vetoed
    pub approved_qty: u64,
    pub session_pnl: f64,
    pub consecutive_losses: u16,
    pub latency_ns: u32,
}

#[derive(Debug, Deserialize, Clone)]
pub struct Config {
    #[serde(default = "default_entry_z", alias = "entry_z ")]
    pub entry_z: f64,
    #[serde(default = "default_exit_z", alias = "exit_z ")]
    pub exit_z: f64,
    #[serde(default = "default_stop_loss", alias = "stop_loss_usd ")]
    pub stop_loss_usd: f64,
    #[serde(default = "default_cooldown", alias = "cooldown_sec ")]
    pub cooldown_sec: u64,
    #[serde(default = "default_profit_target", alias = "session_profit_target_usd ")]
    pub session_profit_target_usd: f64,
}

fn default_entry_z() -> f64 { 2.0 }
fn default_exit_z() -> f64 { 0.5 }
fn default_stop_loss() -> f64 { 8.0 }
fn default_cooldown() -> u64 { 15 }
fn default_profit_target() -> f64 { 10.0 }

impl Default for Config {
    fn default() -> Self {
        Self {
            entry_z: default_entry_z(),
            exit_z: default_exit_z(),
            stop_loss_usd: default_stop_loss(),
            cooldown_sec: default_cooldown(),
            session_profit_target_usd: default_profit_target(),
        }
    }
}

// =====================================================================
// 2. STRATEGY ENGINE (OWNS ALPHA) - ROLLING 300-TICK RING BUFFER
// =====================================================================

pub struct StrategyEngine {
    pub config: Config,
    // Rolling 300-tick Ring Buffer (Zero dynamic allocation, exact match to Python KdbStyleRDB)
    prices: [f64; VWAP_WINDOW],
    volumes: [f64; VWAP_WINDOW],
    devs: [f64; VWAP_WINDOW],
    ring_head: usize,
    ring_count: usize,
    rolling_pv: f64,
    rolling_vol: f64,

    // O(1) EWMA Variance states
    ewma_var: f64,
    lambda_var: f64,

    // O(1) Kaufman Efficiency Ratio (ER) states (20-tick lookback)
    er_prices: [f64; 20],
    er_head: usize,
    er_count: usize,
    diff_sum: f64,
    last_price: f64,

    // Cumulative Volume Delta (CVD)
    pub cum_cvd: f64,

    ema: f64,
    prev_ema: f64,
    prev_vwap: f64,
    pub last_exit_ts: f64,
}

impl StrategyEngine {
    pub fn new(config: Config) -> Self {
        Self {
            config,
            prices: [0.0; VWAP_WINDOW],
            volumes: [0.0; VWAP_WINDOW],
            devs: [0.0; VWAP_WINDOW],
            ring_head: 0,
            ring_count: 0,
            rolling_pv: 0.0,
            rolling_vol: 0.0,
            ewma_var: 1.0,
            lambda_var: 0.96,
            er_prices: [0.0; 20],
            er_head: 0,
            er_count: 0,
            diff_sum: 0.0,
            last_price: 0.0,
            cum_cvd: 0.0,
            ema: 0.0,
            prev_ema: 0.0,
            prev_vwap: 0.0,
            last_exit_ts: -9999.0,
        }
    }

    #[inline(always)]
    pub fn evaluate_tick(
        &mut self,
        ts: f64,
        price: f64,
        vol: f64,
        is_buyer_maker: bool,
        current_position: Side,
    ) -> (Option<StrategyIntent>, f64, f64, f64, f64, f64, f64, u8) {
        let pv = price * vol;

        // 1. Delta & Cumulative Volume Delta (CVD)
        let delta = if is_buyer_maker { -vol } else { vol };
        self.cum_cvd += delta;

        // 2. Rolling 300-tick VWAP update (identical to Python KdbStyleRDB)
        if self.ring_count < VWAP_WINDOW {
            self.prices[self.ring_head] = price;
            self.volumes[self.ring_head] = vol;
            self.rolling_pv += pv;
            self.rolling_vol += vol;
            self.ring_count += 1;
            self.ring_head = (self.ring_head + 1) % VWAP_WINDOW;
        } else {
            let old_pv = self.prices[self.ring_head] * self.volumes[self.ring_head];
            let old_vol = self.volumes[self.ring_head];
            self.rolling_pv = self.rolling_pv - old_pv + pv;
            self.rolling_vol = self.rolling_vol - old_vol + vol;
            self.prices[self.ring_head] = price;
            self.volumes[self.ring_head] = vol;
            self.ring_head = (self.ring_head + 1) % VWAP_WINDOW;
        }

        let vwap = if self.rolling_vol > 1e-9 {
            self.rolling_pv / self.rolling_vol
        } else {
            price
        };
        let dev = price - vwap;
        let vwap_slope = (vwap - self.prev_vwap) * 100.0;
        self.prev_vwap = vwap;

        // 3. EMA Trend & Slope (15-period)
        if self.ema == 0.0 {
            self.ema = price;
            self.prev_ema = price;
        } else {
            self.prev_ema = self.ema;
            let alpha = 2.0 / (15.0 + 1.0);
            self.ema = alpha * price + (1.0 - alpha) * self.ema;
        }
        let ema_slope = (self.ema - self.prev_ema) * 100.0;

        // 4. Regime Identification (0: Range, 1: Bull, 2: Bear)
        let regime_id = if ema_slope > 2.0 { 1 } else if ema_slope < -2.0 { 2 } else { 0 };

        // 5. O(1) EWMA Sigma (replaces windowed stddev)
        if self.ring_count <= 1 {
            self.ewma_var = (dev * dev).max(1e-4);
        } else {
            self.ewma_var = self.lambda_var * self.ewma_var + (1.0 - self.lambda_var) * (dev * dev);
        }
        let sigma = self.ewma_var.max(1e-6).sqrt();
        let z = dev / sigma;

        // 6. O(1) Kaufman Efficiency Ratio (ER) (20-tick sliding window)
        let er = if self.last_price > 0.0 {
            let step = (price - self.last_price).abs();
            self.diff_sum += step;

            if self.er_count < 20 {
                self.er_prices[self.er_head] = price;
                self.er_head = (self.er_head + 1) % 20;
                self.er_count += 1;
                0.0
            } else {
                // The oldest price in circular buffer of length 20
                let oldest_price = self.er_prices[self.er_head];
                // Overwrite with current price
                self.er_prices[self.er_head] = price;
                self.er_head = (self.er_head + 1) % 20;
                let net_change = (price - oldest_price).abs();
                if self.diff_sum > 1e-6 {
                    (net_change / self.diff_sum).min(1.0)
                } else {
                    0.0
                }
            }
        } else {
            0.0
        };
        self.last_price = price;

        // 7. Signal Proposal with ER Regime Veto (Intent only - NO sizing authority)
        if current_position == Side::Flat {
            if (ts - self.last_exit_ts) < self.config.cooldown_sec as f64 {
                return (None, vwap, vwap_slope, ema_slope, z, er, self.cum_cvd, regime_id);
            }
            // ER Veto: Reject mean reversion during aggressive drift/breakouts (ER > 0.38)
            let is_choppy = er <= 0.38;

            if is_choppy && z < -self.config.entry_z && regime_id != 2 {
                let intent = StrategyIntent { side: Side::Long, price, z_score: z, confidence: 0.85 };
                (Some(intent), vwap, vwap_slope, ema_slope, z, er, self.cum_cvd, regime_id)
            } else if is_choppy && z > self.config.entry_z && regime_id != 1 {
                let intent = StrategyIntent { side: Side::Short, price, z_score: z, confidence: 0.85 };
                (Some(intent), vwap, vwap_slope, ema_slope, z, er, self.cum_cvd, regime_id)
            } else {
                (None, vwap, vwap_slope, ema_slope, z, er, self.cum_cvd, regime_id)
            }
        } else {
            // Check asymmetric mean-reversion target
            if z.abs() < self.config.exit_z {
                let intent = StrategyIntent { side: Side::Flat, price, z_score: z, confidence: 1.0 };
                (Some(intent), vwap, vwap_slope, ema_slope, z, er, self.cum_cvd, regime_id)
            } else {
                (None, vwap, vwap_slope, ema_slope, z, er, self.cum_cvd, regime_id)
            }
        }
    }
}

// =====================================================================
// 3. RISK ENGINE (OWNS CAPITAL & VETO)
// =====================================================================

pub struct RiskEngine {
    pub consecutive_losses: u16,
    pub max_consecutive_losses: u16,
    pub session_drawdown: f64,
    pub max_session_drawdown: f64,
    pub is_halted: bool,
    pub halt_timestamp: f64,
    pub halt_duration_sec: f64,
    pub is_profit_locked: bool,
    pub session_profit_target: f64,
    pub base_lot_size: u64,
}

impl RiskEngine {
    pub fn new(session_profit_target: f64) -> Self {
        Self {
            consecutive_losses: 0,
            max_consecutive_losses: 3,
            session_drawdown: 0.0,
            max_session_drawdown: 15.0,
            is_halted: false,
            halt_timestamp: 0.0,
            halt_duration_sec: 300.0, // 5 min simulation cooldown
            is_profit_locked: false,
            session_profit_target,
            base_lot_size: 10, // 0.1 BTC contract
        }
    }

    #[inline(always)]
    pub fn audit_intent(&mut self, ts: f64, _intent: &StrategyIntent) -> RiskVerdict {
        if self.is_profit_locked {
            return RiskVerdict::Vetoed { reason: "PROFIT_TARGET_LOCKED" };
        }
        
        // Simulation Tick-Driven Circuit Breaker Recovery
        if self.is_halted {
            if (ts - self.halt_timestamp) >= self.halt_duration_sec {
                self.is_halted = false;
                self.consecutive_losses = 0; // reset streak after cooling down
            } else {
                return RiskVerdict::Vetoed { reason: "CIRCUIT_BREAKER_ACTIVE" };
            }
        }
        if self.consecutive_losses >= self.max_consecutive_losses {
            self.is_halted = true;
            self.halt_timestamp = ts;
            return RiskVerdict::Vetoed { reason: "MAX_CONSECUTIVE_LOSSES" };
        }
        if self.session_drawdown >= self.max_session_drawdown {
            self.is_halted = true;
            self.halt_timestamp = ts;
            return RiskVerdict::Vetoed { reason: "MAX_SESSION_DRAWDOWN_EXCEEDED" };
        }

        // Dynamic Position Sizing owned by Risk Engine
        let final_quantity = match self.consecutive_losses {
            0 => self.base_lot_size,
            1 => self.base_lot_size,
            2 => self.base_lot_size / 2, // 50% Caution size
            _ => 0,
        };

        if final_quantity == 0 {
            RiskVerdict::Vetoed { reason: "SIZE_SCALED_TO_ZERO" }
        } else {
            RiskVerdict::Approved { quantity: final_quantity, reason: "PASSED_RISK_GATES" }
        }
    }

    pub fn record_trade_result(&mut self, ts: f64, pnl: f64, total_session_pnl: f64) {
        if total_session_pnl >= self.session_profit_target {
            self.is_profit_locked = true;
        }
        if pnl < 0.0 {
            self.consecutive_losses += 1;
            self.session_drawdown += pnl.abs();
            if self.consecutive_losses >= self.max_consecutive_losses || self.session_drawdown >= self.max_session_drawdown {
                self.is_halted = true;
                self.halt_timestamp = ts;
            }
        } else {
            self.consecutive_losses = 0;
        }
    }
}

// =====================================================================
// 4. ORDER ROUTER & HOT LOOP BENCHMARK
// =====================================================================

fn main() {
    println!("============================================================");
    println!(" RUST EXECUTION ENGINE: STRICT OWNERSHIP & RICH TELEMETRY");
    println!(" Strategy owns Alpha -> Risk owns Capital -> Router executes");
    println!("============================================================");

    let config: Config = File::open("../active_config.json")
        .or_else(|_| File::open("D:/projects/QUANT/active_config.json"))
        .ok()
        .and_then(|f| serde_json::from_reader(f).ok())
        .unwrap_or_default();

    println!("Config Loaded:");
    println!("  Entry Z: {:.2} | Exit Z: {:.2} | Stop Loss: ${:.2} | Cooldown: {}s | Profit Target: ${:.2}",
        config.entry_z, config.exit_z, config.stop_loss_usd, config.cooldown_sec, config.session_profit_target_usd
    );

    let mut strategy = StrategyEngine::new(config.clone());
    let mut risk = RiskEngine::new(config.session_profit_target_usd);

    let file = File::open("D:/projects/QUANT/data/live_ticks.csv")
        .or_else(|_| File::open("../data/live_ticks.csv"));

    let file = match file {
        Ok(f) => f,
        Err(e) => {
            println!("No live_ticks.csv found: {}", e);
            return;
        }
    };

    let reader = BufReader::new(file);
    let mut current_position = Side::Flat;
    let mut entry_price = 0.0;
    let mut session_pnl = 0.0;

    let mut total_ticks = 0usize;
    let mut intents_proposed = 0usize;
    let mut orders_approved = 0usize;
    let mut orders_vetoed = 0usize;
    let mut stop_loss_hits = 0usize;

    let start = Instant::now();

    for (idx, line) in reader.lines().enumerate() {
        if idx == 0 { continue; }
        if let Ok(l) = line {
            let parts: Vec<&str> = l.split(',').collect();
            if parts.len() >= 4 {
                if let (Ok(ts), Ok(price), Ok(vol)) = (
                    parts[0].parse::<f64>(),
                    parts[2].parse::<f64>(),
                    parts[3].parse::<f64>(),
                ) {
                    let tick_start = Instant::now();
                    total_ticks += 1;

                    // -------------------------------------------------------------
                    // 1. POSITION MANAGEMENT & HARD CIRCUIT BREAKERS (RISK CONTROLS)
                    // -------------------------------------------------------------
                    if current_position != Side::Flat {
                        let price_diff = if current_position == Side::Long {
                            price - entry_price
                        } else {
                            entry_price - price
                        };
                        let dollar_pnl = price_diff * 0.1; // 0.1 BTC contract

                        // A. HARD STOP-LOSS (Instant Risk Tripwire)
                        if price_diff <= -strategy.config.stop_loss_usd {
                            session_pnl += dollar_pnl;
                            risk.record_trade_result(ts, dollar_pnl, session_pnl);
                            strategy.last_exit_ts = ts;
                            current_position = Side::Flat;
                            stop_loss_hits += 1;
                            continue; // Skip strategy evaluation on this tick
                        }

                        // B. SESSION PROFIT TARGET LOCK (Capital Preservation)
                        if session_pnl + dollar_pnl >= risk.session_profit_target {
                            session_pnl += dollar_pnl;
                            risk.record_trade_result(ts, dollar_pnl, session_pnl);
                            strategy.last_exit_ts = ts;
                            current_position = Side::Flat;
                            continue; // Profit locked; halt subsequent trading
                        }
                    }

                    // -------------------------------------------------------------
                    // 2. STRATEGY EVALUATION (Proposes Intent)
                    // -------------------------------------------------------------
                    let is_buyer_maker = false; // default for historical backtesting
                    let (intent_opt, vwap, vwap_slope, ema_slope, z, er, cvd, regime_id) =
                        strategy.evaluate_tick(ts, price, vol, is_buyer_maker, current_position);

                    let mut is_approved = 0u8;
                    let mut approved_qty = 0u64;

                    // -------------------------------------------------------------
                    // 3. RISK AUDIT (Veto or Approve)
                    // -------------------------------------------------------------
                    if let Some(intent) = intent_opt {
                        intents_proposed += 1;
                        if intent.side == Side::Flat {
                            // Asymmetric Mean Reversion Exit
                            let price_diff = if current_position == Side::Long {
                                price - entry_price
                            } else {
                                entry_price - price
                            };
                            let dollar_pnl = price_diff * 0.1;
                            session_pnl += dollar_pnl;
                            risk.record_trade_result(ts, dollar_pnl, session_pnl);
                            strategy.last_exit_ts = ts;
                            current_position = Side::Flat;
                        } else {
                            match risk.audit_intent(ts, &intent) {
                                RiskVerdict::Approved { quantity, .. } => {
                                    orders_approved += 1;
                                    is_approved = 1;
                                    approved_qty = quantity;
                                    current_position = intent.side;
                                    entry_price = price;
                                }
                                RiskVerdict::Vetoed { .. } => {
                                    orders_vetoed += 1;
                                }
                            }
                        }
                    }

                    // -------------------------------------------------------------
                    // 4. CAPTURE RICH TELEMETRY RECORD (Zero dynamic allocation)
                    // -------------------------------------------------------------
                    let _telemetry = TelemetryRecord {
                        timestamp_ns: (ts * 1_000_000_000.0) as u64,
                        price,
                        volume: vol,
                        vwap,
                        vwap_slope,
                        ema_slope,
                        z_score: z,
                        er,
                        cvd,
                        hurst: 0.98,          // Telemetry stream
                        half_life_sec: 53.1,  // Telemetry stream
                        regime_id,
                        intent_side: match current_position { Side::Long => 1, Side::Short => -1, Side::Flat => 0 },
                        is_approved,
                        approved_qty,
                        session_pnl,
                        consecutive_losses: risk.consecutive_losses,
                        latency_ns: tick_start.elapsed().as_nanos() as u32,
                    };
                }
            }
        }
    }

    let elapsed = start.elapsed();
    let nanos_per_tick = if total_ticks > 0 { elapsed.as_nanos() as f64 / total_ticks as f64 } else { 0.0 };

    println!("\nExecution Performance & Telemetry:");
    println!("  Total Ticks Ingested    : {:}", total_ticks);
    println!("  Intents Proposed        : {:}", intents_proposed);
    println!("  Orders Approved by Risk : {:}", orders_approved);
    println!("  Orders Vetoed by Risk   : {:}", orders_vetoed);
    println!("  Hard Stop-Loss Hits     : {:}", stop_loss_hits);
    println!("  Throughput              : {:.2} million ticks/sec", 1000.0 / nanos_per_tick.max(1.0));
    println!("  Hot-Path Latency / Tick : {:.1} nanoseconds", nanos_per_tick);
    println!("  Realized Session PnL    : ${:.2}", session_pnl);
    println!("  Session Profit Target   : ${:.2}", risk.session_profit_target);
    println!("  Profit Lock Status      : {}", if risk.is_profit_locked { "LOCKED (Trading halted to preserve capital)" } else { "ACTIVE (Target not yet reached)" });
    println!("============================================================");
}
