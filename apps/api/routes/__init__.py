"""API routers."""

from fastapi import APIRouter

from apps.api.routes import brands, health, runs

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(brands.router, prefix="/brands", tags=["brands"])
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
