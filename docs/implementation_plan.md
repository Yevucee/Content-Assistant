# Content Harness — implementation plan

This document maps **Milestones 2–5** after **Milestone 1** (initial schemas, YAML brands, LangGraph phase-1 pipeline, FastAPI, worker stub, SQLite persistence).

## Principles

- Human approval before any WordPress call; **draft posts only** in v1.
- Typed **Pydantic** artifacts between stages; **LangGraph** for deterministic **phase-1** pipeline only (through `pending_review`).
- **WordPress draft export** is a separate, explicit HTTP action after approval (`harness/services/wp_export.py`); it is **not** a second LangGraph graph.
- **PostgreSQL** on Railway via `DATABASE_URL` (the app rewrites `postgres://` / `postgresql://` to `postgresql+asyncpg://` for SQLAlchemy async); **Alembic** should replace `create_all` before production scale.
- LLM calls via **OpenAI-compatible** client (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `DEFAULT_MODEL`).
- **Structured logging** (structlog); no secrets in logs (truncate WP responses).

## Architecture reference

**Phase 1 pipeline** (`harness/graphs/pipeline.py` → `persist_review_item`): ingestion through channel assets; run status ends at `pending_review`.

**WordPress (after approval)** — not part of LangGraph:

- Service: `harness/services/wp_export.py` → `export_approved_run_to_wordpress`.
- HTTP: **`POST /runs/{run_id}/wordpress/draft`** (JSON API) and review UI **`POST /review/runs/{run_id}/wordpress-draft`** (form).
- Client + payload: `harness/services/wordpress.py` (`create_draft_post`, `draft_payload_from_state`); credentials from env vars named in `brand.yaml` (`wordpress.username_env`, `wordpress.application_password_env`).
- Results: append-only journal in `PipelineRun.wordpress_result_json`, modelled as `WordPressExportJournal` (`harness/schemas/wordpress_export.py`).

**State**: `GraphState` TypedDict in `harness/state/graph_state.py`; DB column `PipelineRun.state_json` holds a JSON-serialisable snapshot (`harness/services/state_json.py`).

---

## Unified input modes & channel outputs (vNext)

### Design

- **One pipeline**, multiple **entry paths** (`RunMode`), controlled by `route_after_brand` in `harness/graphs/routing.py` after `load_brand_config`.
- **RunIntent** steers emphasis (e.g. `social_only` uses a stub article so channel adapters still run); full matrix is evolving.
- All paths converge before `create_editorial_brief` on a shared shape: `selected_topic` + `source_items` (often empty for idea runs) + `brand_config_snapshot`.
- **Normalisation**: typed captures in `harness/schemas/inputs.py` → `NormalizedContentInput` via `harness/services/input_normalization.py`.
- **Brand template**: `harness/schemas/brand_template.py` + `harness/services/brand_template.py` (YAML-backed today; inference from site/blog = future).
- **Channel adapters** produce a **`ChannelOutputBundle`** (`harness/schemas/channel_outputs.py`) stored in `state_json` and `run_generated_content.channel_outputs_json`, alongside legacy `linkedin_post` / `image_prompts`.

### Run modes (all wired in `harness/graphs/routing.py`)

| RunMode | Entry |
| ------- | ----- |
| `source_driven` | Default: `fetch_sources` → score → select → brief → … |
| `idea_driven` | `POST /runs/trigger` with `idea`; skips fetch/score/select. |
| `document_driven`, `transcript_driven` | Paste or upload via `POST /runs/trigger` or `POST /runs/trigger/upload`. |
| `mixed` | `MixedInputBundle` + optional upload. |
| `website_discovery`, `existing_blog_style` | Site/blog analysis → review only (no full article path). |

### Phases (build order)

- **A** (done): schemas, routing, normalisation, channel bundle persistence, review UI surfacing.
- **B** (done): idea-driven + multi-channel text outputs.
- **C** (done): document/transcript uploads + text extraction → normalisers.
- **D** (done): website / existing-blog discovery + proposed `BrandTemplateProfile` (see `docs/brand_template_lifecycle.md` for save-as-active flow).
- **E** (done): `MixedInputBundle` merge + validation.

### Database note

`run_generated_content.channel_outputs_json` is added for new installs. Existing SQLite DBs without the column should be recreated locally (`rm data/*.db`) or migrated manually until Alembic lands.

---

## Milestone 2 — Source ingestion and topic candidates

**Goals (current implementation)**

- **RSS** + **manual URL** fetch in `harness/services/source_ingestion.py` (`feedparser`, `httpx`).
- Normalise to `SourceItem`; graph state plus optional rows via `harness/services/run_artifacts.py` (`RunSourceItem`, `RunTopicCandidate`).
- Nodes: `harness/nodes/fetch_sources.py`, `harness/nodes/score_topics.py`; topic discovery LLM path in `harness/services/topic_generation.py` + `harness/prompts/topic_discovery.j2`.
- Config: `brands/*/sources.yaml` lists.

**Persistence**

- Source list and topic candidates are stored in `state_json` and mirrored to relational tables when a run reaches `pending_review` (see `pipeline_runner` + `run_artifacts`).

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
- Only **`approved`** runs may call WordPress export (`wp_export` enforces this).

**Files**

- Review UI: `apps/api/routes/review_ui.py`, `apps/api/templates/review/*.html`.
- Run / export API: `apps/api/routes/runs.py` (`POST /runs/{run_id}/wordpress/draft`).

**State machine**

- `RunStatus`: `pending_review` → `approved` | `rejected` | `editing_later` (via review forms / approval service).
- WordPress is **not** triggered by approval itself; the user or API calls the export endpoint after approve.

---

## Milestone 5 — WordPress draft export and Railway readiness

**Goals**

- `harness/services/wordpress.py`: `POST /wp-json/wp/v2/posts` with `status: draft`, map title, HTML content, excerpt, slug.
- Auth: **Application Passwords**; credentials from env vars named in each brand’s `brand.yaml` (`username_env`, `application_password_env`).
- Orchestration: `harness/services/wp_export.py` appends attempts to `wordpress_result_json` (`WordPressExportJournal` / `WordPressExportAttempt` in `harness/schemas/wordpress_export.py`); review UI shows export history and post links.
- **Railway**: two services (API + worker), **Postgres** plugin — see **`docs/railway.md`**.
- **Cron**: Railway Cron job `POST /runs/trigger` with `Authorization` secret **or** worker `WEEKLY_CRON` enabled; document one recommended path.

**Ops**

- Add **Alembic** migrations for `PipelineRun` and future tables.
- Health check should verify DB connectivity optionally.

---

## Postgres notes

- Local: `DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/harness`
- Railway: paste the plugin URL as-is (`postgres://` or `postgresql://`); `harness/services/db.py` rewrites it for async SQLAlchemy (already `postgresql+asyncpg://` is left unchanged).
- SQLite dev keeps iteration fast; run one migration smoke on Postgres before launch.
- Hosted checklist: **`docs/railway.md`**.

---

## Testing strategy (later)

- Contract tests for RSS parser and WP client (mocked HTTP).
- Golden-file tests for prompt rendering (optional).

---

## Completed in Milestone 1

- Package layout, `.env.example`, Docker/Railway scaffolding.
- Pydantic schemas and brand YAML for three slugs.
- LangGraph **phase-1** graph (`build_phase1_graph`); compiled lazily from `create_and_run_phase1` in `harness/services/pipeline_runner.py`.
- `PipelineRun` + `create_and_run_phase1`; WordPress export lives outside the graph (see Architecture reference above).
- FastAPI: health, brands, runs list/trigger/detail.
- Worker with APScheduler stub.
- **Runtime notes:** `requires-python >= 3.9` plus `eval-type-backport` for Pydantic `|` unions on 3.9; LangGraph `GraphState` uses `typing.Optional` for optional keys (required for `get_type_hints` on 3.9). Set **`BRANDS_ROOT`** in Docker/Railway (`/app/brands`) so packs resolve when the package is installed from a wheel layout.
