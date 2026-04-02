"""Channel assets: LinkedIn, Facebook, Instagram, social angles, image concepts, metadata."""

from __future__ import annotations

import structlog

from harness.schemas.content import ImagePromptSet, LinkedInPost
from harness.schemas.channel_outputs import ChannelOutputBundle
from harness.schemas.pipeline import PipelineStage
from harness.services import (
    gen_facebook,
    gen_image_concepts,
    gen_instagram,
    gen_linkedin_channel,
    gen_metadata,
    gen_social_ideas,
)
from harness.services.state_helpers import brand_snapshot
from harness.state.graph_state import GraphState

log = structlog.get_logger(__name__)


def generate_channel_assets(state: GraphState) -> dict:
    slug = state.get("brand_slug", "")
    log.info("node.generate_channel_assets", slug=slug)
    brand = brand_snapshot(state)
    draft = state.get("article_draft") or {}
    brief = state.get("editorial_brief") or {}

    li_ch = gen_linkedin_channel.generate_linkedin_channel(brand, draft, brief)
    li = LinkedInPost(text=li_ch.primary, hashtags=li_ch.hashtags)

    fb = gen_facebook.generate_facebook_post(brand, draft, brief)
    ig = gen_instagram.generate_instagram_caption(brand, draft, brief)
    ideas = gen_social_ideas.generate_social_idea_pack(brand, draft, brief)
    concepts = gen_image_concepts.generate_image_concepts(brand, draft, brief)

    prompt_strings = [c.prompt_text for c in concepts if c.prompt_text.strip()]
    style_notes = concepts[0].mood if concepts else ""
    if prompt_strings:
        images = ImagePromptSet(prompts=prompt_strings[:6], style_notes=style_notes[:4000])
    else:
        from harness.services import gen_image_prompts

        images = gen_image_prompts.generate_image_prompts(brand, draft, brief)

    meta = gen_metadata.generate_metadata(brand, draft, brief)

    bundle = ChannelOutputBundle(
        linkedin=li_ch,
        facebook=fb,
        instagram=ig,
        social_ideas=ideas,
        image_concepts=concepts,
    )

    return {
        "linkedin_post": li.model_dump(mode="json"),
        "image_prompts": images.model_dump(mode="json"),
        "metadata_package": meta.model_dump(mode="json"),
        "channel_output_bundle": bundle.model_dump(mode="json"),
        "stage": PipelineStage.ASSETS_READY.value,
    }
