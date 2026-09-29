"""
Fast, Parallel Downloader for Binance Historical Klines (2019 to Present)
Source: data.binance.vision (Public AWS S3 CloudFront CDN)

Features:
- Downloads official monthly 1-minute zip archives from 2019-01 onwards.
- Multi-threaded streaming downloads with progress reporting.
- Converts to DuckDB-friendly partitioned Parquet storage (or consolidated Parquet).
- Zero rate limits, maximum throughput.
"""

import os
import sys
import glob
import time
import zipfile
import io
import csv
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import pyarrow as pa
import pyarrow.parquet as pq

SYMBOL = "BTCUSDT"
START_YEAR = 2019
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "historical"))
os.makedirs(BASE_DIR, exist_ok=True)
PARQUET_OUT_DIR = os.path.join(BASE_DIR, "klines_1m_monthly")
os.makedirs(PARQUET_OUT_DIR, exist_ok=True)

KLINE_SCHEMA = pa.schema([
    ("timestamp", pa.int64()),  # Unix timestamp in seconds
    ("open", pa.float64()),
    ("high", pa.float64()),
    ("low", pa.float64()),
    ("close", pa.float64()),
    ("volume", pa.float64()),
    ("close_time", pa.int64()),
    ("quote_volume", pa.float64()),
    ("count", pa.int64()),
    ("taker_buy_volume", pa.float64()),
    ("taker_buy_quote_volume", pa.float64()),
])

def generate_month_list(start_year=2019):
    months = []
    now = datetime.datetime.now()
    cur_year = now.year
    cur_month = now.month
    
    for y in range(start_year, cur_year + 1):
        end_m = 12 if y < cur_year else cur_month - 1
        for m in range(1, end_m + 1):
            months.append(f"{y}-{m:02d}")
    return months

def download_and_convert_month(month_str):
    out_parquet = os.path.join(PARQUET_OUT_DIR, f"{SYMBOL}-1m-{month_str}.parquet")
    if os.path.exists(out_parquet) and os.path.getsize(out_parquet) > 100_000:
        return f"[SKIP] {month_str} already exists."
    
    url = f"https://data.binance.vision/data/spot/monthly/klines/{SYMBOL}/1m/{SYMBOL}-1m-{month_str}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        return f"[404] {month_str} not available ({e.code})"
    except Exception as e:
        return f"[ERR] {month_str} download failed: {e}"
        
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for fname in z.namelist():
                if fname.endswith(".csv"):
                    with z.open(fname) as f:
                        lines = io.TextIOWrapper(f, encoding="utf-8")
                        reader = csv.reader(lines)
                        
                        ts_list = []
                        o_list = []
                        h_list = []
                        l_list = []
                        c_list = []
                        v_list = []
                        ct_list = []
                        qv_list = []
                        cnt_list = []
                        tbv_list = []
                        tbqv_list = []
                        
                        for row in reader:
                            if not row or not row[0].isdigit():
                                continue
                            try:
                                ts_list.append(int(int(row[0]) // 1000))
                                o_list.append(float(row[1]))
                                h_list.append(float(row[2]))
                                l_list.append(float(row[3]))
                                c_list.append(float(row[4]))
                                v_list.append(float(row[5]))
                                ct_list.append(int(int(row[6]) // 1000))
                                qv_list.append(float(row[7]))
                                cnt_list.append(int(row[8]))
                                tbv_list.append(float(row[9]))
                                tbqv_list.append(float(row[10]))
                            except (ValueError, IndexError):
                                continue
                                
                        table = pa.Table.from_arrays([
                            pa.array(ts_list, type=pa.int64()),
                            pa.array(o_list, type=pa.float64()),
                            pa.array(h_list, type=pa.float64()),
                            pa.array(l_list, type=pa.float64()),
                            pa.array(c_list, type=pa.float64()),
                            pa.array(v_list, type=pa.float64()),
                            pa.array(ct_list, type=pa.int64()),
                            pa.array(qv_list, type=pa.float64()),
                            pa.array(cnt_list, type=pa.int64()),
                            pa.array(tbv_list, type=pa.float64()),
                            pa.array(tbqv_list, type=pa.float64()),
                        ], schema=KLINE_SCHEMA)
                        
                        pq.write_table(table, out_parquet, compression="zstd")
                        return f"[DONE] {month_str}: {len(ts_list):,} bars saved to Parquet ({os.path.getsize(out_parquet)/1024:.1f} KB)"
    except Exception as e:
        return f"[ERR] {month_str} parsing failed: {e}"

def main():
    months = generate_month_list(START_YEAR)
    print("=" * 80)
    print(f" BINANCE BULK HISTORICAL ARCHIVE INGESTION")
    print(f" Target: {SYMBOL} 1m Klines from {START_YEAR}-01 to {months[-1]}")
    print(f" Total Months Scheduled: {len(months)}")
    print(f" Output Directory: {PARQUET_OUT_DIR}")
    print("=" * 80)
    
    t0 = time.time()
    completed = 0
    # Use 8 worker threads for fast parallel download
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(download_and_convert_month, m): m for m in months}
        for future in as_completed(futures):
            month = futures[future]
            res = future.result()
            completed += 1
            print(f"[{completed}/{len(months)}] {res}")
            
    elapsed = time.time() - t0
    print("=" * 80)
    print(f"ALL HISTORICAL ARCHIVE INGESTION COMPLETED IN {elapsed:.1f}s")
    print("=" * 80)

if __name__ == "__main__":
    main()
