"""
High-Frequency Binance Microstructure Logger: bookTicker + aggTrade
Streams:
- btcusdt@bookTicker (best bid/ask price + qty, exchange time E)
- btcusdt@aggTrade   (trade price, qty, maker flag m, trade ID a, exchange time T)

Features:
- Dual-stream WebSocket multiplexer via combined stream endpoint
- Records local receive timestamp: time.time_ns()
- Aggregates in memory buffer
- Rotates to hourly Parquet files with ZSTD compression
- Tracks sequence gaps and websocket reconnect with exponential backoff + jitter
"""

import os
import sys
import time
import orjson
import asyncio
import random
import datetime
import websockets
import pyarrow as pa
import pyarrow.parquet as pq

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "microstructure"))
os.makedirs(DATA_DIR, exist_ok=True)

SYMBOL = "btcusdt"
WS_COMBINED_URL = f"wss://stream.binance.com:9443/stream?streams={SYMBOL}@bookTicker/{SYMBOL}@aggTrade"

# Schemas for Parquet storage
BOOK_TICKER_SCHEMA = pa.schema([
    ("local_recv_ns", pa.int64()),
    ("event_time_ms", pa.int64()),
    ("update_id", pa.int64()),
    ("bid_price", pa.float64()),
    ("bid_qty", pa.float64()),
    ("ask_price", pa.float64()),
    ("ask_qty", pa.float64()),
])

AGG_TRADE_SCHEMA = pa.schema([
    ("local_recv_ns", pa.int64()),
    ("event_time_ms", pa.int64()),
    ("trade_time_ms", pa.int64()),
    ("agg_trade_id", pa.int64()),
    ("price", pa.float64()),
    ("quantity", pa.float64()),
    ("is_buyer_maker", pa.bool_()),
])

def _write_parquet_chunk(table, filepath):
    pq.write_table(table, filepath, compression="zstd")

class MicrostructureLogger:
    def __init__(self, flush_interval_sec: float = 30.0):
        self.flush_interval = flush_interval_sec
        # Columnar lists for zero dict-allocation overhead
        self.reset_buffers()
        self.last_agg_trade_id = None
        self.gap_count = 0
        self.total_book_records = 0
        self.total_trade_records = 0

    def reset_buffers(self):
        self.b_recv_ns, self.b_event_ms, self.b_update_id = [], [], []
        self.b_bid_p, self.b_bid_q, self.b_ask_p, self.b_ask_q = [], [], [], []
        self.t_recv_ns, self.t_event_ms, self.t_trade_ms = [], [], []
        self.t_agg_id, self.t_p, self.t_q, self.t_maker = [], [], [], []

    async def flush(self):
        hour_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H")
        now_ts = int(time.time())
        
        # Flush bookTicker in worker thread so event loop never blocks
        if self.b_recv_ns:
            chunk_file = os.path.join(DATA_DIR, f"book_{SYMBOL}_{hour_str}_{now_ts}.parquet")
            table = pa.Table.from_arrays([
                pa.array(self.b_recv_ns, type=pa.int64()),
                pa.array(self.b_event_ms, type=pa.int64()),
                pa.array(self.b_update_id, type=pa.int64()),
                pa.array(self.b_bid_p, type=pa.float64()),
                pa.array(self.b_bid_q, type=pa.float64()),
                pa.array(self.b_ask_p, type=pa.float64()),
                pa.array(self.b_ask_q, type=pa.float64()),
            ], schema=BOOK_TICKER_SCHEMA)
            self.total_book_records += len(self.b_recv_ns)
            asyncio.create_task(asyncio.to_thread(_write_parquet_chunk, table, chunk_file))

        # Flush aggTrade in worker thread
        if self.t_recv_ns:
            chunk_file = os.path.join(DATA_DIR, f"trade_{SYMBOL}_{hour_str}_{now_ts}.parquet")
            table = pa.Table.from_arrays([
                pa.array(self.t_recv_ns, type=pa.int64()),
                pa.array(self.t_event_ms, type=pa.int64()),
                pa.array(self.t_trade_ms, type=pa.int64()),
                pa.array(self.t_agg_id, type=pa.int64()),
                pa.array(self.t_p, type=pa.float64()),
                pa.array(self.t_q, type=pa.float64()),
                pa.array(self.t_maker, type=pa.bool_()),
            ], schema=AGG_TRADE_SCHEMA)
            self.total_trade_records += len(self.t_recv_ns)
            asyncio.create_task(asyncio.to_thread(_write_parquet_chunk, table, chunk_file))

        self.reset_buffers()

    async def run(self):
        print("=" * 80)
        print(" BINANCE MICROSTRUCTURE LOGGER (bookTicker + aggTrade)")
        print(f" Target Dir: {DATA_DIR} | Compression: ZSTD (Hourly Rotation)")
        print("=" * 80)
        
        delay = 1.0
        last_flush_t = time.time()
        
        while True:
            try:
                print(f"[Logger] Connecting to {WS_COMBINED_URL}...")
                async with websockets.connect(WS_COMBINED_URL, ping_interval=20, ping_timeout=10) as ws:
                    print("[Logger] Connected successfully! Streaming order-book & trades...")
                    delay = 1.0
                    
                    while True:
                        msg = await ws.recv()
                        local_ns = time.time_ns()
                        data_wrap = orjson.loads(msg)
                        stream_name = data_wrap.get("stream", "")
                        data = data_wrap.get("data", {})
                        
                        if "bookTicker" in stream_name:
                            self.b_recv_ns.append(local_ns)
                            self.b_event_ms.append(int(data.get("E", 0)))
                            self.b_update_id.append(int(data.get("u", 0)))
                            self.b_bid_p.append(float(data.get("b", 0.0)))
                            self.b_bid_q.append(float(data.get("B", 0.0)))
                            self.b_ask_p.append(float(data.get("a", 0.0)))
                            self.b_ask_q.append(float(data.get("A", 0.0)))
                            
                        elif "aggTrade" in stream_name:
                            agg_id = int(data.get("a", 0))
                            if self.last_agg_trade_id is not None and agg_id != self.last_agg_trade_id + 1:
                                self.gap_count += 1
                                print(f"[Logger Warning] AggTrade sequence gap: Expected {self.last_agg_trade_id + 1}, got {agg_id} (Total gaps: {self.gap_count})")
                            self.last_agg_trade_id = agg_id
                            
                            self.t_recv_ns.append(local_ns)
                            self.t_event_ms.append(int(data.get("E", 0)))
                            self.t_trade_ms.append(int(data.get("T", 0)))
                            self.t_agg_id.append(agg_id)
                            self.t_p.append(float(data.get("p", 0.0)))
                            self.t_q.append(float(data.get("q", 0.0)))
                            self.t_maker.append(bool(data.get("m", False)))
                            
                        # Periodic flush check
                        now = time.time()
                        if now - last_flush_t >= self.flush_interval:
                            await self.flush()
                            last_flush_t = now
                            print(f"[Logger Status] Ingested: {self.total_book_records:,} quotes | {self.total_trade_records:,} trades | Buffer: {len(self.b_recv_ns)}/{len(self.t_recv_ns)}")
                            
            except Exception as e:
                print(f"[Logger Error] Disconnected: {e}")
                await self.flush()
                sleep_time = delay + random.random()
                print(f"[Logger] Reconnecting in {sleep_time:.1f}s...")
                await asyncio.sleep(sleep_time)
                delay = min(delay * 2.0, 30.0)

if __name__ == "__main__":
    logger = MicrostructureLogger(flush_interval_sec=15.0)
    try:
        asyncio.run(logger.run())
    except KeyboardInterrupt:
        print("[Logger] Shutting down...")
        asyncio.run(logger.flush())
