"""Save uploaded run files under data/uploads/{run_id}/ (local only)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

# Truncate very large extractions for pipeline / DB payload size
MAX_STORED_SOURCE_CHARS = 100_000
# Multipart upload cap (``POST /runs/trigger/upload``)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def uploads_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "data" / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_filename(name: str, max_len: int = 120) -> str:
    base = Path(name).name
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", base)
    if not base or base in (".", "_"):
        base = "upload.bin"
    return base[:max_len]


def save_upload_bytes(run_id: uuid.UUID, filename: str, data: bytes) -> str:
    """
    Write file; return relative path from repo root: data/uploads/{id}/{file}.
    """
    run_dir = uploads_root() / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / safe_filename(filename)
    path.write_bytes(data)
    return str(path.relative_to(Path(__file__).resolve().parents[2]))
