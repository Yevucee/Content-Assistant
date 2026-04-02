"""How a run enters the shared pipeline and what it should produce."""

from __future__ import annotations

from enum import Enum


class RunMode(str, Enum):
    """
    Entry path into the unified pipeline.

    website_discovery and existing_blog_style run a capped site/blog sample
    then stop at review (proposed template + opportunities only; no article draft).
    """

    SOURCE_DRIVEN = "source_driven"
    IDEA_DRIVEN = "idea_driven"
    WEBSITE_DISCOVERY = "website_discovery"
    DOCUMENT_DRIVEN = "document_driven"
    TRANSCRIPT_DRIVEN = "transcript_driven"
    EXISTING_BLOG_STYLE = "existing_blog_style"
    MIXED = "mixed"


class RunIntent(str, Enum):
    """What outputs the run should emphasize (guides adapter selection later)."""

    FULL_CONTENT_PACKAGE = "full_content_package"
    BLOG_ONLY = "blog_only"
    SOCIAL_ONLY = "social_only"
    BLOG_PLUS_SOCIAL = "blog_plus_social"
    IDEA_GENERATION_ONLY = "idea_generation_only"
    BRAND_DISCOVERY_ONLY = "brand_discovery_only"


DEFAULT_RUN_MODE = RunMode.SOURCE_DRIVEN
DEFAULT_RUN_INTENT = RunIntent.BLOG_PLUS_SOCIAL
