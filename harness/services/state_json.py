"""Serialise graph / pipeline state for DB storage."""

from __future__ import annotations

import json
from typing import Any


def state_to_json_blob(state: dict[str, Any]) -> str:
    """Dump state dict to JSON string (handles basic Python types)."""
    return json.dumps(state, default=str, ensure_ascii=False)


def json_blob_to_state(blob: str) -> dict[str, Any]:
    """Parse DB JSON string to dict."""
    if not blob or blob == "{}":
        return {}
    return json.loads(blob)
