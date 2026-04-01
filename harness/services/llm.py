"""Thin OpenAI-compatible client for JSON-shaped completions."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import structlog
from openai import OpenAI

log = structlog.get_logger(__name__)


def openai_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", "local"),
        base_url=os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:9888/v1"),
    )


def default_model() -> str:
    return os.environ.get("DEFAULT_MODEL", "local-8b")


def strip_json_fence(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", t, re.I)
    if m:
        return m.group(1).strip()
    return t


def parse_json_object(text: str) -> dict[str, Any]:
    raw = strip_json_fence(text)
    return json.loads(raw)


def chat_json(*, system: str, user: str, temperature: float = 0.35) -> dict[str, Any]:
    """Chat completion; parse response as JSON object."""
    client = openai_client()
    model = default_model()
    log.info("llm.chat_json.request", model=model)
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        log.warning("llm.empty_response")
        return {}
    try:
        return parse_json_object(text)
    except json.JSONDecodeError as e:
        log.warning("llm.json_parse_failed", error=str(e), sample=text[:200])
        return {}


def chat_text(
    *,
    system: str,
    user: str,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> str:
    """Chat completion; return raw assistant text (e.g. markdown)."""
    client = openai_client()
    model = default_model()
    mt = max_tokens
    if mt is None:
        mt_env = os.environ.get("CONTENT_MAX_TOKENS")
        if mt_env:
            try:
                mt = int(mt_env)
            except ValueError:
                mt = None
    log.info("llm.chat_text.request", model=model, max_tokens=mt)
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if mt is not None:
        kwargs["max_tokens"] = mt
    resp = client.chat.completions.create(**kwargs)
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        log.warning("llm.chat_text.empty")
    return text
