"""Brand configuration schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WordPressSettings(BaseModel):
    """WordPress REST API connection; secrets via env key names only in YAML."""

    site_url: str = Field(description="Base URL, e.g. https://example.com")
    username_env: str = Field(
        default="WORDPRESS_USERNAME",
        description="Env var name holding WP username",
    )
    application_password_env: str = Field(
        default="WORDPRESS_APPLICATION_PASSWORD",
        description="Env var name holding WP application password",
    )


class LinkedInStyle(BaseModel):
    """Voice/format hints for LinkedIn companion copy."""

    tone_notes: str = ""
    max_chars_hint: int | None = 3000
    hashtag_policy: str = "minimal"


class ImageStylePreferences(BaseModel):
    """Hints for image prompt generation."""

    style_notes: str = ""
    aspect_ratio: str = "16:9"
    negative_prompts: list[str] = Field(default_factory=list)


class MetadataPreferences(BaseModel):
    """Defaults for SEO/slug behaviour."""

    title_suffix: str | None = None
    default_categories: list[str] = Field(default_factory=list)


class ApprovalSettings(BaseModel):
    """Who/when approval applies (v1: flags only)."""

    require_human_approval: bool = True
    notify_email_env: str | None = Field(
        default=None, description="Optional env var for notify email list"
    )


class BrandConfig(BaseModel):
    """Full brand profile loaded from YAML + merged sources."""

    slug: str
    name: str
    description: str = ""
    tone: str = ""
    audience: str = ""
    key_themes: list[str] = Field(default_factory=list)
    banned_phrases: list[str] = Field(default_factory=list)
    cta_style: str = ""
    linkedin: LinkedInStyle = Field(default_factory=LinkedInStyle)
    image: ImageStylePreferences = Field(default_factory=ImageStylePreferences)
    metadata: MetadataPreferences = Field(default_factory=MetadataPreferences)
    wordpress: WordPressSettings | None = None
    approval: ApprovalSettings = Field(default_factory=ApprovalSettings)

    extra: dict[str, Any] = Field(default_factory=dict, description="Forward-compatible bag")
