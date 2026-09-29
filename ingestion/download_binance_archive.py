"""
Download historical 1-minute Kline data from Binance Archive (data.binance.vision)
Downloads monthly / daily bulk klines for BTCUSDT without REST rate limits.
"""

import os
import sys
import urllib.request
import zipfile
import io
import csv
import datetime

DATA_DIR = "D:/projects/QUANT/data/historical"
os.makedirs(DATA_DIR, exist_ok=True)

# We will download the last completed months or recent daily klines from data.binance.vision
# Format: https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2025-01.zip
# Or daily klines for recent dates: https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM-DD.zip

def download_binance_klines(symbol="BTCUSDT", days=30):
    print("=" * 80)
    print(f" BINANCE BULK KLINE INGESTION: {symbol} (Target: ~{days} days of 1m bars)")
    print("=" * 80)
    
    today = datetime.date.today()
    all_rows = []
    
    # Check daily archives starting from yesterday backwards
    success_days = 0
    for d_offset in range(1, days + 15):
        if success_days >= days:
            break
        dt = today - datetime.timedelta(days=d_offset)
        dt_str = dt.strftime("%Y-%m-%d")
        zip_url = f"https://data.binance.vision/data/spot/daily/klines/{symbol}/1m/{symbol}-1m-{dt_str}.zip"
        
        try:
            req = urllib.request.Request(
                zip_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                zip_data = resp.read()
                with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                    for filename in z.namelist():
                        with z.open(filename) as f:
                            content = io.TextIOWrapper(f)
                            reader = csv.reader(content)
                            day_rows = []
                            for row in reader:
                                if len(row) >= 6:
                                    try:
                                        # open_time, open, high, low, close, volume
                                        open_time = float(row[0]) / 1000.0 # seconds
                                        o = float(row[1])
                                        h = float(row[2])
                                        l = float(row[3])
                                        c = float(row[4])
                                        v = float(row[5])
                                        day_rows.append([open_time, o, h, l, c, v])
                                    except ValueError:
                                        continue
                            if day_rows:
                                all_rows.extend(day_rows)
                                success_days += 1
                                print(f"  [+] Ingested {dt_str}: {len(day_rows)} bars (Total: {success_days}/{days} days)")
        except urllib.error.HTTPError as e:
            # Maybe not available yet for recent day, continue
            continue
        except Exception as e:
            print(f"  [-] Error downloading {dt_str}: {e}")
            continue

    if not all_rows:
        print("Failed to download daily archives from data.binance.vision. Trying fallback...")
        return None

    # Sort chronologically
    all_rows.sort(key=lambda x: x[0])
    
    out_file = os.path.join(DATA_DIR, f"{symbol}_1m_{success_days}d.csv")
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        writer.writerows(all_rows)

    print("-" * 80)
    print(f"SUCCESS: Saved {len(all_rows):,} continuous 1m bars across {success_days} days to:")
    print(f"-> {out_file}")
    print("=" * 80)
    return out_file

if __name__ == "__main__":
    download_binance_klines(days=35)
