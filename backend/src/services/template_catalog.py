"""Bundled vertical template catalog and safe placeholder handling.

The Demo templates intentionally use a very small placeholder DSL rather than a
general purpose template engine.  Keeping the parser here makes previews and
final rendering share exactly the same validation and escaping rules.
"""

from __future__ import annotations

import html
import math
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from src.domain.content_modes import (
    get_content_mode_capability,
    supported_content_modes,
)

_PARAM_PATTERN = re.compile(
    r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?::\s*([a-z]+))?\s*(?:=\s*([^}]+?))?\s*\}\}"
)
_PRESET_PARAMS = {"title", "text", "narration", "image", "index", "subtitle"}
_SUPPORTED_TYPES = {"text", "number", "color", "bool"}
_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_DEFAULT_MEDIA_SIZE = (1024, 1024)
_MEDIA_WIDTH_META = "template:media-width"
_MEDIA_HEIGHT_META = "template:media-height"
_VIDEO_FRAME_META = {
    "x": "template:video-frame-x",
    "y": "template:video-frame-y",
    "width": "template:video-frame-width",
    "height": "template:video-frame-height",
}

TEMPLATE_NAMES_ZH = {
    # 9:16 (竖屏)
    "image_gallery_matted": "画廊留白展卡",
    "image_editorial_warm": "暖调人文社论",
    "image_frosted_ambient": "磨砂微光视窗",
    "static_editorial_quote": "质感金句引言",
    "static_bulletin_flash": "动态快讯简报",
    "video_cinema_scope": "电影宽幅遮幅",
    "video_full_overlay": "沉浸全屏字幕",

    # 16:9 (横屏)
    "image_wide_minimal": "横屏极简视窗",
    "image_wide_cinema": "横屏电影胶片",
    "image_wide_editorial": "横屏深度专栏",
    "static_wide_bulletin": "横屏焦点快报",
    "video_wide_full": "横屏全景沉浸",
    "video_wide_cinema_scope": "横屏影院宽幅",

    # 1:1 (正方)
    "image_square_matted": "正方雅致留白",
    "image_square_editorial": "正方精选社论",
    "image_square_frosted": "正方磨砂卡片",
    "static_square_quote": "正方金句卡片",
    "video_square_full": "正方全景画幅",
    "video_square_card": "正方杂志动效",

}

TEMPLATE_PARAM_LABELS_ZH = {
    "author": "创作者署名",
    "describe": "副标题说明",
    "brand": "品牌标识",
    "tag": "标签文案",
    "source": "来源引文",
    "theme_color": "主题配色",
    "title": "主标题",
    "subtitle": "副标题",
    "accent_color": "强调色彩",
    "background_color": "背景色彩",
    "font_size": "字号大小",
    "date": "日期标注",
}


class _MediaMetaParser(HTMLParser):
    """Read the media dimensions declared by a bundled HTML template."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attributes = {key.lower(): value or "" for key, value in attrs if key}
        name = attributes.get("name", "").strip().lower()
        if name not in {_MEDIA_WIDTH_META, _MEDIA_HEIGHT_META, *_VIDEO_FRAME_META.values()}:
            return
        try:
            value = int(attributes.get("content", "").strip())
        except (TypeError, ValueError):
            return
        allows_zero = name in {_VIDEO_FRAME_META["x"], _VIDEO_FRAME_META["y"]}
        if value > 0 or (allows_zero and value == 0):
            self.values[name] = value


def parse_media_size(template: str) -> tuple[int, int]:
    """Return the media size declared in a template, with a safe default."""
    parser = _MediaMetaParser()
    try:
        parser.feed(template)
        parser.close()
    except Exception:
        return _DEFAULT_MEDIA_SIZE

    width = parser.values.get(_MEDIA_WIDTH_META)
    height = parser.values.get(_MEDIA_HEIGHT_META)
    if width and height:
        return width, height
    return _DEFAULT_MEDIA_SIZE


def parse_video_frame(
    template: str,
    canvas_size: tuple[int, int] = (1080, 1920),
) -> tuple[int, int, int, int]:
    """Return a validated display frame for dynamic video templates.

    ``media_width``/``media_height`` describe the source rendition requested
    from a provider.  The video frame is a separate canvas-level contract so
    a source can be cropped into a deliberate slot without stretching it.
    Invalid or incomplete declarations intentionally fall back to the full
    template canvas.
    """
    parser = _MediaMetaParser()
    try:
        parser.feed(template)
        parser.close()
    except Exception:
        parser.values.clear()

    canvas_width, canvas_height = canvas_size
    fallback = (0, 0, canvas_width, canvas_height)
    try:
        frame = tuple(parser.values[_VIDEO_FRAME_META[key]] for key in ("x", "y", "width", "height"))
    except KeyError:
        return fallback
    x, y, width, height = frame
    if (
        x < 0
        or y < 0
        or width <= 0
        or height <= 0
        or x + width > canvas_width
        or y + height > canvas_height
        or any(value % 2 for value in frame)
    ):
        return fallback
    return frame


def _parse_default(param_type: str, raw: str | None) -> Any:
    if raw is None:
        return {"text": "", "number": 0, "color": "#000000", "bool": False}.get(
            param_type, ""
        )
    value = raw.strip()
    if param_type == "number":
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            return 0
    if param_type == "bool":
        return value.lower() in {"true", "1", "yes", "on"}
    if param_type == "color":
        return value if value.startswith("#") else f"#{value}"
    return value


def parse_parameters(template: str) -> list[dict[str, Any]]:
    """Return unique user-editable parameters in first-seen order."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _PARAM_PATTERN.finditer(template):
        name, raw_type, raw_default = match.groups()
        if name in _PRESET_PARAMS or name in seen:
            continue
        param_type = raw_type if raw_type in _SUPPORTED_TYPES else "text"
        param_label = TEMPLATE_PARAM_LABELS_ZH.get(name, name.replace("_", " ").strip().title())
        found.append(
            {
                "name": name,
                "type": param_type,
                "default": _parse_default(param_type, raw_default),
                "label": param_label,
            }
        )
        seen.add(name)
    return found


def _safe_value(param_type: str, value: Any) -> str:
    """Validate a DSL value and return an HTML/CSS-safe string."""
    if value is None:
        return ""
    if param_type == "number":
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0
        if not math.isfinite(number):
            number = 0
        return str(int(number)) if number.is_integer() else str(number)
    if param_type == "bool":
        if isinstance(value, str):
            return "true" if value.strip().lower() in {"true", "1", "yes", "on"} else "false"
        return "true" if bool(value) else "false"
    if param_type == "color":
        candidate = str(value)
        if not candidate.startswith("#"):
            candidate = f"#{candidate}"
        return candidate if _COLOR_PATTERN.fullmatch(candidate) else "#000000"
    return html.escape(str(value), quote=True)


def render_template_html(template: str, values: dict[str, Any]) -> str:
    """Replace placeholders with validated values and HTML-escaped text."""
    schema = {item["name"]: item for item in parse_parameters(template)}

    def replace(match: re.Match[str]) -> str:
        name, raw_type, raw_default = match.groups()
        param_type = raw_type if raw_type in _SUPPORTED_TYPES else schema.get(name, {}).get("type", "text")
        if name in values:
            return _safe_value(param_type, values[name])
        return _safe_value(param_type, _parse_default(param_type, raw_default))

    return _PARAM_PATTERN.sub(replace, template)


class TemplateCatalog:
    """Discover and resolve bundled templates across multiple canvas resolutions."""

    SUPPORTED_SIZES = ("1080x1920", "1920x1080", "1080x1080")

    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parent.parent.parent / "templates"
        self._cache: dict[str, dict[str, Any]] | None = None
        self._video_frames: dict[str, tuple[int, int, int, int]] = {}

    @staticmethod
    def _template_type(stem: str) -> str:
        prefix = stem.split("_", 1)[0].lower()
        return prefix if prefix in {"image", "video", "static", "asset"} else "image"

    @staticmethod
    def _aspect_ratio_from_size(width: int, height: int) -> str:
        if width == height:
            return "1:1"
        return "16:9" if width > height else "9:16"

    @staticmethod
    def _supported_modes(template_type: str) -> list[str]:
        return supported_content_modes(template_type)

    def _find_preview(self, stem: str, size: str = "1080x1920") -> str | None:
        size_preview_dir = self.root / "previews" / size
        for suffix in (".png", ".jpg", ".jpeg", ".webp"):
            candidate = size_preview_dir / f"{stem}{suffix}"
            if candidate.is_file():
                return f"previews/{size}/{candidate.name}"
        # Fallback to root previews or 1080x1920
        fallback_dir = self.root / "previews" / "1080x1920"
        for suffix in (".png", ".jpg", ".jpeg", ".webp"):
            candidate = fallback_dir / f"{stem}{suffix}"
            if candidate.is_file():
                return f"previews/1080x1920/{candidate.name}"
        return None

    def scan(
        self, aspect_ratio: str | None = None, content_mode: str | None = None
    ) -> list[dict[str, Any]]:
        if self._cache is not None:
            active_items = list(self._cache.values())
            if aspect_ratio:
                active_items = [item for item in active_items if item.get("aspect_ratio") == aspect_ratio]
            if content_mode:
                active_items = [
                    item for item in active_items
                    if content_mode in item.get("supported_content_modes", [])
                ]
            return active_items

        items: dict[str, dict[str, Any]] = {}
        for size in self.SUPPORTED_SIZES:
            template_dir = self.root / size
            if not template_dir.is_dir():
                continue
            width_str, height_str = size.split("x")
            width, height = int(width_str), int(height_str)
            size_aspect = self._aspect_ratio_from_size(width, height)

            for path in sorted(template_dir.glob("*.html")):
                if path.name == "default.html":
                    continue
                content = path.read_text(encoding="utf-8")
                stem = path.stem
                template_type = self._template_type(stem)
                media_width, media_height = parse_media_size(content)
                if template_type == "video":
                    self._video_frames[stem] = parse_video_frame(content, canvas_size=(width, height))
                template_name = TEMPLATE_NAMES_ZH.get(stem, stem.replace("_", " ").title())
                item = {
                    "id": stem,
                    "name": template_name,
                    "version": "2" if template_type == "video" else "1",
                    "width": width,
                    "height": height,
                    "aspect_ratio": size_aspect,
                    "media_width": media_width,
                    "media_height": media_height,
                    "template_type": template_type,
                    "html_path": f"{size}/{path.name}",
                    "preview_path": self._find_preview(stem, size),
                    "parameter_schema": parse_parameters(content),
                    "default_params": {
                        parameter["name"]: parameter["default"]
                        for parameter in parse_parameters(content)
                    },
                    "supported_content_modes": self._supported_modes(template_type),
                }
                items[item["id"]] = item

        self._cache = items

        active_items = list(items.values())
        if aspect_ratio:
            active_items = [item for item in active_items if item.get("aspect_ratio") == aspect_ratio]
        if content_mode:
            active_items = [
                item for item in active_items
                if content_mode in item.get("supported_content_modes", [])
            ]
        return active_items

    def get_default_for_aspect(
        self, aspect_ratio: str, content_mode: str | None = None
    ) -> str:
        capability = get_content_mode_capability(content_mode)
        if capability and capability.media_kind == "video":
            if aspect_ratio == "16:9":
                return "video_wide_full"
            if aspect_ratio == "1:1":
                return "video_square_full"
            return "video_full_overlay"

        if aspect_ratio == "16:9":
            return "image_wide_minimal"
        if aspect_ratio == "1:1":
            return "image_square_matted"
        return "image_gallery_matted"

    def get(
        self,
        template_id: str | None,
        aspect_ratio: str | None = None,
        content_mode: str | None = None,
    ) -> dict[str, Any] | None:
        if not template_id:
            template_id = self.get_default_for_aspect(aspect_ratio or "9:16", content_mode)
        if self._cache is None:
            self.scan()
        if self._cache and template_id in self._cache:
            return self._cache[template_id]
        return None

    def resolve_path(self, template_id: str | None) -> Path:
        item = self.get(template_id)
        if not item:
            raise FileNotFoundError(f"Template not found: {template_id}")
        return self.root / item["html_path"]

    def get_media_size(
        self,
        template_id: str | None,
        fallback: tuple[int, int] = _DEFAULT_MEDIA_SIZE,
    ) -> tuple[int, int]:
        item = self.get(template_id)
        if not item:
            return fallback
        return int(item.get("media_width") or fallback[0]), int(
            item.get("media_height") or fallback[1]
        )

    def get_media_aspect_ratio(self, template_id: str | None, fallback: str = "9:16") -> str:
        item = self.get(template_id)
        if not item:
            return fallback
        width = int(item.get("media_width") or 0)
        height = int(item.get("media_height") or 0)
        if width <= 0 or height <= 0:
            return fallback
        if width == height:
            return "1:1"
        return "16:9" if width > height else "9:16"

    def get_video_frame(
        self,
        template_id: str | None,
        fallback: tuple[int, int, int, int] = (0, 0, 1080, 1920),
    ) -> tuple[int, int, int, int]:
        """Return the canvas slot used to compose a dynamic video source."""
        item = self.get(template_id)
        if not item:
            return fallback
        tid = item["id"]
        if tid in self._video_frames:
            return self._video_frames[tid]
        return (0, 0, int(item.get("width") or fallback[2]), int(item.get("height") or fallback[3]))

    def invalidate(self) -> None:
        self._cache = None
        self._video_frames = {}


template_catalog = TemplateCatalog()
