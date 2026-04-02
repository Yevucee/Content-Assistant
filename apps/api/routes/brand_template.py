"""Active brand template (``brand_template.yaml``) — read, preview merge, replace."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from harness.schemas.brand_template import (
    BrandTemplateProfile,
    BrandTemplatePromptSource,
    BrandTemplateResolution,
    merge_template_profiles,
)
from harness.services import brand_loader
from harness.services import brand_template_storage

router = APIRouter()


def _load_brand_pair_http(slug: str):
    try:
        return brand_loader.load_brand_pair(slug)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class SaveBrandTemplateBody(BaseModel):
    """Explicit save; existing files require ``confirm_replace``."""

    profile: BrandTemplateProfile
    confirm_replace: bool = Field(
        default=False,
        description="Must be true if brands/<slug>/brand_template.yaml already exists.",
    )


@router.get("/{slug}/brand-template")
def get_active_brand_template(slug: str) -> dict:
    """Return the saved active profile, or null if no file."""
    _load_brand_pair_http(slug)
    prof = brand_template_storage.load_active_brand_template(slug)
    root = brand_loader.brands_root()
    path = brand_template_storage.active_brand_template_path(slug, root=root)
    return {
        "slug": slug,
        "active_profile": prof.model_dump(mode="json") if prof else None,
        "path_relative_to_brands_root": f"{slug}/brand_template.yaml",
        "file_exists": path.is_file(),
    }


@router.get("/{slug}/brand-template/resolved-preview")
def preview_resolved_brand_template(slug: str) -> dict:
    """Show base (from ``brand.yaml``), optional active file, and merged resolution."""
    brand, _ = _load_brand_pair_http(slug)
    base = BrandTemplateProfile.from_brand_config_dict(brand.model_dump(mode="json"))
    active = brand_template_storage.load_active_brand_template(slug)
    resolved = merge_template_profiles(base, active) if active is not None else base
    resolution = BrandTemplateResolution(
        prompt_template_source=(
            BrandTemplatePromptSource.ACTIVE_FILE if active is not None else BrandTemplatePromptSource.BRAND_YAML_ONLY
        ),
        active_template_relpath=f"{slug}/brand_template.yaml" if active is not None else None,
        active_file_existed_at_load=active is not None,
    )
    return {
        "slug": slug,
        "from_brand_yaml": base.model_dump(mode="json"),
        "from_active_file": active.model_dump(mode="json") if active else None,
        "resolved": resolved.model_dump(mode="json"),
        "resolution": resolution.model_dump(mode="json"),
    }


@router.put("/{slug}/brand-template")
def put_active_brand_template(slug: str, body: SaveBrandTemplateBody) -> dict:
    """Write validated profile to ``brand_template.yaml`` (atomic replace)."""
    _load_brand_pair_http(slug)
    path = brand_template_storage.active_brand_template_path(slug)
    if path.is_file() and not body.confirm_replace:
        raise HTTPException(
            status_code=409,
            detail="brand_template.yaml already exists for this brand. "
            "Send confirm_replace=true after review, or delete the file manually.",
        )
    brand_template_storage.save_active_brand_template(slug, body.profile)
    root = brand_loader.brands_root()
    rel = path.resolve().relative_to(root.resolve())
    return {"ok": True, "path": str(rel)}
