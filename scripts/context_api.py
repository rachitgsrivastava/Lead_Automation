"""Shared Sunrun Context.dev API client (stdlib only)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://sunrunapi.context.dev/v1"
DEFAULT_MAX_ROWS = 500_000
DEFAULT_PAGE_LIMIT = 1000
STATE_FILENAME = "refresh_state.json"
LATEST_DIRNAME = "latest"


def auth_header() -> str:
    key = os.environ.get("api_key")
    if not key:
        raise SystemExit(
            "Missing environment variable api_key. Set it in Cursor cloud environment secrets."
        )
    return f"Bearer {key}"


def request(
    path: str,
    params: dict[str, str] | None = None,
    max_retries: int = 30,
) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    headers = {
        "Authorization": auth_header(),
        "Accept": "application/json",
        "User-Agent": os.environ.get("USER_AGENT", "Lead-Automation/1.0"),
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
    data = request("/jurisdictions")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    jurisdictions = data.get("jurisdictions") or data.get("results") or []
    if isinstance(data, list):
        jurisdictions = data
    print(f"Jurisdictions saved to {out_path} (count={len(jurisdictions)})", flush=True)
    return jurisdictions


def iter_permits(
    max_rows: int,
    page_limit: int,
    since: str | None = None,
    since_param: str = "since",
) -> Iterator[dict[str, Any]]:
    """Yield permit records from GET /permits with cursor pagination."""
    params: dict[str, str] = {"limit": str(min(page_limit, 1000))}
    if since:
        params[since_param] = since

    cursor: str | None = None
    total_yielded = 0
    page = 0

    while total_yielded < max_rows:
        page += 1
        q = dict(params)
        if cursor:
            q["cursor"] = cursor

        data = request("/permits", q)
        pagination = data.get("pagination") or {}
        permits = data.get("permits") or []

        for permit in permits:
            if total_yielded >= max_rows:
                return
            yield permit
            total_yielded += 1

        print(
            f"Page {page}: fetched {len(permits)} rows, total={total_yielded}, "
            f"hasMore={pagination.get('hasMore')}",
            flush=True,
        )

        if total_yielded >= max_rows:
            return

        if not pagination.get("hasMore"):
            return

        next_cursor = pagination.get("nextCursor")
        if not next_cursor:
            return
        cursor = next_cursor


def write_permits_jsonl(path: Path, permits: Iterator[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", encoding="utf-8") as f:
        for permit in permits:
            f.write(json.dumps(permit, ensure_ascii=False) + "\n")
            written += 1
    return written


def pull_permits(
    out_path: Path,
    max_rows: int,
    page_limit: int,
    since: str | None = None,
    since_param: str = "since",
) -> int:
    return write_permits_jsonl(
        out_path,
        iter_permits(max_rows, page_limit, since=since, since_param=since_param),
    )


def permit_key(permit: dict[str, Any]) -> str | None:
    for field in ("id", "permitId", "permit_id", "uuid", "permitNumber", "permit_number"):
        value = permit.get(field)
        if value is not None and str(value).strip():
            return str(value)
    return None


def load_permits_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    merged: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                permit = json.loads(line)
            except json.JSONDecodeError as e:
                raise SystemExit(f"Invalid JSON in {path} line {line_no}: {e}") from e
            key = permit_key(permit)
            if key is None:
                key = f"__row_{line_no}"
            merged[key] = permit
    return merged


def write_merged_permits_jsonl(path: Path, permits_by_key: dict[str, dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for permit in permits_by_key.values():
            f.write(json.dumps(permit, ensure_ascii=False) + "\n")
    return len(permits_by_key)


def state_path(data_dir: Path) -> Path:
    return data_dir / STATE_FILENAME


def load_refresh_state(data_dir: Path) -> dict[str, Any]:
    path = state_path(data_dir)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid refresh state at {path}: {e}") from e


def save_refresh_state(data_dir: Path, state: dict[str, Any]) -> None:
    path = state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
