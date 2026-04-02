# Content Harness

Multi-brand editorial pipeline: ingest sources → topics → brief → draft → review assets → **human approval** in the review UI → optional integrations (e.g. WordPress draft) configured per brand.

**v0.1** — FastAPI API, worker with optional scheduler, SQLite by default, YAML brands under `brands/`.

## Requirements

- Python 3.9+ (3.11+ recommended; `eval-type-backport` helps on 3.9)
- Optional: OpenAI-compatible HTTP API (see `.env.example`)

## Local setup

```bash
cd "Content Assistant"
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env
# Edit .env — at minimum DATABASE_URL and LLM settings if you use an LLM
```

The `data/` directory is created for the default SQLite file path (`./data/harness.db`). It is mostly gitignored once databases exist; an empty `data/` is kept via `data/.gitkeep`.

## Run the API

```bash
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

- **http://127.0.0.1:8000** — home
- **http://127.0.0.1:8000/docs** — OpenAPI (try `POST /runs/trigger` here)
- **http://127.0.0.1:8000/review** — review queue (HTML)
- **GET /healthz** — health
- **GET /brands** — configured brand slugs
- **GET /runs** — list runs; optional query `?brand_slug=...`

## Run the worker

Runs scheduled jobs when `WEEKLY_CRON` is set (see `.env.example`). Set `DISABLE_SCHEDULER=1` to run without firing cron.

```bash
python -m apps.worker.main
```

## Trigger a pipeline run (phase 1)

With the API running:

```bash
curl -s -X POST http://127.0.0.1:8000/runs/trigger \
  -H "Content-Type: application/json" \
  -d '{"brand_slug": "inventive-africa"}'
```

**Idea-driven run** (skip RSS/topic discovery; you supply the angle). Optional `run_intent` (default `blog_plus_social`); use `social_only` for a stub article plus full social pack.

```bash
curl -s -X POST http://127.0.0.1:8000/runs/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "brand_slug": "onix",
    "run_mode": "idea_driven",
    "run_intent": "blog_plus_social",
    "idea": {
      "working_title": "Why operators still underestimate patch latency",
      "bullet_points": ["SMB precedent", "Budget trade-offs", "One KPI to watch"],
      "angle": "Practical, non-alarmist take for IT leaders",
      "notes": "Link to brand tone: clear, technical"
    }
  }'
```

You can also run **POST /runs/trigger** from `/docs` and edit the JSON there (source-driven or idea-driven).

The run moves through phase 1 until it reaches **`pending_review`** (if your brand requires human approval). **GET /runs/{uuid}** returns JSON including `state` and `status`.

## Review queue

1. Open **http://127.0.0.1:8000/review**
2. Filter by **brand** and **status** (e.g. pending review vs all)
3. Open a run → inspect the package → **Approve**, **Reject**, or **Mark editing later**
4. **Approved** runs only: optional **Send to WordPress draft** in the UI, or **`POST /runs/{run_id}/wordpress/draft`** from the API, if WordPress env vars and `brand.yaml` are set (see `docs/implementation_plan.md`)

## Local testing (quick checks)

1. **Health:** `curl -s http://127.0.0.1:8000/healthz`
2. **Brands:** `curl -s http://127.0.0.1:8000/brands`
3. **Trigger:** `POST /runs/trigger` with a valid `brand_slug`, note the `id` in the response
4. **Poll:** `GET /runs/{id}` until `status` is `pending_review` (or terminal state if LLM skips are enabled)
5. **Review UI:** open `/review`, find the run, open detail, exercise approve/reject as needed

With **`SKIP_TOPIC_LLM=1`** / **`SKIP_CONTENT_LLM=1`** in `.env`, the pipeline can complete with less dependence on a live model (see `.env.example` comments).

## Docker (optional)

```bash
docker compose up --build
```

API on port **8000**; compose may set `DISABLE_SCHEDULER=1` for the worker — see `docker-compose.yml`.

## Railway (hosted)

First-time production layout: **one API service** + **one worker service**, same Docker image, **shared Postgres** (`DATABASE_URL`). The API listens on **`PORT`** (set by Railway). Step-by-step env vars, database, uploads, and brands-on-disk behavior: **[docs/railway.md](docs/railway.md)**.

## Brands

Edit **`brands/<slug>/brand.yaml`** and **`sources.yaml`**. Example slugs: `inventive-africa`, `onix`, `tucker-family-charity`.

## Docs

- [docs/implementation_plan.md](docs/implementation_plan.md) — milestones and architecture notes
- [docs/railway.md](docs/railway.md) — Railway deployment (API + worker + Postgres)
