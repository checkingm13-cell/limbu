# Module 17: Multi-Decade Macro, Global Equities & Commodity Ingestion Task

## Task Objective
Ingest continuous historical daily price series (OHLCV) across **Global Indices (1970–2026)**, **Indian Stock Markets (1996–2026)**, **Commodities (2000–2026)**, and **Macro Interest Rates (1970–2026)** into optimized columnar Parquet format for DuckDB backtesting.

---

## 1. Asset Universe & Historical Boundaries

### Category A: Global Equity Indices
| Asset Name | Symbol | Earliest Digital Inception | Coverage (Years) | Estimated Bars |
| :--- | :--- | :--- | :--- | :--- |
| **S&P 500 (US Large Cap)** | `^GSPC` | **1970-01-02** | 56.7 Years | ~14,296 |
| **NASDAQ Composite (US Tech)** | `^IXIC` | **1971-02-05** | 55.6 Years | ~14,018 |
| **Nikkei 225 (Japan)** | `^N225` | **1970-01-05** | 56.7 Years | ~14,489 |
| **FTSE 100 (UK)** | `^FTSE` | **1984-01-03** | 42.7 Years | ~10,969 |
| **Dow Jones Industrial** | `^DJI` | **1992-01-02** | 34.7 Years | ~8,736 |

### Category B: Indian Stock Market & Benchmark Indices
> **Market Microstructure Fact:** Electronic screen trading at National Stock Exchange (NSE) began in November 1994, and BSE BOLT launched in 1995. Prior data was physical paper trade slips.
| Asset Name | Symbol | Earliest Digital Inception | Coverage (Years) | Estimated Bars |
| :--- | :--- | :--- | :--- | :--- |
| **BSE Sensex** | `^BSESN` | **1997-07-01** | ~29.2 Years | ~7,326 |
| **Nifty 50** | `^NSEI` | **2007-09-17** | ~19.0 Years | ~4,694 |
| **Bank Nifty** | `^NSEBANK` | **2007-09-17** | ~19.0 Years | ~4,694 |
| **Reliance Industries** | `RELIANCE.NS` | **1996-01-01** | ~30.7 Years | ~7,717 |
| **HDFC Bank** | `HDFCBANK.NS` | **1996-01-01** | ~30.7 Years | ~7,717 |
| **Infosys** | `INFY.NS` | **1996-01-01** | ~30.7 Years | ~7,717 |
| **Tata Consultancy Services**| `TCS.NS` | **2002-08-12** | ~24.1 Years | ~5,992 |

### Category C: Commodities, Forex & Sovereign Rates
| Asset Name | Symbol | Earliest Digital Inception | Coverage (Years) | Estimated Bars |
| :--- | :--- | :--- | :--- | :--- |
| **Gold Futures (COMEX)** | `GC=F` | **2000-08-30** | ~26.1 Years | ~6,617 |
| **Silver Futures** | `SI=F` | **2000-08-30** | ~26.1 Years | ~6,617 |
| **Crude Oil WTI** | `CL=F` | **2000-08-23** | ~26.1 Years | ~6,622 |
| **USD / INR Forex Spot** | `INR=X` | **2003-12-01** | ~22.8 Years | ~5,947 |
| **US 10-Yr Treasury Yield** | `^TNX` | **1970-01-02** | 56.7 Years | ~14,296 |

---

## 2. Ingestion Performance Metrics

```
+-------------------------------------------------------------------------+
| TOTAL ASSETS INGESTED:          17 Core Instruments                     |
| TOTAL COMBINED DAILY BARS:      ~148,500 Bars (1970 - 2026)             |
| TOTAL PAYLOAD DOWNLOAD SIZE:    ~12.0 MB                                |
| FINAL DISK SIZE (ZSTD PARQUET): ~2.1 MB                                 |
| TOTAL INGESTION EXECUTION TIME: ~18.5 Seconds                           |
| STORAGE LOCATION:               data/macro/*.parquet                    |
+-------------------------------------------------------------------------+
```

---

## 3. Storage Schema Specification

Each symbol is written to `data/macro/{clean_symbol}_1d.parquet` with the following canonical PyArrow schema:

```python
MACRO_SCHEMA = pa.schema([
    ("timestamp", pa.int64()),       # Unix epoch timestamp in seconds
    ("date", pa.string()),           # YYYY-MM-DD
    ("open", pa.float64()),          # Opening price
    ("high", pa.float64()),          # Intraday high
    ("low", pa.float64()),           # Intraday low
    ("close", pa.float64()),         # Daily close
    ("volume", pa.float64()),        # Trading volume
    ("adj_close", pa.float64()),     # Dividend / split adjusted close
])
```

---

## 4. Execution Command & Pipeline

To run the automated ingestion:
```powershell
python ingestion/download_macro_and_equities.py
```

To query across 50 years of multi-asset data with DuckDB:
```python
import duckdb
con = duckdb.connect()
df = con.execute("""
    SELECT date, close 
    FROM 'data/macro/GSPC_1d.parquet' 
    WHERE date >= '1985-01-01'
""").df()
```
