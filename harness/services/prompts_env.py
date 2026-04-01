"""Shared Jinja2 environment for harness/prompts."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def get_prompt_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPT_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",)),
    )
