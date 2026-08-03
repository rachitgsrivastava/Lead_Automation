#!/usr/bin/env python3
"""Pull permits from Sunrun Context.dev API with cursor pagination."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://sunrunapi.context.dev/v1"
DEFAULT_MAX_ROWS = 500_000
DEFAULT_PAGE_LIMIT = 1000


def _auth_header() -> str:
    key = os.environ.get("api_key")
    if not key:
        raise SystemExit(
            "Missing environment variable api_key. Set it in Cursor cloud environment secrets."
        )
    return f"Bearer {key}"


def _request(
    path: str,
    params: dict[str, str] | None = None,
    max_retries: int = 30,
) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    headers = {
        "Authorization": _auth_header(),
        "Accept": "application/json",
    }

    for attempt in range(max_retries):
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except HTTPError as e:
            if e.code == 503 and attempt < max_retries - 1:
                retry_after = e.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else 5
                print(f"503 change_feed_busy, retry in {wait}s...", flush=True)
                time.sleep(wait)
                continue
            err_body = e.read().decode("utf-8", errors="replace")
            raise SystemExit(f"HTTP {e.code} for {url}: {err_body}") from e
        except URLError as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"Request failed: {e}") from e

    raise SystemExit("Max retries exceeded")


def pull_jurisdictions(out_path: Path) -> list[dict[str, Any]]:
    data = _request("/jurisdictions")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    jurisdictions = data.get("jurisdictions") or data.get("results") or []
    if isinstance(data, list):
        jurisdictions = data
    print(f"Jurisdictions saved to {out_path} (count={len(jurisdictions)})", flush=True)
    return jurisdictions


def pull_permits(
    out_path: Path,
    max_rows: int,
    page_limit: int,
) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    params: dict[str, str] = {"limit": str(min(page_limit, 1000))}
    cursor: str | None = None
    total_written = 0
    page = 0

    with out_path.open("w", encoding="utf-8") as f:
        while total_written < max_rows:
            page += 1
            q = dict(params)
            if cursor:
                q["cursor"] = cursor

            data = _request("/permits", q)
            pagination = data.get("pagination") or {}
            permits = data.get("permits") or []

            for permit in permits:
                if total_written >= max_rows:
                    break
                f.write(json.dumps(permit, ensure_ascii=False) + "\n")
                total_written += 1

            print(
                f"Page {page}: wrote {len(permits)} rows, total={total_written}, "
                f"hasMore={pagination.get('hasMore')}",
                flush=True,
            )

            if total_written >= max_rows:
                break

            if not pagination.get("hasMore"):
                break

            next_cursor = pagination.get("nextCursor")
            if not next_cursor:
                break
            cursor = next_cursor

    return total_written


def main() -> None:
    max_rows = int(os.environ.get("MAX_ROWS", str(DEFAULT_MAX_ROWS)))
    page_limit = int(os.environ.get("PAGE_LIMIT", str(DEFAULT_PAGE_LIMIT)))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    data_dir = Path(os.environ.get("DATA_DIR", "data/context_permits"))
    run_dir = data_dir / stamp

    jurisdictions_path = run_dir / "jurisdictions.json"
    permits_path = run_dir / "permits.jsonl"
    meta_path = run_dir / "pull_meta.json"

    pull_jurisdictions(jurisdictions_path)
    written = pull_permits(permits_path, max_rows=max_rows, page_limit=page_limit)

    meta = {
        "pulled_at": stamp,
        "max_rows_cap": max_rows,
        "rows_written": written,
        "permits_path": str(permits_path),
        "jurisdictions_path": str(jurisdictions_path),
        "filters": "all jurisdictions, all time (no date filters)",
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Done. {written} permits in {permits_path}", flush=True)


if __name__ == "__main__":
    main()
