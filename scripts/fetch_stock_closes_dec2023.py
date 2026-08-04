#!/usr/bin/env python3
"""Fetch daily closing prices for energy tickers (last 30 trading days of 2023).

Uses Yahoo Finance's public chart API (no API key). Trading days are taken from
SPY session dates in calendar year 2023 (NYSE-style daily bars). Output is written
under data/stock_closes_dec2023/ by default.
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

YEAR = 2023
N_TRADING_DAYS = 30
CALENDAR_TICKER = "SPY"

USER_AGENT = (
    "Mozilla/5.0 (compatible; Lead_Automation/1.0; +https://github.com/rachitgsrivastava/Lead_Automation)"
)


def year_unix_bounds(year: int) -> tuple[int, int]:
    period1 = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp())
    return period1, period2


def load_tickers(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    tickers = [row["ticker"].strip() for row in rows if row.get("ticker")]
    if not tickers:
        raise ValueError(f"No tickers found in {path}")
    return tickers


def _fetch_chart_payload(ticker: str, period1: int, period2: int, retries: int = 3) -> dict:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(ticker)}"
        f"?period1={period1}&period2={period2}&interval=1d"
    )
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
            else:
                raise RuntimeError(f"{ticker}: failed after {retries} attempts") from last_err
    raise RuntimeError(f"{ticker}: unreachable") from last_err


def parse_daily_closes(
    payload: dict,
    ticker: str,
    *,
    year: int | None = None,
    only_dates: set[date] | None = None,
) -> list[tuple[date, float]]:
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
        if year is not None and d.year != year:
            continue
        if only_dates is not None and d not in only_dates:
            continue
        out.append((d, float(close)))
    out.sort(key=lambda x: x[0])
    return out


def fetch_daily_closes(
    ticker: str,
    period1: int,
    period2: int,
    *,
    year: int | None = None,
    only_dates: set[date] | None = None,
) -> list[tuple[date, float]]:
    payload = _fetch_chart_payload(ticker, period1, period2)
    return parse_daily_closes(payload, ticker, year=year, only_dates=only_dates)


def last_n_trading_days_of_year(year: int, n: int, calendar_ticker: str = CALENDAR_TICKER) -> list[date]:
    period1, period2 = year_unix_bounds(year)
    series = fetch_daily_closes(calendar_ticker, period1, period2, year=year)
    dates = sorted({d for d, _ in series})
    if len(dates) < n:
        raise RuntimeError(
            f"Expected at least {n} trading days in {year} from {calendar_ticker}, got {len(dates)}"
        )
    return dates[-n:]


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
    parser.add_argument(
        "--calendar-ticker",
        default=CALENDAR_TICKER,
        help=f"Ticker used to define US trading days (default: {CALENDAR_TICKER})",
    )
    args = parser.parse_args()

    period1, period2 = year_unix_bounds(YEAR)
    trading_dates = last_n_trading_days_of_year(YEAR, N_TRADING_DAYS, args.calendar_ticker)
    trading_set = set(trading_dates)

    print(
        f"Last {N_TRADING_DAYS} trading days of {YEAR}: "
        f"{trading_dates[0].isoformat()} .. {trading_dates[-1].isoformat()}",
        file=sys.stderr,
    )

    tickers = load_tickers(args.tickers_csv)
    long_rows: list[dict[str, str | float]] = []
    by_ticker: dict[str, dict[date, float]] = {}
    errors: list[str] = []

    for i, ticker in enumerate(tickers):
        if i > 0 and args.sleep > 0:
            time.sleep(args.sleep)
        try:
            series = fetch_daily_closes(
                ticker, period1, period2, year=YEAR, only_dates=trading_set
            )
            if not series:
                raise RuntimeError("no closing prices on target trading days (symbol may be delisted)")
            by_ticker[ticker] = {d: c for d, c in series}
            for d, c in series:
                long_rows.append({"date": d.isoformat(), "ticker": ticker, "close": c})
            missing = len(trading_dates) - len(series)
            suffix = f", {missing} dates missing" if missing else ""
            print(f"{ticker}: {len(series)} closes{suffix}", file=sys.stderr)
        except Exception as e:
            errors.append(f"{ticker}: {e}")
            print(f"ERROR {ticker}: {e}", file=sys.stderr)

    long_rows.sort(key=lambda r: (r["date"], r["ticker"]))

    out_long = args.out_dir / "closes_long.csv"
    out_wide = args.out_dir / "closes_wide.csv"
    write_long_csv(out_long, long_rows)
    write_wide_csv(out_wide, by_ticker, trading_dates)

    meta = {
        "year": YEAR,
        "n_trading_days": N_TRADING_DAYS,
        "calendar_ticker": args.calendar_ticker,
        "trading_dates": [d.isoformat() for d in trading_dates],
        "range_start": trading_dates[0].isoformat(),
        "range_end": trading_dates[-1].isoformat(),
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
