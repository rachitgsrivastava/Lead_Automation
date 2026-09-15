# Lead_Automation

Pull Sunrun permit data from the Context.dev API and (later) score leads.

## Context permit pull

Requires the **`api_key`** environment variable (set in [Cursor Cloud Agents → Environment → Secrets](https://cursor.com/dashboard/cloud-agents#environments) as a **Runtime Secret**, then start a new agent run so the VM receives it).

```bash
# Default: all jurisdictions, all time, max 500,000 rows, 1000 rows/page
python3 scripts/pull_context_permits.py

# Optional overrides
export MAX_ROWS=500000
export PAGE_LIMIT=1000
export DATA_DIR=data/context_permits
```

Output is written under `data/context_permits/<UTC-timestamp>/`:

- `jurisdictions.json`
- `permits.jsonl` (one permit JSON per line)
- `pull_meta.json`

## Refresh (incremental + `latest/` snapshot)

Use this for day-to-day updates instead of re-downloading everything:

```bash
# Default: incremental since last successful refresh (merges into data/context_permits/latest/)
python3 scripts/refresh_context_permits.py

# Force a full re-pull into latest/
REFRESH_MODE=full python3 scripts/refresh_context_permits.py

# Override the incremental window (ISO 8601 UTC)
SINCE=2026-09-01T00:00:00Z python3 scripts/refresh_context_permits.py
```

Each run also writes a timestamped folder under `data/context_permits/<UTC-timestamp>/` with `refresh_meta.json`. State for the next incremental run is stored in `data/context_permits/refresh_state.json`.

Optional: `SINCE_PARAM` (default `since`) if the API uses a different query name.

## API

- Base URL: `https://sunrunapi.context.dev/v1`
- Docs: jurisdictions, permits list, lookup (see project chat / internal Context docs)
