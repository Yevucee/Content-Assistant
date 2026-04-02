"""Channel-specific outputs derived from one shared editorial package."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LinkedInChannelOutput(BaseModel):
    primary: str = ""
    punchy: str = Field(default="", description="Shorter, higher-energy variant.")
    teaser: str = Field(default="", description="Teaser / hook-forward variant.")
    hashtags: list[str] = Field(default_factory=list)


class FacebookPost(BaseModel):
    primary: str = ""
    community: str = Field(
        default="",
        description="Optional warmer, conversational variant.",
    )


class InstagramCaption(BaseModel):
    primary: str = ""
    short: str = ""
    hashtags: list[str] = Field(default_factory=list)


class SocialPostAngle(BaseModel):
    title: str = ""
    hook: str = ""
    platform_notes: str = ""


class SocialIdeaPack(BaseModel):
    angles: list[SocialPostAngle] = Field(default_factory=list)


class ImageConcept(BaseModel):
    concept: str = ""
    prompt_text: str = ""
    mood: str = ""
    aspect_ratio_hint: str = ""
    signage_notes: str = Field(
        default="",
        description="Guidance on text/logo usage in-frame.",
    )


class ChannelOutputBundle(BaseModel):
    """
    All channel adapters write here; legacy fields (linkedin_post, image_prompts)
    remain in GraphState for backward compatibility.
    """

    linkedin: LinkedInChannelOutput = Field(default_factory=LinkedInChannelOutput)
    facebook: FacebookPost = Field(default_factory=FacebookPost)
    instagram: InstagramCaption = Field(default_factory=InstagramCaption)
    social_ideas: SocialIdeaPack = Field(default_factory=SocialIdeaPack)
    image_concepts: list[ImageConcept] = Field(default_factory=list)
