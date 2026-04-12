# Railway deployment (first hosted setup)

This project runs as **two services** from the **same Docker image**:

| Service | Start command | Role |
|--------|----------------|------|
| **API** | Image default (`uvicorn`, see `Dockerfile`) | HTTP + review UI + OpenAPI |
| **Worker** | `python -m apps.worker.main` | Optional `WEEKLY_CRON` scheduler (idle loop if unset) |

Create **two Railway services**, connect the same GitHub repo, use **Dockerfile** builds for both. Override **only the worker’s** start command in the Railway service settings.

---

## Required environment variables (both services)

Set the **same** values on API and worker unless noted.

| Variable | Required | Notes |
|----------|----------|--------|
| `DATABASE_URL` | **Yes** (hosted) | From **Railway Postgres** plugin (recommended). The app rewrites `postgres://` / `postgresql://` to `postgresql+asyncpg://`. Do **not** rely on SQLite for production with two containers: each container has its own disk unless you add a shared volume. |
| `BRANDS_ROOT` | Recommended | Default in image: `/app/brands` (already set in `Dockerfile`). Override only if you mount brands elsewhere. |
| `OPENAI_BASE_URL` | If using LLM | Must be reachable from Railway (public HTTPS or your private network), **not** `127.0.0.1` unless you use a tunnel. |
| `OPENAI_API_KEY` | If provider needs it | |
| `DEFAULT_MODEL` | If using LLM | |
| `APP_BASE_URL` | Recommended | Public URL of the **API** service (e.g. `https://your-app.up.railway.app`). Used for review UI links and callbacks; set to your primary HTTPS origin. |
| `LOG_LEVEL` | Optional | Default `INFO`. |
| `LOG_FORMAT` | Optional | `json` for structured logs. |
| `ENABLE_DEBUG_ROUTES` | Optional | Set to `1` only for temporary diagnostics — mounts `/debug/*` (default **off**; omit in production). |
| `SKIP_INIT_DB_ON_STARTUP` | Optional | Set to `1` to skip `init_db()` on boot (rare; for isolating HTTP vs DB). **Unset** for normal operation. |

**WordPress** (if used): same variable **names** as in each brand’s `brand.yaml` (`wordpress.username_env`, `wordpress.application_password_env`). Set the corresponding secrets in Railway for **API** (export runs in the API process).

**Worker-only:**

| Variable | Notes |
|----------|--------|
| `WEEKLY_CRON` | Optional. Empty = scheduler disabled (worker sleeps; see `apps/worker/scheduler.py`). |
| `DISABLE_SCHEDULER` | Set to `1` to force-disable cron even if `WEEKLY_CRON` is set. |

---

## Database expectations

- **Local:** SQLite (`sqlite+aiosqlite:///./data/harness.db`) is fine; `data/` is persistent on your machine / bind-mounted in Compose.
- **Railway (API + worker):** use **Railway Postgres** and attach the plugin so both services receive the **same** `DATABASE_URL`. The async driver is applied in `harness/services/db.py` (`pool_pre_ping` enabled for transient network blips).
- **Schema:** `init_db()` runs `create_all` on API startup (`apps.api.main` lifespan). First API boot creates tables on the Postgres instance.
- **`pipeline_runs` timestamps (Postgres only):** After `create_all`, if existing columns are still `timestamp without time zone`, `init_db` runs a one-time `ALTER … TYPE timestamptz` for `created_at` / `updated_at`, interpreting stored naive values as UTC. This fixes asyncpg naive/aware errors on older DBs without Alembic. New databases already use timestamptz from the model and skip the ALTER.
- **Migrations:** There is no Alembic in-repo yet; schema changes today assume acceptable `create_all` behavior or manual DB handling.

If `sslmode` / SSL errors appear with your Postgres provider, append query args to `DATABASE_URL` as required by that host (e.g. `?sslmode=require`) — Railway’s generated URLs are usually sufficient.

---

## Uploads storage (`data/uploads/`)

- Run-trigger **multipart uploads** are written under `data/uploads/{run_id}/` (see `harness/services/upload_storage.py`).
- In the container, that path resolves under **`/app/data/uploads`** (ephemeral filesystem on Railway).
- **What does not persist across redeploy / new instances:** uploaded binary files on disk. Pipeline **state** (including extracted text capped for the run) is in **`state_json`** / DB; the **original file on disk** may be missing after redeploy.
- **Mitigation (future / ops):** mount a Railway volume on `/app/data`, or switch to object storage (not implemented in v0.1).

---

## What the Docker image contains

- **`brands/`** is **`COPY`**’d into the image at build time (`Dockerfile`). Updates to YAML packs require a **new deploy** (rebuild) unless you mount a volume over `/app/brands`.
- **`data/`** in the image is an empty directory only; production DB should be Postgres, not the baked SQLite file.

---

## Recommended deployment order

1. Create **Postgres** on Railway; copy `DATABASE_URL` into variables for later.
2. Create **API** service: Dockerfile build, set env vars (at minimum `DATABASE_URL`, `APP_BASE_URL`, LLM-related if needed). Deploy and confirm `GET /healthz` on the public URL.
3. Create **Worker** service: same repo/image, **start command** `python -m apps.worker.main`, **same** `DATABASE_URL` (and LLM env if the worker will trigger runs later).
4. Trigger a test run via `POST /runs/trigger` on the API public URL; open `/review` and verify DB-backed state.

---

## Caveats / warnings

- **SQLite on Railway:** Single-service experiments may “work” with default SQLite, but the DB file is **ephemeral**; redeploys lose data. **Two services without Postgres** = two separate SQLite files ⇒ **broken** shared state.
- **`PORT`:** The API container must listen on Railway’s `PORT`; the `Dockerfile` `CMD` uses `${PORT:-8000}`. Railway injects `PORT` at runtime — do not hard-code a different listen port in the image.
- **Health checks:** `railway.toml` may set `healthcheckPath` to `GET /ping` (static JSON, no DB). You can point the service health check at `/ping` or `/healthz` in the dashboard; `/healthz` is also lightweight (no DB). Prefer consistency with the repo config when possible.
- **Private LLM at `127.0.0.1`:** Not reachable from Railway; point `OPENAI_BASE_URL` at a publicly reachable or VPC-reachable endpoint.
- **Review UI** is served by the API; protect `/review` in production (network policy or future auth) if the deployment is public.

See also [.env.example](../.env.example) and [implementation_plan.md](implementation_plan.md).
