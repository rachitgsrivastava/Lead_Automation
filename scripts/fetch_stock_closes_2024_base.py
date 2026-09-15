#!/usr/bin/env python3
"""Fetch closes and return vs 2024 base window for the solar peer list (17 tickers)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from stock_avg_return import run_avg_return_study

ROOT = Path(__file__).resolve().parents[1]
BASE_YEAR = 2024


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare average close: last 30 NYSE sessions of calendar year 2024 vs "
            "last 30 sessions as of run date (SPY calendar). "
            "Default tickers: data/energy_companies_2024_base.csv (17 names, includes RUN)."
        )
    )
    parser.add_argument(
        "--tickers-csv",
        type=Path,
        default=ROOT / "data" / "energy_companies_2024_base.csv",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "data" / "stock_closes_2024_base",
    )
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--calendar-ticker", default="SPY")
    args = parser.parse_args()
    return run_avg_return_study(
        base_year=BASE_YEAR,
        tickers_csv=args.tickers_csv,
        out_dir=args.out_dir,
        sleep=args.sleep,
        calendar_ticker=args.calendar_ticker,
        write_legacy_closes_aliases=False,
    )


if __name__ == "__main__":
    sys.exit(main())
