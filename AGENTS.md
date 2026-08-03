# AGENTS.md

Guidance for AI agents and developers working in this repository.

## Product

**Lead_Automation** — pulls Sunrun permit data from the Context.dev API (`https://sunrunapi.context.dev/v1`) via `scripts/pull_context_permits.py`. Output lands under `data/context_permits/<UTC-timestamp>/` (`jurisdictions.json`, `permits.jsonl`, `pull_meta.json`). Python 3 stdlib only; no `requirements.txt` or local services.

## Cursor Cloud specific instructions

### Secrets

- **`api_key`** (required for real API calls): Bearer token for Context.dev. Configure as a **Runtime Secret** in [Cursor Cloud Agents → Environment → Secrets](https://cursor.com/dashboard/cloud-agents#environments), then start a new agent run so the VM receives it.

### Run the permit pull

From the repository root:

```bash
python3 scripts/pull_context_permits.py
```

Optional environment variables (see `README.md`): `MAX_ROWS`, `PAGE_LIMIT`, `DATA_DIR`.

### Cloudflare / User-Agent (Error 1010)

Some networks (including many cloud egress IPs) block Python’s default `urllib` User-Agent (`Python-urllib/3.x`) with Cloudflare **Error 1010**. Symptoms: `HTTP 403` and `browser_signature_banned` on the first request to `/jurisdictions`.

- **Verify API + secret**: `curl` with a custom `-A` / `User-Agent` and `Authorization: Bearer $api_key` should return `200`.
- **Run the CLI without editing the repo** (monkeypatch before `runpy`):

```bash
MAX_ROWS=5 python3 -c "
import runpy, urllib.request
_O = urllib.request.Request
class R(_O):
    def __init__(self, url, data=None, headers={}, **kw):
        h = dict(headers or {}); h.setdefault('User-Agent', 'Lead-Automation/1.0')
        kw2 = {k: v for k, v in kw.items() if k in ('origin_req_host', 'unverifiable', 'method')}
        super().__init__(url, data, h, **kw2)
urllib.request.Request = R
runpy.run_path('scripts/pull_context_permits.py', run_name='__main__')
"
```

A durable fix is to add a `User-Agent` header in `scripts/pull_context_permits.py`’s `_request()` (not applied in this doc-only setup).

### Lint / tests

- **Syntax check**: `python3 -m py_compile scripts/pull_context_permits.py`
- **Automated tests**: none in the repository today.
- **E2E smoke**: successful run creates a new timestamped folder under `data/context_permits/` with three files and `pull_meta.json` reporting `rows_written` > 0 when the API has data.

### Services

| Component | Required |
|-----------|----------|
| Python 3 | Yes |
| Context.dev Sunrun API (HTTPS) | Yes |
| `api_key` env | Yes (live pull) |
| Docker / DB / npm | No |
