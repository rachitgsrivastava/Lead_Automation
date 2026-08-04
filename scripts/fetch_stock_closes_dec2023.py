#!/usr/bin/env python3
"""Fetch daily closing prices for energy tickers (last 30 days of 2023).

Uses Yahoo Finance's public chart API (no API key). Output is written under
data/stock_closes_dec2023/ by default.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TICKERS_CSV = ROOT / "data" / "energy_companies.csv"

# Last 30 calendar days of 2023: 2023-12-02 through 2023-12-31 (inclusive).
RANGE_START = date(2023, 12, 2)
RANGE_END = date(2023, 12, 31)
# Request window: start of Dec 1 UTC through start of Jan 1 2024 UTC.
PERIOD1 = int(datetime(2023, 12, 1, tzinfo=timezone.utc).timestamp())
PERIOD2 = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())

USER_AGENT = (
    "Mozilla/5.0 (compatible; Lead_Automation/1.0; +https://github.com/rachitgsrivastava/Lead_Automation)"
)


def load_tickers(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    tickers = [row["ticker"].strip() for row in rows if row.get("ticker")]
    if not tickers:
        raise ValueError(f"No tickers found in {path}")
    return tickers


def fetch_daily_closes(ticker: str, retries: int = 3) -> list[tuple[date, float]]:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(ticker)}"
        f"?period1={PERIOD1}&period2={PERIOD2}&interval=1d"
    )
    last_err: Exception | None = None
    payload: dict
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
            break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
            else:
                raise RuntimeError(f"{ticker}: failed after {retries} attempts") from last_err
    else:
        raise RuntimeError(f"{ticker}: unreachable") from last_err

    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        err = chart.get("error") or {}
        raise RuntimeError(f"{ticker}: no chart data ({err.get('description', 'unknown error')})")

    result = results[0]
    timestamps = result.get("timestamp") or []
    quotes = (result.get("indicators") or {}).get("quote") or [{}]
    closes = quotes[0].get("close") or []

    out: list[tuple[date, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        if RANGE_START <= d <= RANGE_END:
            out.append((d, float(close)))
    out.sort(key=lambda x: x[0])
    return out


def write_long_csv(path: Path, rows: list[dict[str, str | float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "ticker", "close"])
        writer.writeheader()
        writer.writerows(rows)


def write_wide_csv(path: Path, by_ticker: dict[str, dict[date, float]], dates: list[date]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tickers = sorted(by_ticker.keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", *tickers])
        for d in dates:
            writer.writerow([d.isoformat(), *[by_ticker[t].get(d, "") for t in tickers]])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tickers-csv",
        type=Path,
        default=DEFAULT_TICKERS_CSV,
        help="CSV with a ticker column (default: data/energy_companies.csv)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "data" / "stock_closes_dec2023",
        help="Directory for output CSV files",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.35,
        help="Seconds between ticker requests (rate limiting)",
    )
    args = parser.parse_args()

    tickers = load_tickers(args.tickers_csv)
    long_rows: list[dict[str, str | float]] = []
    by_ticker: dict[str, dict[date, float]] = {}
    errors: list[str] = []

    for i, ticker in enumerate(tickers):
        if i > 0 and args.sleep > 0:
            time.sleep(args.sleep)
        try:
            series = fetch_daily_closes(ticker)
            if not series:
                raise RuntimeError("no closing prices in date range (symbol may be delisted or illiquid)")
            by_ticker[ticker] = {d: c for d, c in series}
            for d, c in series:
                long_rows.append({"date": d.isoformat(), "ticker": ticker, "close": c})
            print(f"{ticker}: {len(series)} closes", file=sys.stderr)
        except Exception as e:
            errors.append(f"{ticker}: {e}")
            print(f"ERROR {ticker}: {e}", file=sys.stderr)

    long_rows.sort(key=lambda r: (r["date"], r["ticker"]))
    dates = sorted({d for m in by_ticker.values() for d in m})

    out_long = args.out_dir / "closes_long.csv"
    out_wide = args.out_dir / "closes_wide.csv"
    write_long_csv(out_long, long_rows)
    write_wide_csv(out_wide, by_ticker, dates)

    meta = {
        "range_start": RANGE_START.isoformat(),
        "range_end": RANGE_END.isoformat(),
        "tickers_requested": tickers,
        "tickers_ok": sorted(by_ticker.keys()),
        "errors": errors,
        "rows_long": len(long_rows),
    }
    meta_path = args.out_dir / "fetch_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out_long} ({len(long_rows)} rows)", file=sys.stderr)
    print(f"Wrote {out_wide}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
