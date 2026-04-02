# Brand knowledge (file drop-in)

Optional files under each **`brands/<slug>/`** add structured and narrative context for LLM prompts. Everything is read **once** at the start of phase 1 (`load_brand_config`). There is **no** search index or vector retrieval — text is concatenated with **fixed size caps** (see `harness/services/brand_knowledge_loader.py`).

**If you add no extra files**, behaviour matches a brand that only has `brand.yaml` and `sources.yaml`: the snapshot is empty, prompts get no `brand_knowledge_context`, and the review UI shows no “Brand knowledge” block.

---

## Recommended per-brand layout

```text
brands/<slug>/
  brand.yaml              # required — voice, audience, settings (existing)
  sources.yaml            # optional — URL list for source-driven runs (existing)

  partners.yaml           # optional — partners, events, approved phrasing, sensitivity
  content_notes.md        # optional — long-form notes (markdown)
  template.yaml           # optional — free-form key/value hints for article shape
  library/                # optional — background .md / .txt (see rules below)
```

Copy examples from **`docs/examples/brand_knowledge/`** when you are ready (rename `.example` → real filename).

---

## Supported files (reference)

| File | Format | Where to put what |
|------|--------|-------------------|
| **`partners.yaml`** | YAML mapping | **Partners**: list under `partners` (`name`, `role`, `organisation`, `website`, `notes`, `sensitivity`). **Recurring campaigns/events**: `recurring_events`. **Approved wording**: `approved_language` (`phrase`, `context`). **Short programme positioning**: `programme_notes`. **Careful handling**: `sensitive_context` (plain text / block scalar). Unknown keys are ignored. |
| **`content_notes.md`** | Markdown (UTF-8) | **Notes**: positioning, programme history, meeting summaries, “what worked in past content”, anything too long for YAML. |
| **`template.yaml`** | YAML mapping | **Template hints**: any keys you find useful (e.g. `intro_preference`, `section_patterns`); values become labelled lines in the prompt. Must be a YAML dictionary (not a bare list). |
| **`library/*.{md,txt}`** | UTF-8 text | **Background docs**: briefings, paste-ready context, scraped notes. Sorted path order; only `.md` and `.txt`. **`README.md` / `README.txt` in `library/` are ignored** so you can document the folder locally. Hidden files (`.*`) skipped. |

**Not loaded:** files outside these names/paths, binary formats (e.g. PDF/DOCX — paste or extract to `.md`/`.txt` first), other extensions in `library/`.

---

## Robustness

- **Missing files**: no error; empty snapshot for that section.
- **Invalid YAML** (`partners.yaml` / `template.yaml`): warning in logs; that file’s contribution is treated as empty; pipeline continues.
- **Wrong root type** (e.g. YAML list instead of mapping at top level for `partners.yaml`): treated as empty structured section.
- **Bad rows** in `partners`, `recurring_events`, or `approved_language`: invalid rows are **skipped**; valid rows still apply.
- **Oversized notes / many library files**: excerpts and totals are **truncated**; flags on the snapshot / review UI reflect truncation where applicable.
- **`loaded_paths`** in the snapshot lists only sources that **actually contributed** non-empty prompt material (so an empty placeholder `partners.yaml` does not clutter the review UI).

---

## How to add a new brand knowledge pack later

1. Pick your slug: `brands/<slug>/` must already contain at least **`brand.yaml`** (and usually `sources.yaml`).
2. **Partners / programmes / sensitivity / approved language** → create or edit **`partners.yaml`** (start from `docs/examples/brand_knowledge/partners.yaml.example`).
3. **Longer narrative notes** → add **`content_notes.md`** (see `content_notes.md.example`).
4. **Article-shape hints** → add **`template.yaml`** (see `template.yaml.example`).
5. **Extra background text** → create **`library/`** and drop in **`.md` or `.txt`** files; optional local **`library/README.md`** explaining the folder is ignored by the loader.
6. Run the pipeline as usual; review the run detail page to confirm **“Brand knowledge used”** lists the paths you expect.

No API or admin UI step is required — filesystem changes are picked up on the next run.

---

## Related code

- Loader: `harness/services/brand_knowledge_loader.py`
- Schema: `harness/schemas/brand_knowledge.py`
- Prompt block: `harness/prompts/_brand_knowledge.j2`
