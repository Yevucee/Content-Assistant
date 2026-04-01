"""Load BrandConfig and SourceListConfig from YAML on disk."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from harness.schemas.brand import BrandConfig
from harness.schemas.sources import SourceListConfig


def brands_root() -> Path:
    """
    Resolve directory containing `<slug>/brand.yaml`.

    Order: BRANDS_ROOT env → ./brands from cwd → repo-style layout next to harness (editable).
    """
    if env := os.environ.get("BRANDS_ROOT"):
        p = Path(env)
        if not p.is_dir():
            msg = f"BRANDS_ROOT is not a directory: {p}"
            raise FileNotFoundError(msg)
        return p

    cwd_candidate = Path.cwd() / "brands"
    if cwd_candidate.is_dir():
        return cwd_candidate.resolve()

    # Editable / dev: harness/services/brand_loader.py → parents[2] is repo root
    here = Path(__file__).resolve()
    repo_like = here.parents[2]
    if (repo_like / "brands").is_dir():
        return (repo_like / "brands").resolve()

    msg = "Cannot find brands/: set BRANDS_ROOT or run from a directory containing brands/"
    raise FileNotFoundError(msg)


def list_brand_slugs(root: Path | None = None) -> list[str]:
    """Discover brand slugs as immediate subdirectories containing brand.yaml."""
    base = root or brands_root()
    if not base.is_dir():
        return []
    slugs: list[str] = []
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / "brand.yaml").is_file():
            slugs.append(child.name)
    return slugs


def load_brand_pair(
    slug: str,
    root: Path | None = None,
) -> tuple[BrandConfig, SourceListConfig]:
    """Load brand.yaml and sources.yaml for slug."""
    base = root or brands_root()
    brand_path = base / slug / "brand.yaml"
    sources_path = base / slug / "sources.yaml"
    if not brand_path.is_file():
        msg = f"Missing brand.yaml for slug={slug} at {brand_path}"
        raise FileNotFoundError(msg)

    with brand_path.open(encoding="utf-8") as f:
        raw_brand = yaml.safe_load(f) or {}
    if "slug" not in raw_brand:
        raw_brand["slug"] = slug

    try:
        brand = BrandConfig.model_validate(raw_brand)
    except ValidationError as e:
        raise ValueError(f"Invalid brand.yaml for {slug}: {e}") from e

    sources_raw: dict = {}
    if sources_path.is_file():
        with sources_path.open(encoding="utf-8") as f:
            sources_raw = yaml.safe_load(f) or {}
    sources = SourceListConfig.model_validate(sources_raw)

    return brand, sources


def load_brand_config(slug: str, root: Path | None = None) -> BrandConfig:
    """Convenience: BrandConfig only."""
    brand, _ = load_brand_pair(slug, root)
    return brand
