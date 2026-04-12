"""Brand listing from YAML."""

from fastapi import APIRouter

from harness.services import brand_loader
from harness.schemas.brand import BrandConfig

router = APIRouter()

_PLACEHOLDER_DESCS = frozenset(
    {
        "",
        ".",
        "…",
        "...",
        "—",
        "-",
        "–",
        "n/a",
        "na",
        "tbd",
        "todo",
        "none",
        "placeholder",
        "lorem ipsum",
    }
)


def _clean_public_description(description: str | None) -> str | None:
    """Omit placeholder-like descriptions from API list responses."""
    if description is None:
        return None
    d = description.strip()
    if not d:
        return None
    if d.lower() in _PLACEHOLDER_DESCS:
        return None
    if len(d) <= 3 and all(ch in ".…—-_ " for ch in d):
        return None
    return d


@router.get("")
def list_brands() -> list[dict]:
    """Return minimal brand info for each configured slug."""
    out: list[dict] = []
    for slug in brand_loader.list_brand_slugs():
        brand, _sources = brand_loader.load_brand_pair(slug)
        b: BrandConfig = brand
        desc = _clean_public_description(b.description)
        out.append(
            {
                "slug": b.slug,
                "name": b.name,
                "description": desc,
            }
        )
    return out
