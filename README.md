# Lead_Automation

## Energy industry tickers

Peer and adjacent public companies (solar, storage, renewables) for lead scoring and enrichment:

| File | Description |
|------|-------------|
| [`data/energy_companies.csv`](data/energy_companies.csv) | Ticker and company name (19 rows) |

```bash
# Quick view
column -t -s, data/energy_companies.csv
```

## Stock closes and average-return comparison

For every ticker in `energy_companies.csv`, the script:

1. Pulls daily **closes** for the **last 30 NYSE sessions of calendar year 2023** (SPY calendar).
2. Pulls daily **closes** for the **last 30 NYSE sessions as of run date** (SPY calendar).
3. Computes the **average close** in each window and **return %**:

   `(avg_recent − avg_2023) / avg_2023 × 100`

   Tickers with **no recent trade data** are treated as no longer traded → **return −100%**.

Data comes from Yahoo Finance’s public chart API (stdlib only; no API key).

```bash
python3 scripts/fetch_stock_closes_dec2023.py
```

Outputs under `data/stock_closes_dec2023/` (gitignored):

| File | Format |
|------|--------|
| `returns_avg_last_30td.csv` | Per-ticker averages, return %, delisted flag |
| `closes_2023_last_30td_long.csv` / `_wide.csv` | 2023 window daily closes |
| `closes_recent_last_30td_long.csv` / `_wide.csv` | Recent window daily closes |
| `closes_long.csv` / `closes_wide.csv` | Same as 2023 files (backward compatible) |
| `fetch_meta.json` | Trading date lists, formula, errors |

2023 window (fixed): **2023-11-16 .. 2023-12-29**. Recent window end date is the latest SPY session on or before the run date.
