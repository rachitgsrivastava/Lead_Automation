"""Shared logic: compare avg close (last 30 sessions of a base year) vs recent 30 sessions."""

from __future__ import annotations

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


def return_pct(avg_base: float, avg_recent: float) -> float:
    return (avg_recent - avg_base) / avg_base * 100.0


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


def write_returns_csv(path: Path, rows: list[dict[str, object]], base_year: int) -> None:
    avg_base_col = f"avg_close_{base_year}_last_30td"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "ticker",
        avg_base_col,
        "avg_close_recent_last_30td",
        "return_pct",
        "no_longer_traded",
        "note",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_avg_return_study(
    *,
    base_year: int,
    tickers_csv: Path,
    out_dir: Path,
    sleep: float = 0.35,
    calendar_ticker: str = CALENDAR_TICKER,
    write_legacy_closes_aliases: bool = False,
) -> int:
    as_of = datetime.now(timezone.utc).date()
    avg_base_col = f"avg_close_{base_year}_last_30td"
    period1_base, period2_base = year_unix_bounds(base_year)
    period1_recent, period2_recent = recent_unix_bounds()

    trading_dates_base = last_n_trading_days_of_year(base_year, N_TRADING_DAYS, calendar_ticker)
    trading_set_base = set(trading_dates_base)
    trading_dates_recent = last_n_trading_days_recent(N_TRADING_DAYS, calendar_ticker, as_of=as_of)
    trading_set_recent = set(trading_dates_recent)

    print(
        f"Last {N_TRADING_DAYS} trading days of {base_year}: "
        f"{trading_dates_base[0].isoformat()} .. {trading_dates_base[-1].isoformat()}",
        file=sys.stderr,
    )
    print(
        f"Last {N_TRADING_DAYS} trading days as of {as_of.isoformat()}: "
        f"{trading_dates_recent[0].isoformat()} .. {trading_dates_recent[-1].isoformat()}",
        file=sys.stderr,
    )

    tickers = load_tickers(tickers_csv)
    long_rows_base: list[dict[str, str | float]] = []
    long_rows_recent: list[dict[str, str | float]] = []
    by_ticker_base: dict[str, dict[date, float]] = {}
    by_ticker_recent: dict[str, dict[date, float]] = {}
    returns_rows: list[dict[str, object]] = []
    errors: list[str] = []

    for i, ticker in enumerate(tickers):
        if i > 0 and sleep > 0:
            time.sleep(sleep)

        series_base, err_base = try_fetch_daily_closes(
            ticker,
            period1_base,
            period2_base,
            year=base_year,
            only_dates=trading_set_base,
        )
        if sleep > 0:
            time.sleep(sleep)
        series_recent, err_recent = try_fetch_daily_closes(
            ticker,
            period1_recent,
            period2_recent,
            only_dates=trading_set_recent,
            on_or_before=as_of,
        )

        avg_base = average_close(series_base)
        avg_recent = average_close(series_recent)
        no_longer_traded = not series_recent
        notes: list[str] = []
        if err_base:
            notes.append(f"{base_year}: {err_base}")
        if err_recent:
            notes.append(f"recent: {err_recent}")

        if no_longer_traded:
            ret = DELISTED_RETURN_PCT
            if not notes:
                notes.append("no recent closing prices (no longer traded)")
        elif avg_base is None:
            ret = DELISTED_RETURN_PCT
            notes.append(f"missing {base_year} average; return set to -100%")
        else:
            ret = return_pct(avg_base, avg_recent)  # type: ignore[arg-type]

        if series_base:
            by_ticker_base[ticker] = {d: c for d, c in series_base}
            for d, c in series_base:
                long_rows_base.append({"date": d.isoformat(), "ticker": ticker, "close": c})
        if series_recent:
            by_ticker_recent[ticker] = {d: c for d, c in series_recent}
            for d, c in series_recent:
                long_rows_recent.append({"date": d.isoformat(), "ticker": ticker, "close": c})

        returns_rows.append(
            {
                "ticker": ticker,
                avg_base_col: "" if avg_base is None else round(avg_base, 6),
                "avg_close_recent_last_30td": "" if avg_recent is None else round(avg_recent, 6),
                "return_pct": round(ret, 6),
                "no_longer_traded": "true" if no_longer_traded else "false",
                "note": "; ".join(notes),
            }
        )

        status = "DELISTED" if no_longer_traded else "ok"
        print(
            f"{ticker}: {base_year} avg={avg_base!s}, recent avg={avg_recent!s}, "
            f"return={ret:.2f}% ({status})",
            file=sys.stderr,
        )
        if no_longer_traded or err_base:
            errors.append(f"{ticker}: {'; '.join(notes)}")

    long_rows_base.sort(key=lambda r: (r["date"], r["ticker"]))
    long_rows_recent.sort(key=lambda r: (r["date"], r["ticker"]))

    out_long_base = out_dir / f"closes_{base_year}_last_30td_long.csv"
    out_wide_base = out_dir / f"closes_{base_year}_last_30td_wide.csv"
    out_long_recent = out_dir / "closes_recent_last_30td_long.csv"
    out_wide_recent = out_dir / "closes_recent_last_30td_wide.csv"
    out_returns = out_dir / "returns_avg_last_30td.csv"

    write_long_csv(out_long_base, long_rows_base, f"{base_year}_last_{N_TRADING_DAYS}td")
    write_wide_csv(out_wide_base, by_ticker_base, trading_dates_base)
    write_long_csv(out_long_recent, long_rows_recent, f"recent_last_{N_TRADING_DAYS}td")
    write_wide_csv(out_wide_recent, by_ticker_recent, trading_dates_recent)
    write_returns_csv(out_returns, returns_rows, base_year)

    if write_legacy_closes_aliases:
        write_long_csv(out_dir / "closes_long.csv", long_rows_base, f"{base_year}_last_{N_TRADING_DAYS}td")
        write_wide_csv(out_dir / "closes_wide.csv", by_ticker_base, trading_dates_base)

    meta = {
        "as_of": as_of.isoformat(),
        "base_year": base_year,
        "n_trading_days": N_TRADING_DAYS,
        "calendar_ticker": calendar_ticker,
        f"trading_dates_{base_year}": [d.isoformat() for d in trading_dates_base],
        "trading_dates_recent": [d.isoformat() for d in trading_dates_recent],
        f"range_{base_year}_start": trading_dates_base[0].isoformat(),
        f"range_{base_year}_end": trading_dates_base[-1].isoformat(),
        "range_recent_start": trading_dates_recent[0].isoformat(),
        "range_recent_end": trading_dates_recent[-1].isoformat(),
        "delisted_return_pct": DELISTED_RETURN_PCT,
        "return_formula": f"(avg_recent - avg_{base_year}) / avg_{base_year} * 100",
        "tickers_requested": tickers,
        f"tickers_with_{base_year}_closes": sorted(by_ticker_base.keys()),
        "tickers_with_recent_closes": sorted(by_ticker_recent.keys()),
        "errors": errors,
        f"rows_long_{base_year}": len(long_rows_base),
        "rows_long_recent": len(long_rows_recent),
    }
    meta_path = out_dir / "fetch_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out_returns}", file=sys.stderr)
    print(f"Wrote {out_long_base} ({len(long_rows_base)} rows)", file=sys.stderr)
    print(f"Wrote {out_long_recent} ({len(long_rows_recent)} rows)", file=sys.stderr)
    return 1 if errors else 0
