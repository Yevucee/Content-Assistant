"""Brand listing from YAML."""

from fastapi import APIRouter

from harness.services import brand_loader
from harness.schemas.brand import BrandConfig

router = APIRouter()


@router.get("")
def list_brands() -> list[dict]:
    """Return minimal brand info for each configured slug."""
    out: list[dict] = []
    for slug in brand_loader.list_brand_slugs():
        brand, _sources = brand_loader.load_brand_pair(slug)
        b: BrandConfig = brand
        out.append(
            {
                "slug": b.slug,
                "name": b.name,
                "description": b.description,
            }
        )
    return out
