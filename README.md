# Lead_Automation

## Energy industry tickers

Peer and adjacent public companies (solar, storage, renewables) for lead scoring and enrichment:

| File | Description |
|------|-------------|
| [`data/energy_companies.csv`](data/energy_companies.csv) | Ticker and company name (18 rows) |

```bash
# Quick view
column -t -s, data/energy_companies.csv
```

## Historical closes (Dec 2023)

Fetch daily **closing** prices for every ticker in `energy_companies.csv` for the **last 30 calendar days of 2023** (2023-12-02 through 2023-12-31). Data is pulled from Yahoo Finance’s public chart API (stdlib only; no API key).

```bash
python3 scripts/fetch_stock_closes_dec2023.py
```

Outputs under `data/stock_closes_dec2023/` (gitignored):

| File | Format |
|------|--------|
| `closes_long.csv` | `date`, `ticker`, `close` |
| `closes_wide.csv` | One row per date, one column per ticker |
| `fetch_meta.json` | Date range, tickers fetched, any errors |

Weekends and market holidays have no rows; expect ~20 trading days in that window per symbol.

**Note:** Symbols removed from Yahoo after delisting (e.g. `NOVA`, `TPIC` as of 2026) may return no data; see `fetch_meta.json` for per-ticker errors.
