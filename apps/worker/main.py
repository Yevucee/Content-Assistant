"""Worker entrypoint — scheduler and optional one-shot pipeline."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Repo root on path for `apps` and `harness`
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")

from harness.utils.logging import configure_logging


def main() -> None:
    configure_logging(
        json_logs=os.environ.get("LOG_FORMAT", "console") == "json",
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
    import structlog

    from apps.worker.scheduler import run_scheduler_loop

    log = structlog.get_logger(__name__)
    log.info("worker.starting", hint="weekly schedule runs in Milestone 5 / APScheduler")
    asyncio.run(run_scheduler_loop())


if __name__ == "__main__":
    main()
