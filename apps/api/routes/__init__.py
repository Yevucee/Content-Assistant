"""API routers."""

import os

from fastapi import APIRouter

from apps.api.routes import brand_template, brands, debug_temp, health, runs

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
if os.environ.get("ENABLE_DEBUG_ROUTES", "").strip().lower() in ("1", "true", "yes", "on"):
    api_router.include_router(debug_temp.router)
api_router.include_router(brands.router, prefix="/brands", tags=["brands"])
api_router.include_router(brand_template.router, prefix="/brands", tags=["brand-template"])
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
