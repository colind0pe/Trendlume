from dataclasses import dataclass
from enum import StrEnum


class ContentMode(StrEnum):
    """Stable values shared by task validation and template capabilities."""

    GENERATED_IMAGE = "generated_image"
    GENERATED_VIDEO = "generated_video"
    ONLINE_ASSET = "online_asset"
    UPLOADED_ASSET = "uploaded_asset"
    STATIC = "static"


LEGACY_CONTENT_MODE = "trend_asset"


@dataclass(frozen=True)
class ContentModeCapability:
    """Runtime contract for one visual source mode."""

    template_types: frozenset[str]
    media_kind: str


CONTENT_MODE_CAPABILITIES: dict[ContentMode, ContentModeCapability] = {
    ContentMode.GENERATED_IMAGE: ContentModeCapability(
        template_types=frozenset({"image"}),
        media_kind="image",
    ),
    ContentMode.GENERATED_VIDEO: ContentModeCapability(
        template_types=frozenset({"video"}),
        media_kind="video",
    ),
    ContentMode.ONLINE_ASSET: ContentModeCapability(
        template_types=frozenset({"video"}),
        media_kind="video",
    ),
    ContentMode.UPLOADED_ASSET: ContentModeCapability(
        template_types=frozenset({"image", "video", "asset"}),
        media_kind="asset",
    ),
    ContentMode.STATIC: ContentModeCapability(
        template_types=frozenset({"static"}),
        media_kind="none",
    ),
}


def resolve_content_mode(
    mode: str | ContentMode | None,
    *,
    template_type: str | None = None,
    visual_mode: str | None = None,
) -> str:
    """Resolve current and legacy task fields to one content-mode value."""

    if mode == LEGACY_CONTENT_MODE:
        return (
            ContentMode.GENERATED_VIDEO.value
            if template_type == "video"
            else ContentMode.GENERATED_IMAGE.value
        )
    if isinstance(mode, ContentMode):
        return mode.value
    if mode:
        return str(mode)
    if template_type == "static":
        return ContentMode.STATIC.value
    if template_type == "asset":
        return ContentMode.UPLOADED_ASSET.value
    return (
        ContentMode.GENERATED_VIDEO.value
        if visual_mode == "video"
        else ContentMode.GENERATED_IMAGE.value
    )


def get_content_mode_capability(
    mode: str | ContentMode | None,
) -> ContentModeCapability | None:
    if mode is None:
        return None
    try:
        return CONTENT_MODE_CAPABILITIES[ContentMode(mode)]
    except ValueError:
        return None


def supported_content_modes(template_type: str) -> list[str]:
    return [
        mode.value
        for mode, capability in CONTENT_MODE_CAPABILITIES.items()
        if template_type in capability.template_types
    ]


def is_content_mode_supported(mode: str | ContentMode | None, template_type: str) -> bool:
    capability = get_content_mode_capability(mode)
    return capability is not None and template_type in capability.template_types
