"""Read/write active ``BrandTemplateProfile`` at ``brands/<slug>/brand_template.yaml``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import ValidationError

from harness.schemas.brand_template import BrandTemplateProfile
from harness.services.brand_loader import brands_root, validate_brand_slug

log = structlog.get_logger(__name__)

ACTIVE_BRAND_TEMPLATE_FILENAME = "brand_template.yaml"


def active_brand_template_path(slug: str, root: Path | None = None) -> Path:
    s = validate_brand_slug(slug)
    base = (root or brands_root()).resolve()
    return (base / s / ACTIVE_BRAND_TEMPLATE_FILENAME).resolve()


def load_active_brand_template(slug: str) -> BrandTemplateProfile | None:
    """Return validated profile or None if missing; raises on invalid YAML or schema."""
    path = active_brand_template_path(slug)
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        msg = f"{path.name}: root must be a mapping, got {type(raw).__name__}"
        raise ValueError(msg)
    return BrandTemplateProfile.model_validate(raw)


def load_active_brand_template_optional(slug: str) -> tuple[BrandTemplateProfile | None, str | None]:
    """Same as load, but return (None, error_message) instead of raising."""
    path = active_brand_template_path(slug)
    if not path.is_file():
        return None, None
    try:
        return load_active_brand_template(slug), None
    except (ValidationError, yaml.YAMLError, OSError) as e:
        log.warning("brand_template.load_failed", slug=slug, path=str(path), error=str(e))
        return None, str(e)


def save_active_brand_template(slug: str, profile: BrandTemplateProfile) -> Path:
    """
    Validate, then atomically replace ``brand_template.yaml`` (write temp + rename).
    """
    path = active_brand_template_path(slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = profile.model_dump(mode="json")
    text = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    log.info("brand_template.saved", slug=slug, path=str(path))
    return path
