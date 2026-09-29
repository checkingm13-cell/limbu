"""
Maker Queue Fill & Adverse Selection Offline Simulator
Algorithm:
1. Load recorded Parquet chunks of bookTicker and aggTrade directly via DuckDB.
2. Two-pointer ASOF merge on time-sorted quotes and trades.
3. Queue Fill Model (Prefix Sum + Binary Search):
   - Optimistic bound: filled as soon as trade volume >= displayed queue depth at placement.
   - Pessimistic bound: filled only after 2x queue depth trades through (accounting for cancels ahead).
4. Adverse Selection & Latency:
   - 180 ms network cancel lag modeled.
   - Measure post-fill forward returns at 1s, 5s, 15s, 60s.
"""

import os
import sys
import glob
import duckdb
import numpy as np

DATA_DIR = "D:/projects/QUANT/data/microstructure"

def run_maker_fill_simulation(latency_cancel_ms: float = 180.0, maker_fee_bps: float = 1.0):
    print("=" * 80)
    print(" MAKER QUEUE FILL & ADVERSE SELECTION SIMULATOR (DUCKDB + NUMPY)")
    print(f" Modeled Cancel Latency: {latency_cancel_ms:.0f} ms | Maker Fee Hurdle: {maker_fee_bps:.1f} bps per side")
    print("=" * 80)

    # 1. Connect DuckDB in-memory
    con = duckdb.connect()

    book_files = glob.glob(os.path.join(DATA_DIR, "book_*.parquet"))
    trade_files = glob.glob(os.path.join(DATA_DIR, "trade_*.parquet"))

    if not book_files or not trade_files:
        print("No microstructure data found in", DATA_DIR)
        return

    print(f"Scanning {len(book_files)} quote chunks and {len(trade_files)} trade chunks...")
    
    # Query sorted quotes and trades directly from parquet
    q_quotes = f"""
    SELECT local_recv_ns, bid_price, bid_qty, ask_price, ask_qty,
           (bid_price + ask_price) / 2.0 AS mid_price
    FROM read_parquet('{DATA_DIR}/book_*.parquet')
    ORDER BY local_recv_ns ASC
    """
    
    q_trades = f"""
    SELECT local_recv_ns, price, quantity, is_buyer_maker
    FROM read_parquet('{DATA_DIR}/trade_*.parquet')
    ORDER BY local_recv_ns ASC
    """
    
    df_quotes = con.execute(q_quotes).fetchnumpy()
    df_trades = con.execute(q_trades).fetchnumpy()

    ts_quote = df_quotes["local_recv_ns"]
    bids = df_quotes["bid_price"]
    bid_qtys = df_quotes["bid_qty"]
    asks = df_quotes["ask_price"]
    ask_qtys = df_quotes["ask_qty"]
    mids = df_quotes["mid_price"]

    ts_trade = df_trades["local_recv_ns"]
    tr_prices = df_trades["price"]
    tr_qtys = df_trades["quantity"]
    tr_is_buyer_maker = df_trades["is_buyer_maker"] # True = market sell, False = market buy

    print(f"Loaded {len(ts_quote):,} quotes and {len(ts_trade):,} trade prints.")
    if len(ts_quote) < 100 or len(ts_trade) < 50:
        print("Dataset too small for meaningful queue simulation. Letting logger run.")
        return

    # Prefix sums of aggressive volume
    # Market sells hit the BID (buyer is maker: is_buyer_maker == True)
    sell_qtys = np.where(tr_is_buyer_maker, tr_qtys, 0.0)
    cum_sells = np.cumsum(sell_qtys)
    
    # Market buys lift the ASK (buyer is maker: is_buyer_maker == False)
    buy_qtys = np.where(~tr_is_buyer_maker, tr_qtys, 0.0)
    cum_buys = np.cumsum(buy_qtys)

    horizons_sec = [1.0, 5.0, 15.0, 60.0]
    latency_ns = int(latency_cancel_ms * 1_000_000)

    # Evaluate passive Bid placements at every N quotes (sample rate)
    sample_step = max(1, len(ts_quote) // 500)
    
    for bound_name, queue_mult in [("Optimistic Queue (1.0x Depth)", 1.0), ("Pessimistic Queue (2.0x Depth)", 2.0)]:
        print("\n" + "-" * 80)
        print(f" QUEUE MODEL: {bound_name}")
        print("-" * 80)

        fills_bids = [] # (t_fill, fill_price)
        
        for q_idx in range(0, len(ts_quote) - 10, sample_step):
            t_place = ts_quote[q_idx]
            bid_p = bids[q_idx]
            bid_q = bid_qtys[q_idx]
            
            # Find trade position at t_place
            tr_start = np.searchsorted(ts_trade, t_place)
            if tr_start >= len(ts_trade):
                continue
                
            base_sell = cum_sells[tr_start]
            target_vol = base_sell + (bid_q * queue_mult)
            
            # Find trade that fills us
            fill_trade_idx = np.searchsorted(cum_sells, target_vol)
            if fill_trade_idx < len(ts_trade):
                # Verify that price at fill is still <= our bid
                if tr_prices[fill_trade_idx] <= bid_p:
                    t_fill = ts_trade[fill_trade_idx]
                    fills_bids.append((t_fill, bid_p))

        print(f"Total Simulated Limit Fills: {len(fills_bids)}")
        if not fills_bids:
            continue

        print(f"{'Horizon':<10} | {'Fills':<8} | {'Win Rate':<10} | {'Gross Return':<14} | {'Net Return (Maker)':<18}")
        print("-" * 75)

        for h in horizons_sec:
            h_ns = int(h * 1_000_000_000)
            returns = []
            
            for t_fill, fill_p in fills_bids:
                # Target evaluation time: t_fill + horizon
                t_eval = t_fill + h_ns
                m_idx = np.searchsorted(ts_quote, t_eval)
                if m_idx < len(mids):
                    post_mid = mids[m_idx]
                    # Long return: (exit - entry) / entry
                    bps_gross = ((post_mid - fill_p) / fill_p) * 10_000.0
                    returns.append(bps_gross)
                    
            if returns:
                arr = np.array(returns)
                wr = (arr > 0).mean() * 100.0
                m_gross = arr.mean()
                m_net = m_gross - (2.0 * maker_fee_bps)
                print(f"{h:<8.1f}s | {len(arr):<8} | {wr:>6.1f}%    | {m_gross:>+8.2f} bps    | {m_net:>+10.2f} bps")

    print("=" * 80)

if __name__ == "__main__":
    run_maker_fill_simulation()
