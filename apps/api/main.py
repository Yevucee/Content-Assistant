"""FastAPI application — API and future server-rendered review UI."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from apps.api.routes import api_router
from apps.api.routes.review_ui import router as review_ui_router
from harness.services.db import init_db
from harness.utils.logging import configure_logging

load_dotenv()

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_format = os.environ.get("LOG_FORMAT", "console")
    configure_logging(
        json_logs=log_format == "json",
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
    # Hosted diagnostics: skip DB init when isolating startup (e.g. /ping vs DB connectivity).
    if os.environ.get("SKIP_INIT_DB_ON_STARTUP") != "1":
        await init_db()
    yield


app = FastAPI(title="Content Harness API", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)
app.include_router(review_ui_router, prefix="/review", tags=["review"])


@app.get("/ping")
async def ping():
    return {"ok": True, "route": "ping"}

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Minimal landing page until review UI (Milestone 4)."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {"title": "Content Harness", "app_base_url": os.environ.get("APP_BASE_URL", "")},
    )
