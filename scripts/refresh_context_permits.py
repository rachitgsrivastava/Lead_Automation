#!/usr/bin/env python3
"""Refresh permit data: incremental pull (since last run) and merge into latest/."""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from context_api import (
    DEFAULT_MAX_ROWS,
    DEFAULT_PAGE_LIMIT,
    LATEST_DIRNAME,
    iter_permits,
    load_permits_jsonl,
    load_refresh_state,
    permit_key,
    pull_jurisdictions,
    save_refresh_state,
    write_merged_permits_jsonl,
    write_permits_jsonl,
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _refresh_mode() -> str:
    mode = os.environ.get("REFRESH_MODE", "incremental").strip().lower()
    if mode not in {"incremental", "full"}:
        raise SystemExit(f"Invalid REFRESH_MODE={mode!r}; use incremental or full")
    return mode


def _since_param_name() -> str:
    return os.environ.get("SINCE_PARAM", "since").strip() or "since"


def _fetch_merge_and_write_run(
    run_permits: Path,
    latest_permits: Path,
    max_rows: int,
    page_limit: int,
    since: str | None,
    since_param: str,
    seed_from_latest: bool,
) -> tuple[int, int]:
    """Fetch permits once, write run snapshot, merge into latest."""
    merged = load_permits_jsonl(latest_permits) if seed_from_latest else {}
    before_keys = set(merged)
    fetched = 0

    with run_permits.open("w", encoding="utf-8") as run_file:
        for permit in iter_permits(
            max_rows,
            page_limit,
            since=since,
            since_param=since_param,
        ):
            fetched += 1
            run_file.write(json.dumps(permit, ensure_ascii=False) + "\n")
            key = permit_key(permit)
            if key is None:
                key = f"__anonymous_{fetched}"
            merged[key] = permit

    write_merged_permits_jsonl(latest_permits, merged)
    net_new = len(set(merged) - before_keys)
    return fetched, net_new


def main() -> None:
    max_rows = int(os.environ.get("MAX_ROWS", str(DEFAULT_MAX_ROWS)))
    page_limit = int(os.environ.get("PAGE_LIMIT", str(DEFAULT_PAGE_LIMIT)))
    mode = _refresh_mode()
    since_param = _since_param_name()
    explicit_since = os.environ.get("SINCE")

    data_dir = Path(os.environ.get("DATA_DIR", "data/context_permits"))
    data_dir.mkdir(parents=True, exist_ok=True)

    stamp = _utc_stamp()
    run_dir = data_dir / stamp
    latest_dir = data_dir / LATEST_DIRNAME
    latest_permits = latest_dir / "permits.jsonl"
    latest_jurisdictions = latest_dir / "jurisdictions.json"
    latest_meta = latest_dir / "pull_meta.json"

    prior_state = load_refresh_state(data_dir)
    prior_since = prior_state.get("last_refresh_at")
    since_for_api: str | None = None

    if mode == "full":
        since_for_api = None
    elif explicit_since:
        since_for_api = explicit_since
    elif prior_since and latest_permits.is_file():
        since_for_api = prior_since
    else:
        mode = "full"
        print("No prior latest snapshot; running full refresh.", flush=True)

    run_jurisdictions = run_dir / "jurisdictions.json"
    run_permits = run_dir / "permits.jsonl"
    run_meta = run_dir / "refresh_meta.json"

    pull_jurisdictions(run_jurisdictions)

    rows_fetched = 0
    rows_net_new = 0

    latest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run_jurisdictions, latest_jurisdictions)

    if mode == "full":
        rows_fetched = write_permits_jsonl(
            run_permits,
            iter_permits(max_rows, page_limit),
        )
        shutil.copy2(run_permits, latest_permits)
        rows_net_new = rows_fetched
    else:
        assert since_for_api is not None
        rows_fetched, rows_net_new = _fetch_merge_and_write_run(
            run_permits,
            latest_permits,
            max_rows,
            page_limit,
            since=since_for_api,
            since_param=since_param,
            seed_from_latest=latest_permits.is_file(),
        )

    refreshed_at = _iso_now()
    rows_in_latest = len(load_permits_jsonl(latest_permits))

    run_meta_payload: dict[str, Any] = {
        "refreshed_at": refreshed_at,
        "run_stamp": stamp,
        "mode": mode,
        "since_param": since_param,
        "since_sent": since_for_api,
        "rows_fetched_this_run": rows_fetched,
        "rows_net_new_or_updated": rows_net_new,
        "rows_in_latest": rows_in_latest,
        "run_dir": str(run_dir),
        "latest_dir": str(latest_dir),
    }
    run_meta.write_text(json.dumps(run_meta_payload, indent=2) + "\n", encoding="utf-8")

    latest_meta_payload = {
        **run_meta_payload,
        "permits_path": str(latest_permits),
        "jurisdictions_path": str(latest_jurisdictions),
    }
    latest_meta.write_text(json.dumps(latest_meta_payload, indent=2) + "\n", encoding="utf-8")

    save_refresh_state(
        data_dir,
        {
            "last_refresh_at": refreshed_at,
            "last_mode": mode,
            "last_run_dir": str(run_dir),
            "last_since_sent": since_for_api,
            "rows_in_latest": rows_in_latest,
        },
    )

    print(
        f"Refresh done ({mode}). Fetched {rows_fetched} rows this run; "
        f"{rows_in_latest} permits in {latest_permits}",
        flush=True,
    )


if __name__ == "__main__":
    main()
