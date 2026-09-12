from typing import Literal

ImageStylePreset = Literal[
    "stick_figure",
    "minimalist_line_art",
    "chinese_ink",
    "cinematic_real",
    "animation",
]

DEFAULT_IMAGE_STYLE_PRESET = "cinematic_real"

IMAGE_STYLE_PRESETS: dict[str, dict[str, str]] = {
    "stick_figure": {
        "name": "简约火柴人",
        "description": "极简黑色墨线火柴人插画，纯白干净背景，手绘线稿质感，主体轮廓清晰，画面只保留 1–3 个彼此分明的焦点元素，主体完整入镜，留出均衡负空间，避免杂乱细节",
    },
    "minimalist_line_art": {
        "name": "简笔画插画",
        "description": "通用极简线稿插画，流畅清晰的手绘轮廓，少量平涂色彩点缀，突出 1–3 个焦点元素，边缘留足安全空间，构图简洁，背景不喧宾夺主",
    },
    "chinese_ink": {
        "name": "中国水墨画",
        "description": "传统中国水墨画与国风美学，疏朗有力的笔触，主体布局含蓄雅致，讲究留白，远近层次融入淡墨烟雾，色彩克制，避免视觉堆砌",
    },
    "cinematic_real": {
        "name": "电影写实摄影",
        "description": "电影感写实摄影，高分辨率质感与真实材质；如有人物则保持自然人体结构；浅景深突出完整主体，背景柔和简洁，采用明确的镜头构图与机位，戏剧性明暗光影，呈现丰富但可信的细节",
    },
    "animation": {
        "name": "炫彩动画",
        "description": "清爽明快的动画美术风格，主体轮廓完整清晰；如有人物则保证姿态和面部情绪易读；突出 1–3 个焦点元素，光照柔和，配色协调，背景层次有序",
    },
}


def apply_image_style_preset(prompt: str, style_preset: str | None) -> str:
    """Add a known visual style to a direct image-generation prompt once."""
    clean_prompt = str(prompt or "").strip()
    style_description = IMAGE_STYLE_PRESETS.get(str(style_preset or "").strip(), {}).get("description")
    if not style_description or not clean_prompt or style_description in clean_prompt:
        return clean_prompt
    return f"{style_description}，{clean_prompt}"
