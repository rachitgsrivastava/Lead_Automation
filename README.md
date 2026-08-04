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

## Historical closes (last 30 trading days of 2023)

Fetch daily **closing** prices for every ticker in `energy_companies.csv` for the **last 30 NYSE trading sessions of calendar year 2023** (session list from `SPY` daily bars). Data is pulled from Yahoo Finance’s public chart API (stdlib only; no API key).

```bash
python3 scripts/fetch_stock_closes_dec2023.py
```

Outputs under `data/stock_closes_dec2023/` (gitignored):

| File | Format |
|------|--------|
| `closes_long.csv` | `date`, `ticker`, `close` |
| `closes_wide.csv` | One row per trading date (30 rows), one column per ticker |
| `fetch_meta.json` | Full list of trading dates, tickers fetched, any errors |

For 2023 the window is **2023-11-16 through 2023-12-29** (30 sessions; 2023-12-29 was the last US equity session that year).

**Note:** Symbols removed from Yahoo after delisting (e.g. `NOVA`, `TPIC` as of 2026) may return no data; see `fetch_meta.json` for per-ticker errors.
