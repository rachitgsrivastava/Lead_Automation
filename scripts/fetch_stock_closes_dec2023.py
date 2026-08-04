#!/usr/bin/env python3
"""Fetch closing prices and compare 30-session average vs recent 30-session average.

For each ticker in data/energy_companies.csv:

1. Last 30 US trading sessions of calendar year 2023 (SPY calendar).
2. Last 30 US trading sessions as of when the script runs (SPY calendar).

Writes daily closes plus per-ticker average closes and return
(percent change from 2023 average to recent average). Tickers with no
recent trade data are treated as no longer traded (return -100%).

Uses Yahoo Finance's public chart API (stdlib only; no API key).
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
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TICKERS_CSV = ROOT / "data" / "energy_companies.csv"

YEAR = 2023
N_TRADING_DAYS = 30
CALENDAR_TICKER = "SPY"
DELISTED_RETURN_PCT = -100.0
RECENT_CALENDAR_BUFFER_DAYS = 120

USER_AGENT = (
    "Mozilla/5.0 (compatible; Lead_Automation/1.0; +https://github.com/rachitgsrivastava/Lead_Automation)"
)


def year_unix_bounds(year: int) -> tuple[int, int]:
    period1 = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp())
    return period1, period2


def recent_unix_bounds(buffer_days: int = RECENT_CALENDAR_BUFFER_DAYS) -> tuple[int, int]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=buffer_days)
    period1 = int(datetime.combine(start, dt_time.min, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.combine(today + timedelta(days=1), dt_time.min, tzinfo=timezone.utc).timestamp())
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
    on_or_before: date | None = None,
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
        if on_or_before is not None and d > on_or_before:
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
    on_or_before: date | None = None,
) -> list[tuple[date, float]]:
    payload = _fetch_chart_payload(ticker, period1, period2)
    return parse_daily_closes(
        payload,
        ticker,
        year=year,
        only_dates=only_dates,
        on_or_before=on_or_before,
    )


def try_fetch_daily_closes(
    ticker: str,
    period1: int,
    period2: int,
    *,
    year: int | None = None,
    only_dates: set[date] | None = None,
    on_or_before: date | None = None,
) -> tuple[list[tuple[date, float]], str | None]:
    try:
        return (
            fetch_daily_closes(
                ticker,
                period1,
                period2,
                year=year,
                only_dates=only_dates,
                on_or_before=on_or_before,
            ),
            None,
        )
    except Exception as e:
        return [], str(e)


def last_n_trading_days_of_year(year: int, n: int, calendar_ticker: str = CALENDAR_TICKER) -> list[date]:
    period1, period2 = year_unix_bounds(year)
    series = fetch_daily_closes(calendar_ticker, period1, period2, year=year)
    dates = sorted({d for d, _ in series})
    if len(dates) < n:
        raise RuntimeError(
            f"Expected at least {n} trading days in {year} from {calendar_ticker}, got {len(dates)}"
        )
    return dates[-n:]


def last_n_trading_days_recent(
    n: int,
    calendar_ticker: str = CALENDAR_TICKER,
    *,
    as_of: date | None = None,
) -> list[date]:
    as_of = as_of or datetime.now(timezone.utc).date()
    period1, period2 = recent_unix_bounds()
    series = fetch_daily_closes(calendar_ticker, period1, period2, on_or_before=as_of)
    dates = sorted({d for d, _ in series})
    if len(dates) < n:
        raise RuntimeError(
            f"Expected at least {n} recent trading days from {calendar_ticker}, got {len(dates)}"
        )
    return dates[-n:]


def average_close(series: list[tuple[date, float]]) -> float | None:
    if not series:
        return None
    return mean(c for _, c in series)


def return_pct(avg_2023: float, avg_recent: float) -> float:
    return (avg_recent - avg_2023) / avg_2023 * 100.0


def write_long_csv(path: Path, rows: list[dict[str, str | float]], period: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["period", "date", "ticker", "close"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"period": period, **row})


def write_wide_csv(path: Path, by_ticker: dict[str, dict[date, float]], dates: list[date]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tickers = sorted(by_ticker.keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", *tickers])
        for d in dates:
            writer.writerow([d.isoformat(), *[by_ticker[t].get(d, "") for t in tickers]])


def write_returns_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "ticker",
        "avg_close_2023_last_30td",
        "avg_close_recent_last_30td",
        "return_pct",
        "no_longer_traded",
        "note",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


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

    as_of = datetime.now(timezone.utc).date()
    period1_2023, period2_2023 = year_unix_bounds(YEAR)
    period1_recent, period2_recent = recent_unix_bounds()

    trading_dates_2023 = last_n_trading_days_of_year(YEAR, N_TRADING_DAYS, args.calendar_ticker)
    trading_set_2023 = set(trading_dates_2023)
    trading_dates_recent = last_n_trading_days_recent(
        N_TRADING_DAYS, args.calendar_ticker, as_of=as_of
    )
    trading_set_recent = set(trading_dates_recent)

    print(
        f"Last {N_TRADING_DAYS} trading days of {YEAR}: "
        f"{trading_dates_2023[0].isoformat()} .. {trading_dates_2023[-1].isoformat()}",
        file=sys.stderr,
    )
    print(
        f"Last {N_TRADING_DAYS} trading days as of {as_of.isoformat()}: "
        f"{trading_dates_recent[0].isoformat()} .. {trading_dates_recent[-1].isoformat()}",
        file=sys.stderr,
    )

    tickers = load_tickers(args.tickers_csv)
    long_rows_2023: list[dict[str, str | float]] = []
    long_rows_recent: list[dict[str, str | float]] = []
    by_ticker_2023: dict[str, dict[date, float]] = {}
    by_ticker_recent: dict[str, dict[date, float]] = {}
    returns_rows: list[dict[str, object]] = []
    errors: list[str] = []

    for i, ticker in enumerate(tickers):
        if i > 0 and args.sleep > 0:
            time.sleep(args.sleep)

        series_2023, err_2023 = try_fetch_daily_closes(
            ticker,
            period1_2023,
            period2_2023,
            year=YEAR,
            only_dates=trading_set_2023,
        )
        if args.sleep > 0:
            time.sleep(args.sleep)
        series_recent, err_recent = try_fetch_daily_closes(
            ticker,
            period1_recent,
            period2_recent,
            only_dates=trading_set_recent,
            on_or_before=as_of,
        )

        avg_2023 = average_close(series_2023)
        avg_recent = average_close(series_recent)
        no_longer_traded = not series_recent
        notes: list[str] = []
        if err_2023:
            notes.append(f"2023: {err_2023}")
        if err_recent:
            notes.append(f"recent: {err_recent}")

        if no_longer_traded:
            ret = DELISTED_RETURN_PCT
            if not notes:
                notes.append("no recent closing prices (no longer traded)")
        elif avg_2023 is None:
            ret = DELISTED_RETURN_PCT
            notes.append("missing 2023 average; return set to -100%")
        else:
            ret = return_pct(avg_2023, avg_recent)  # type: ignore[arg-type]

        if series_2023:
            by_ticker_2023[ticker] = {d: c for d, c in series_2023}
            for d, c in series_2023:
                long_rows_2023.append({"date": d.isoformat(), "ticker": ticker, "close": c})
        if series_recent:
            by_ticker_recent[ticker] = {d: c for d, c in series_recent}
            for d, c in series_recent:
                long_rows_recent.append({"date": d.isoformat(), "ticker": ticker, "close": c})

        returns_rows.append(
            {
                "ticker": ticker,
                "avg_close_2023_last_30td": "" if avg_2023 is None else round(avg_2023, 6),
                "avg_close_recent_last_30td": "" if avg_recent is None else round(avg_recent, 6),
                "return_pct": round(ret, 6),
                "no_longer_traded": "true" if no_longer_traded else "false",
                "note": "; ".join(notes),
            }
        )

        status = "DELISTED" if no_longer_traded else "ok"
        print(
            f"{ticker}: 2023 avg={avg_2023!s}, recent avg={avg_recent!s}, "
            f"return={ret:.2f}% ({status})",
            file=sys.stderr,
        )
        if no_longer_traded or err_2023:
            errors.append(f"{ticker}: {'; '.join(notes)}")

    long_rows_2023.sort(key=lambda r: (r["date"], r["ticker"]))
    long_rows_recent.sort(key=lambda r: (r["date"], r["ticker"]))

    out_long_2023 = args.out_dir / "closes_2023_last_30td_long.csv"
    out_wide_2023 = args.out_dir / "closes_2023_last_30td_wide.csv"
    out_long_recent = args.out_dir / "closes_recent_last_30td_long.csv"
    out_wide_recent = args.out_dir / "closes_recent_last_30td_wide.csv"
    out_returns = args.out_dir / "returns_avg_last_30td.csv"

    write_long_csv(out_long_2023, long_rows_2023, f"{YEAR}_last_{N_TRADING_DAYS}td")
    write_wide_csv(out_wide_2023, by_ticker_2023, trading_dates_2023)
    write_long_csv(out_long_recent, long_rows_recent, f"recent_last_{N_TRADING_DAYS}td")
    write_wide_csv(out_wide_recent, by_ticker_recent, trading_dates_recent)
    write_returns_csv(out_returns, returns_rows)

    # Backward-compatible names for 2023 daily files
    write_long_csv(args.out_dir / "closes_long.csv", long_rows_2023, f"{YEAR}_last_{N_TRADING_DAYS}td")
    write_wide_csv(args.out_dir / "closes_wide.csv", by_ticker_2023, trading_dates_2023)

    meta = {
        "as_of": as_of.isoformat(),
        "year": YEAR,
        "n_trading_days": N_TRADING_DAYS,
        "calendar_ticker": args.calendar_ticker,
        "trading_dates_2023": [d.isoformat() for d in trading_dates_2023],
        "trading_dates_recent": [d.isoformat() for d in trading_dates_recent],
        "range_2023_start": trading_dates_2023[0].isoformat(),
        "range_2023_end": trading_dates_2023[-1].isoformat(),
        "range_recent_start": trading_dates_recent[0].isoformat(),
        "range_recent_end": trading_dates_recent[-1].isoformat(),
        "delisted_return_pct": DELISTED_RETURN_PCT,
        "return_formula": "(avg_recent - avg_2023) / avg_2023 * 100",
        "tickers_requested": tickers,
        "tickers_with_2023_closes": sorted(by_ticker_2023.keys()),
        "tickers_with_recent_closes": sorted(by_ticker_recent.keys()),
        "errors": errors,
        "rows_long_2023": len(long_rows_2023),
        "rows_long_recent": len(long_rows_recent),
    }
    meta_path = args.out_dir / "fetch_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out_returns}", file=sys.stderr)
    print(f"Wrote {out_long_2023} ({len(long_rows_2023)} rows)", file=sys.stderr)
    print(f"Wrote {out_long_recent} ({len(long_rows_recent)} rows)", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
