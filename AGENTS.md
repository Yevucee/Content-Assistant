# AGENTS.md

## Cursor Cloud specific instructions

Content Harness is a single Python product: a FastAPI editorial pipeline (LangGraph) with a server-rendered Jinja UI. Standard setup/run commands live in `README.md`; only the non-obvious caveats are captured here.

### Environment
- Dependencies install into a virtualenv at `.venv` (the update script runs `python3 -m venv .venv` + `.venv/bin/pip install -e ".[dev]"`). Either activate it (`source .venv/bin/activate`) or call binaries directly (e.g. `.venv/bin/uvicorn`, `.venv/bin/ruff`).
- `python3.12-venv` (a system apt package) is required to create the venv and is preinstalled in the VM snapshot; it is intentionally NOT in the update script.
- `.env` is gitignored. If it is missing, create it with `cp .env.example .env`.

### Running offline (no LLM in the cloud VM)
- `.env.example` points the LLM at `http://127.0.0.1:9888/v1` (model `local-8b`). That local model is NOT running in the cloud VM. To exercise the pipeline end-to-end offline, set `SKIP_TOPIC_LLM=1` and `SKIP_CONTENT_LLM=1` in `.env` — the pipeline then uses heuristic/structured fallbacks and a triggered run completes to `pending_review` with no external calls.
- The default database is SQLite at `./data/harness.db` and tables are auto-created on API startup (`init_db()`); no DB service to start.

### Services
- API (required): `.venv/bin/uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000`. Serves the REST API, `/docs`, the `/app` workflow UI, and the `/review` approval UI. The LangGraph pipeline runs in-process here.
- Worker (optional): `python -m apps.worker.main`. Only runs scheduled cron jobs (`WEEKLY_CRON`); the tick is currently a stub, so it is NOT needed to test the manual trigger → review → approve flow.

### Smoke test
With the API running: `curl /healthz` → `curl /brands` → `POST /runs/trigger {"brand_slug":"inventive-africa"}` → poll `GET /runs/{id}` until `pending_review` → approve in `/review`.

### Lint
`.venv/bin/ruff check .` (config in `pyproject.toml`). Note: the repo currently has a few pre-existing ruff findings unrelated to environment setup.
