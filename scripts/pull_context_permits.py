#!/usr/bin/env python3
"""Pull permits from Sunrun Context.dev API with cursor pagination."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from context_api import DEFAULT_MAX_ROWS, DEFAULT_PAGE_LIMIT, pull_jurisdictions, pull_permits


def main() -> None:
    max_rows = int(os.environ.get("MAX_ROWS", str(DEFAULT_MAX_ROWS)))
    page_limit = int(os.environ.get("PAGE_LIMIT", str(DEFAULT_PAGE_LIMIT)))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    data_dir = Path(os.environ.get("DATA_DIR", "data/context_permits"))
    data_dir.mkdir(parents=True, exist_ok=True)
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
