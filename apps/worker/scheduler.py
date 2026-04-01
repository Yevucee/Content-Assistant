"""Weekly scheduling — APScheduler stub for Milestone 1."""

from __future__ import annotations

import asyncio
import os

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

log = structlog.get_logger(__name__)


async def scheduled_tick() -> None:
    """
    Placeholder: will enumerate brands and call create_and_run_phase1 per brand.

    Milestone 5 wires DATABASE_URL and optional Railway cron instead of in-process cron.
    """
    log.info("scheduler.tick_stub", message="no automatic runs in Milestone 1")


async def run_scheduler_loop() -> None:
    """Start asyncio scheduler or idle until shutdown."""
    cron = os.environ.get("WEEKLY_CRON", "")
    if not cron or os.environ.get("DISABLE_SCHEDULER", "").lower() in ("1", "true", "yes"):
        log.info("scheduler.disabled", reason="WEEKLY_CRON empty or DISABLE_SCHEDULER set")
        while True:
            await asyncio.sleep(3600)

    parts = cron.split()
    if len(parts) != 5:
        log.warning("scheduler.invalid_cron", cron=cron)
        while True:
            await asyncio.sleep(3600)

    minute, hour, day, month, dow = parts
    trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_tick, trigger=trigger, id="weekly_content", replace_existing=True)
    scheduler.start()
    log.info("scheduler.started", cron=cron)

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        scheduler.shutdown(wait=False)
        raise
