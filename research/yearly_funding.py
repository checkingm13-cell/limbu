import urllib.request, json, time, datetime

# Minimal script: Fetch BTCUSDT funding history from 2021 to now and print yearly breakdown
url_base = 'https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT'
start_ms = int(datetime.datetime(2021, 1, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
now_ms = int(time.time() * 1000)

records = []
cur = start_ms
while cur < now_ms:
    u = f"{url_base}&limit=1000&startTime={cur}"
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        b = json.loads(resp.read().decode('utf-8'))
    if not b:
        break
    records.extend(b)
    last_t = b[-1]['fundingTime']
    if last_t <= cur:
        break
    cur = last_t + 1
    time.sleep(0.1)

seen = set()
clean = []
for r in records:
    ft = r['fundingTime']
    if ft not in seen:
        seen.add(ft)
        clean.append((ft, float(r['fundingRate'])))
clean.sort()

by_year = {}
for ft, rate in clean:
    yr = datetime.datetime.fromtimestamp(ft/1000, tz=datetime.timezone.utc).year
    by_year.setdefault(yr, []).append(rate)

print("=" * 80)
print(f"TOTAL INTERVALS: {len(clean):,} (Span: {datetime.datetime.fromtimestamp(clean[0][0]/1000).strftime('%Y-%m-%d')} to {datetime.datetime.fromtimestamp(clean[-1][0]/1000).strftime('%Y-%m-%d')})")
print("=" * 80)
print(f"{'Year':<6} | {'Intervals':<10} | {'Mean 8h':<12} | {'Median 8h':<12} | {'Annualized APR':<16} | {'Neg Share':<10}")
print("-" * 80)
for yr in sorted(by_year.keys()):
    rates = by_year[yr]
    n = len(rates)
    m = sum(rates) / n
    med = sorted(rates)[n//2]
    apr = m * 3 * 365 * 100.0
    neg_pct = (sum(1 for x in rates if x < 0) / n) * 100.0
    print(f"{yr:<6} | {n:<10} | {m*10000:>+6.2f} bps  | {med*10000:>+6.2f} bps  | {apr:>+12.2f}%    | {neg_pct:>8.1f}%")
print("=" * 80)
