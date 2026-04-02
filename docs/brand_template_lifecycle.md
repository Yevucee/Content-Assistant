# Brand template lifecycle

Structured voice and channel hints for prompts are modeled as `BrandTemplateProfile` (see `harness/schemas/brand_template.py`).

## Storage (two different “templates”)

| Location | Purpose |
|----------|---------|
| `brands/<slug>/brand.yaml` | Canonical brand config; a **baseline** profile is derived via `BrandTemplateProfile.from_brand_config_dict`. |
| `brands/<slug>/brand_template.yaml` | **Active** full profile, optional. Validated on read/write. Used for production runs when present. |
| `brands/<slug>/template.yaml` | **Knowledge** hints only (free-form), loaded by `brand_knowledge_loader`. **Not** the same as `BrandTemplateProfile`. |

Do not use `template.yaml` for the active structured profile — that name is reserved for knowledge merging.

## States in the workflow

1. **Proposed** — Output of website / blog analysis (`proposed_brand_template` on run state). Shown in review UI and via `GET /runs/{id}/proposed-brand-template`. **Never** applied to generation automatically.

2. **Reviewed** — Human inspects JSON on the run detail page or comparison view (`/review/brands/<slug>/brand-template/compare?run_id=…`).

3. **Edited** — JSON adjusted in the template editor (`/review/brands/<slug>/brand-template`) or via `PUT /brands/<slug>/brand-template`.

4. **Saved as active** — Explicit write to `brand_template.yaml` (checkbox in UI, or `confirm_replace: true` in API when replacing an existing file). No silent overwrite.

## What runs use (`brand_template_resolution`)

Each pipeline run stores `brand_template_resolution` in `state_json`:

- `prompt_template_source`: `active_file` — merged active YAML over `brand.yaml` baseline; `brand_yaml_only` — no active file (or file unreadable; see pipeline `errors`).
- `proposed_template_in_run` / `proposed_not_applied_to_prompts`: set on website discovery runs to stress that the proposed blob is **not** the prompt source until saved.

`resolved_brand_template` is the profile merged into `brand_snapshot()` for LLM prompts (including channel gens).

## Local testing

1. Start the API and open `/review`.
2. Run website discovery for a brand; open the run detail — proposed template and resolution appear.
3. Use “Compare with saved active” or “Seed editor from this run”, edit JSON, confirm, save.
4. Trigger a content run for the same brand — resolution should show `active_file` if the file exists and is valid.
