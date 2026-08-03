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

## API

- Base URL: `https://sunrunapi.context.dev/v1`
- Docs: jurisdictions, permits list, lookup (see project chat / internal Context docs)
