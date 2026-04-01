# Content Harness — implementation plan

This document maps **Milestones 2–5** after **Milestone 1** (schemas, YAML brands, placeholder LangGraph, FastAPI, worker stub, SQLite persistence).

## Principles

- Human approval before any WordPress call; **draft posts only** in v1.
- Typed **Pydantic** artifacts between stages; **LangGraph** for deterministic phase-1 flow; **phase 2** export is a separate invoke after approval.
- **PostgreSQL** on Railway via `DATABASE_URL` (`postgresql+asyncpg://...`); **Alembic** should replace `create_all` before production scale.
- LLM calls via **OpenAI-compatible** client (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `DEFAULT_MODEL`).
- **Structured logging** (structlog); no secrets in logs (truncate WP responses).

## Architecture reference

**Phase 1** (`harness/graphs/pipeline.py` → `persist_review_item`): ingestion through assets, status `pending_review`.

**Phase 2** (`build_phase2_export_graph`): `export_to_wordpress_draft` only, after DB approval flag (Milestone 4).

**State**: `GraphState` TypedDict in `harness/state/graph_state.py`; DB column `PipelineRun.state_json` holds a JSON-serialisable snapshot (`harness/services/state_json.py`).

---

## Milestone 2 — Source ingestion and topic candidates

**Goals**

- Real **RSS** parsing and optional **manual URL** fetch (extract title/meta) using `feedparser` and `httpx`.
- Normalise to `SourceItem`; persist with run or as child table (optional normalisation in DB).
- Replace stub `fetch_sources` / `score_topics` nodes with implementations calling `harness/tools/` modules.
- Config: use `brands/*/sources.yaml` lists.

**Files (expected)**

- `harness/tools/rss.py`, `harness/tools/html_excerpt.py` (minimal).
- Update `harness/nodes/fetch_sources.py`, `harness/nodes/score_topics.py`.
- Optional: `harness/services/llm.py` wrapper for scoring/discovery via `DEFAULT_MODEL`.
- Prompts: `harness/prompts/topic_scoring.j2` (if LLM-assisted).

**Persistence**

- Optionally add `SourceItemRow` or embed list in `state_json` only in v1 (current pattern is enough if size stays bounded).

**Risks**

- Rate limits and robots.txt on manual URLs — keep timeouts and user-Agent respectful.

---

## Milestone 3 — Brief, draft, review pass, channel assets

**Goals**

- Jinja templates in `harness/prompts/` for: brief, article, consistency review, LinkedIn, image prompts, metadata.
- `harness/services/llm.py`: single place for chat completions, logging request/response metadata (no full payload dumps in production logs).
- Implement nodes: `create_editorial_brief`, `draft_article`, `review_article`, `generate_channel_assets` with real model calls and `BrandConfig` injection.
- `ReviewWarnings` populated from structured model output or rule-based checks.

**Files**

- Update `harness/nodes/*.py` listed above.
- New prompts `*.j2` per stage.

**Quality**

- Enforce `banned_phrases` in a lightweight post-processor.
- Keep source URLs attached to claims where possible for traceability.

---

## Milestone 4 — Review UI and approval actions

**Goals**

- Server-rendered Jinja pages: run list (filter by brand), run detail showing article, sources, LinkedIn, image prompts, metadata, warnings.
- `POST` approval endpoints: `approve`, `reject`, `editing_later`; persist `approval_json` on `PipelineRun`.
- Only `approved` runs may enqueue or invoke **phase 2** (enforce in route/service).

**Files**

- `apps/api/routes/review.py` or extend `runs.py`.
- `apps/api/templates/review_*.html`.
- Optional: HTMX or plain forms — keep dependency-free.

**State machine**

- `RunStatus`: align API with `pending_review` → `approved` | `rejected` | `editing_later`.
- Phase 2 runner entry: `POST /runs/{id}/export-wordpress` or worker job triggered by approval.

---

## Milestone 5 — WordPress draft export and Railway readiness

**Goals**

- Implement `harness/services/wordpress.py`: `POST /wp-json/wp/v2/posts` with `status: draft`, map title, `content`, `excerpt`, `slug`, categories/tags if API supports.
- Auth: **Application Passwords**; read credentials from env vars named in each brand’s `brand.yaml` (`username_env`, `application_password_env`).
- Store `WordPressExportResult` in `wordpress_result_json`; surface link/id in review UI.
- **Railway**: two services (API + worker), **Postgres** plugin, env vars documented in README.
- **Cron**: Railway Cron job `POST /runs/trigger` with `Authorization` secret **or** worker `WEEKLY_CRON` enabled; document one recommended path.

**Ops**

- Add **Alembic** migrations for `PipelineRun` and future tables.
- Health check should verify DB connectivity optionally.

---

## Postgres notes

- Local: `DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/harness`
- Railway: paste generated URL; ensure `+asyncpg` driver segment matches SQLAlchemy 2 async URL format.
- SQLite dev keeps iteration fast; run one migration smoke on Postgres before launch.

---

## Testing strategy (later)

- Contract tests for RSS parser and WP client (mocked HTTP).
- Golden-file tests for prompt rendering (optional).

---

## Completed in Milestone 1

- Package layout, `.env.example`, Docker/Railway scaffolding.
- Pydantic schemas and brand YAML for three slugs.
- LangGraph phase 1 + phase 2 graphs with stub nodes.
- `PipelineRun` + `create_and_run_phase1` / `run_phase2_export`.
- FastAPI: health, brands, runs list/trigger/detail.
- Worker with APScheduler stub.
- **Runtime notes:** `requires-python >= 3.9` plus `eval-type-backport` for Pydantic `|` unions on 3.9; LangGraph `GraphState` uses `typing.Optional` for optional keys (required for `get_type_hints` on 3.9). Set **`BRANDS_ROOT`** in Docker/Railway (`/app/brands`) so packs resolve when the package is installed from a wheel layout.
