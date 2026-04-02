"""Load per-brand knowledge from YAML, markdown, and library/ text files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import ValidationError

from harness.schemas.brand_knowledge import (
    ApprovedPhrase,
    BrandKnowledgeSnapshot,
    BrandLibraryExcerpt,
    PartnerEntry,
    PartnersProgrammeKnowledge,
    RecurringEvent,
)
from harness.services.brand_loader import brands_root, validate_brand_slug

log = structlog.get_logger(__name__)

# Storage caps (state_json size)
_MAX_CONTENT_NOTES_STORED = 16_000
_MAX_LIBRARY_FILES = 12
_MAX_EXCERPT_PER_FILE = 3_000
_MAX_TOTAL_LIBRARY_STORED = 36_000

# Prompt injection cap (formatted block passed to LLMs)
_MAX_PROMPT_KNOWLEDGE_CHARS = 12_000

_LIBRARY_SUFFIXES = {".md", ".txt"}
# Optional local readme in library/ — not meant as narrative knowledge for the model
_LIBRARY_IGNORE_NAMES = {"readme.md", "readme.txt"}


def _as_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _coerce_partners_programme(raw: dict[str, Any]) -> PartnersProgrammeKnowledge:
    """
    Build structured knowledge from a parsed YAML dict.
    Invalid list rows are skipped; the rest of the file still applies.
    """
    partners: list[PartnerEntry] = []
    for i, item in enumerate(raw.get("partners") or []):
        if not isinstance(item, dict):
            log.warning("brand_knowledge.partner_row_not_object", index=i)
            continue
        try:
            partners.append(PartnerEntry.model_validate(item))
        except ValidationError as e:
            log.warning("brand_knowledge.partner_row_skipped", index=i, error=str(e))

    recurring_events: list[RecurringEvent] = []
    for i, item in enumerate(raw.get("recurring_events") or []):
        if not isinstance(item, dict):
            log.warning("brand_knowledge.event_row_not_object", index=i)
            continue
        try:
            recurring_events.append(RecurringEvent.model_validate(item))
        except ValidationError as e:
            log.warning("brand_knowledge.event_row_skipped", index=i, error=str(e))

    approved_language: list[ApprovedPhrase] = []
    for i, item in enumerate(raw.get("approved_language") or []):
        if not isinstance(item, dict):
            log.warning("brand_knowledge.phrase_row_not_object", index=i)
            continue
        try:
            approved_language.append(ApprovedPhrase.model_validate(item))
        except ValidationError as e:
            log.warning("brand_knowledge.phrase_row_skipped", index=i, error=str(e))

    return PartnersProgrammeKnowledge(
        partners=partners,
        recurring_events=recurring_events,
        approved_language=approved_language,
        sensitive_context=_as_str(raw.get("sensitive_context")),
        programme_notes=_as_str(raw.get("programme_notes")),
    )


def load_partners_programme(base: Path) -> tuple[PartnersProgrammeKnowledge, bool]:
    """Parse partners.yaml; return (model, True if the file exists and was read)."""
    path = base / "partners.yaml"
    if not path.is_file():
        return PartnersProgrammeKnowledge(), False
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        log.warning("brand_knowledge.partners_yaml_parse_error", path=str(path), error=str(e))
        return PartnersProgrammeKnowledge(), True
    except OSError as e:
        log.warning("brand_knowledge.partners_read_failed", path=str(path), error=str(e))
        return PartnersProgrammeKnowledge(), False

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        log.warning("brand_knowledge.partners_root_not_mapping", path=str(path))
        return PartnersProgrammeKnowledge(), True

    return _coerce_partners_programme(raw), True


def _read_content_notes(base: Path) -> tuple[str, bool, bool]:
    path = base / "content_notes.md"
    if not path.is_file():
        return "", False, False
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as e:
        log.warning("brand_knowledge.content_notes_read_failed", path=str(path), error=str(e))
        return "", False, False
    if len(text) > _MAX_CONTENT_NOTES_STORED:
        return text[:_MAX_CONTENT_NOTES_STORED], True, True
    return text, True, False


def _load_template_hints(base: Path) -> tuple[dict[str, Any], bool]:
    path = base / "template.yaml"
    if not path.is_file():
        return {}, False
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        log.warning("brand_knowledge.template_yaml_parse_error", path=str(path), error=str(e))
        return {}, True
    except OSError as e:
        log.warning("brand_knowledge.template_read_failed", path=str(path), error=str(e))
        return {}, False

    if raw is None:
        return {}, True
    if isinstance(raw, dict):
        return raw, True
    log.warning("brand_knowledge.template_not_dict", path=str(path))
    return {}, True


def _collect_library_paths(lib_dir: Path) -> list[Path]:
    if not lib_dir.is_dir():
        return []
    files: list[Path] = []
    for p in sorted(lib_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if p.name.casefold() in _LIBRARY_IGNORE_NAMES:
            continue
        if p.suffix.lower() not in _LIBRARY_SUFFIXES:
            continue
        files.append(p)
    return files


def _load_library_excerpts(base: Path) -> tuple[list[BrandLibraryExcerpt], bool]:
    lib = base / "library"
    all_paths = _collect_library_paths(lib)
    paths = all_paths[:_MAX_LIBRARY_FILES]
    if not paths:
        return [], False
    truncated_global = len(all_paths) > len(paths)
    excerpts: list[BrandLibraryExcerpt] = []
    total = 0
    for path in paths:
        if total >= _MAX_TOTAL_LIBRARY_STORED:
            truncated_global = True
            break
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(base).as_posix()
        budget = min(_MAX_EXCERPT_PER_FILE, _MAX_TOTAL_LIBRARY_STORED - total)
        excerpt = raw.strip()
        if not excerpt:
            continue
        file_trunc = len(excerpt) > budget
        if file_trunc:
            excerpt = excerpt[:budget]
        excerpts.append(
            BrandLibraryExcerpt(rel_path=rel, excerpt=excerpt, truncated=file_trunc),
        )
        total += len(excerpt)
    return excerpts, truncated_global


def _structured_has_content(st: PartnersProgrammeKnowledge) -> bool:
    if st.sensitive_context.strip() or st.programme_notes.strip():
        return True
    if st.partners and any(p.name.strip() or p.organisation.strip() for p in st.partners):
        return True
    if st.recurring_events and any(
        e.name.strip() or e.description.strip() or e.messaging_notes.strip() for e in st.recurring_events
    ):
        return True
    if st.approved_language and any(ap.phrase.strip() for ap in st.approved_language):
        return True
    return False


def _template_hints_effective(hints: dict[str, Any]) -> bool:
    for v in hints.values():
        if v is None or v == "":
            continue
        if isinstance(v, dict) and not v:
            continue
        if isinstance(v, list) and not v:
            continue
        return True
    return False


def load_brand_knowledge_snapshot(slug: str, root: Path | None = None) -> dict[str, Any]:
    """
    Load optional knowledge files under brands/<slug>/.

    Missing files yield empty sections. Broken YAML logs a warning and yields empty
    sections for that file. Partial list rows are skipped where possible.
    """
    slug = validate_brand_slug(slug)
    base = (root or brands_root()) / slug
    loaded: list[str] = []

    structured, partners_touched = load_partners_programme(base)
    if partners_touched and _structured_has_content(structured):
        loaded.append("partners.yaml")

    notes, got_notes, notes_trunc = _read_content_notes(base)
    if got_notes and notes.strip():
        loaded.append("content_notes.md")

    template_hints, got_tmpl = _load_template_hints(base)
    if got_tmpl and _template_hints_effective(template_hints):
        loaded.append("template.yaml")

    library_excerpts, lib_trunc = _load_library_excerpts(base)
    if library_excerpts:
        loaded.append("library/")

    snap = BrandKnowledgeSnapshot(
        slug=slug,
        structured=structured,
        content_notes_text=notes,
        content_notes_truncated=notes_trunc,
        template_hints=template_hints,
        library=library_excerpts,
        library_truncated=lib_trunc,
        loaded_paths=loaded,
    )
    return snap.model_dump(mode="json")


def format_knowledge_for_prompt(snapshot: dict[str, Any] | None) -> str:
    """Turn persisted snapshot dict into a single capped block for LLM prompts."""
    if not snapshot:
        return ""
    lines: list[str] = []
    structured_raw = snapshot.get("structured") or {}
    try:
        st = PartnersProgrammeKnowledge.model_validate(structured_raw)
    except ValidationError:
        st = PartnersProgrammeKnowledge()

    if st.programme_notes.strip():
        lines.append("Programme / positioning notes:\n" + st.programme_notes.strip())
    if st.sensitive_context.strip():
        lines.append(
            "Sensitive context (treat carefully; do not over-claim or name people without justification):\n"
            + st.sensitive_context.strip(),
        )
    for ev in st.recurring_events:
        if not (ev.name or ev.description or ev.messaging_notes):
            continue
        chunk = []
        if ev.name:
            chunk.append(f"Event/campaign: {ev.name}")
        if ev.timing:
            chunk.append(f"Timing: {ev.timing}")
        if ev.description:
            chunk.append(ev.description)
        if ev.messaging_notes:
            chunk.append(f"Messaging: {ev.messaging_notes}")
        lines.append("\n".join(chunk))
    for p in st.partners:
        if not (p.name or p.organisation):
            continue
        parts = []
        if p.name:
            parts.append(p.name + (f" ({p.organisation})" if p.organisation else ""))
        if p.role:
            parts.append(f"Role: {p.role}")
        if p.website:
            parts.append(f"Website: {p.website}")
        if p.notes:
            parts.append(p.notes)
        if p.sensitivity and p.sensitivity != "normal":
            parts.append(f"Sensitivity: {p.sensitivity}")
        lines.append("Partner: " + " | ".join(parts))
    for ap in st.approved_language:
        if ap.phrase.strip():
            ctx = f" ({ap.context})" if ap.context else ""
            lines.append(f"Approved/preferred phrasing{ctx}: {ap.phrase.strip()}")

    notes = str(snapshot.get("content_notes_text") or "").strip()
    if notes:
        lines.append("Content notes (markdown):\n" + notes)

    for hint_key, hint_val in (snapshot.get("template_hints") or {}).items():
        if hint_val is None or hint_val == "":
            continue
        if isinstance(hint_val, (list, dict)):
            lines.append(f"Template hint — {hint_key}: {hint_val!s}")
        else:
            lines.append(f"Template hint — {hint_key}: {hint_val}")

    for doc in snapshot.get("library") or []:
        if not isinstance(doc, dict):
            continue
        rel = doc.get("rel_path", "document")
        excerpt = str(doc.get("excerpt") or "").strip()
        if not excerpt:
            continue
        suf = "…" if doc.get("truncated") else ""
        lines.append(f"Library file [{rel}]:\n{excerpt}{suf}")

    body = "\n\n".join(lines).strip()
    if len(body) > _MAX_PROMPT_KNOWLEDGE_CHARS:
        body = body[:_MAX_PROMPT_KNOWLEDGE_CHARS] + "\n… [brand knowledge truncated for prompt size]"
    return body
