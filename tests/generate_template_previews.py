"""Generate brand-derived test media and previews for every active template.

This intentionally scans only the three active template size directories.

Run from the repository root with:

    .\\backend\\.venv\\Scripts\\python.exe tests\\generate_template_previews.py
"""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

from playwright.async_api import async_playwright

REPO_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_DIR / "backend"
TEMPLATES_DIR = BACKEND_DIR / "templates"
ASSETS_DIR = TEMPLATES_DIR / "assets"
PREVIEWS_DIR = TEMPLATES_DIR / "previews"

sys.path.insert(0, str(BACKEND_DIR))

from src.services.template_catalog import template_catalog  # noqa: E402
from src.services.template_renderer import TemplateRenderer  # noqa: E402


def _svg_data_uri(svg_text: str) -> str:
    encoded = base64.b64encode(svg_text.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _brand_asset_html(width: int, height: int, logo_uri: str, icon_uri: str) -> str:
    orientation = "portrait" if height > width else "landscape" if width > height else "square"
    logo_width = {"portrait": 420, "landscape": 480, "square": 400}[orientation]
    logo_top = {"portrait": 760, "landscape": 390, "square": 350}[orientation]
    label = {"portrait": "9:16 竖屏测试帧", "landscape": "16:9 横屏测试帧", "square": "1:1 方形测试帧"}[orientation]
    corner_markup = "" if orientation == "landscape" else f'<div class="corner">{label}</div>'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; width: {width}px; height: {height}px; overflow: hidden; }}
    body {{ background: #090a0f; font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif; }}
    .canvas {{ position: relative; width: 100%; height: 100%; overflow: hidden; background:
      radial-gradient(ellipse at 50% 45%, rgba(99,102,241,.30), transparent 42%),
      radial-gradient(ellipse at 16% 74%, rgba(34,211,238,.17), transparent 34%),
      linear-gradient(145deg, #090a0f 0%, #11152a 54%, #090a0f 100%); }}
    .grid {{ position: absolute; inset: 0; opacity: .16; background-image:
      linear-gradient(rgba(255,255,255,.12) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.12) 1px, transparent 1px); background-size: 48px 48px;
      mask-image: linear-gradient(to bottom, transparent, black 18%, black 82%, transparent); }}
    .beam {{ position: absolute; width: 150%; height: 22%; left: -24%; top: 37%; transform: rotate(-18deg);
      background: linear-gradient(90deg, transparent, rgba(129,140,248,.20), rgba(34,211,238,.18), transparent);
      filter: blur(12px); }}
    .orb {{ position: absolute; width: 42%; aspect-ratio: 1; left: 29%; top: 31%; border-radius: 50%;
      border: 1px solid rgba(255,255,255,.20); box-shadow: 0 0 90px rgba(99,102,241,.28), inset 0 0 70px rgba(34,211,238,.12);
      transform: rotate(18deg) scaleY(.56); }}
    .orb::after {{ content: ""; position: absolute; inset: 13%; border: 1px solid rgba(255,255,255,.12); border-radius: 50%; }}
    .watermark {{ position: absolute; width: 28%; left: 36%; top: 38%; opacity: .10; filter: saturate(1.2) blur(.2px); }}
    .watermark img {{ display: block; width: 100%; }}
    .logo-lockup {{ position: absolute; left: 50%; top: {logo_top}px; width: {logo_width}px; transform: translateX(-50%);
      filter: drop-shadow(0 18px 42px rgba(0,0,0,.48)); }}
    .logo-lockup img {{ display: block; width: 100%; height: auto; }}
    .caption {{ position: absolute; left: 50%; bottom: 72px; transform: translateX(-50%); color: rgba(255,255,255,.72);
      font-size: 18px; letter-spacing: .16em; white-space: nowrap; }}
    .rule {{ position: absolute; left: 50%; bottom: 124px; width: 120px; height: 2px; transform: translateX(-50%);
      background: linear-gradient(90deg, transparent, #818cf8, transparent); }}
    .corner {{ position: absolute; right: 58px; top: 58px; color: rgba(255,255,255,.42); font-size: 16px; letter-spacing: .12em; }}
    .corner::before {{ content: "TRND / "; color: #a5b4fc; }}
  </style>
</head>
<body>
  <main class="canvas">
    <div class="grid"></div>
    <div class="beam"></div>
    <div class="orb"></div>
    <div class="watermark"><img src="{icon_uri}" alt="Trendlume icon"></div>
    {corner_markup}
    <div class="logo-lockup"><img src="{logo_uri}" alt="Trendlume"></div>
    <div class="rule"></div>
    <div class="caption">AI SHORT VIDEO STUDIO</div>
  </main>
</body>
</html>"""


async def _generate_brand_assets() -> dict[str, Path]:
    frontend_public = BACKEND_DIR.parent / "frontend" / "public"
    logo_uri = _svg_data_uri((frontend_public / "logo.svg").read_text(encoding="utf-8"))
    icon_uri = _svg_data_uri((frontend_public / "icon.svg").read_text(encoding="utf-8"))
    sizes = (
        ("portrait", "sample_real_render_1080x1920.png", 1080, 1920),
        ("landscape", "sample_real_render_1920x1080.png", 1920, 1080),
        ("square", "sample_real_render_1080x1080.png", 1080, 1080),
    )
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            for key, filename, width, height in sizes:
                page = await browser.new_page(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                )
                await page.set_content(_brand_asset_html(width, height, logo_uri, icon_uri), wait_until="load")
                output = ASSETS_DIR / filename
                await page.screenshot(path=str(output), type="png")
                await page.close()
                result[key] = output.resolve()
                print(f"[OK] Generated brand asset {output.name} ({width}x{height})")
        finally:
            await browser.close()
    return result


def _preview_path(size: str, template_id: str) -> Path:
    return PREVIEWS_DIR / size / f"{template_id}.png"


async def main() -> None:
    assets = await _generate_brand_assets()
    for size in ("1080x1920", "1920x1080", "1080x1080"):
        (PREVIEWS_DIR / size).mkdir(parents=True, exist_ok=True)

    portrait = assets["portrait"]
    landscape = assets["landscape"]
    square = assets["square"]

    portrait_items = [
        ("video_full_overlay", "数字生活：重新理解注意力", "把信息留在需要的地方，把时间还给真正重要的事情。", portrait, {}),
        ("video_cinema_scope", "失落文明：时间留下的线索", "从残垣、器物与光影之间，读懂一段文明如何回应时间。", portrait, {}),
        ("image_gallery_matted", "空间诗学：留白如何组织生活", "留白不是空缺，而是让形式、功能与呼吸彼此成全。", portrait, {}),
        ("image_frosted_ambient", "微光视界：给日常留一点安静", "光线慢下来，视线才有机会看见生活里细小而真实的变化。", portrait, {}),
        ("image_editorial_warm", "纸墨温度：慢下来的日常", "在纸页与屏幕之间，重新找回阅读和观察的细腻质感。", portrait, {}),
        ("static_bulletin_flash", "趋势观察：内容产品的三个变化", "从即时消费到长期留存，内容正在回到清晰、可靠和有用。", None, {}),
        ("static_editorial_quote", "向内探索：时间如何改变我们", "真正持久的答案，通常来自一次安静而具体的回望。", None, {}),
    ]
    landscape_items = [
        ("video_wide_full", "深空探索：寻找宇宙的回声", "穿过亿万光年的尘埃，人类仍在用好奇心确认自己的位置。", landscape, {}),
        ("video_wide_cinema_scope", "设计解剖：结构如何产生秩序", "每一处留白、比例与光线，都在服务于清晰而克制的叙事；镜头因此保留了完整的呼吸空间，让观看者在进入故事之前先获得一瞬安静。", landscape, {}),
        ("image_wide_minimal", "极简主义：让秩序清晰可见", "在宽阔画幅里减少干扰，让结构与解说形成稳定的阅读节奏。", landscape, {}),
        ("image_wide_cinema", "城市漫游：胶片里的光", "一束光、一段街角和一次回头，组成城市记忆的细小切片。", landscape, {}),
        ("image_wide_editorial", "深度专栏：时代里的个体思考", "把快速变化放回个人经验里，思考我们如何选择、行动与生活。", landscape, {}),
        (
            "static_wide_bulletin",
            "前沿观察：数字化转型的现场",
            "技术进入日常之后，真正重要的是组织、协作与人的体验。",
            None,
            {
                "point_1": "核心变化：横画幅带来更长的阅读路径",
                "point_2": "结构提炼：让重要信息先被看见",
                "point_3": "持续沉淀：把一次观看变成可复用的知识",
            },
        ),
    ]
    square_items = [
        ("video_square_full", "专注生产力：少一点，做得更好", "在方寸画幅里保留一件重要的事，让注意力回到当下。", square, {}),
        ("video_square_card", "认知觉醒：跳出信息茧房", "当信息不再只是迎合偏见，我们才有机会重新理解世界。", square, {}),
        ("image_square_matted", "雅致生活：日常也值得被认真对待", "给普通时刻留出仪式感，生活就会显出自己的纹理。", square, {}),
        ("image_square_frosted", "未来触感：人与设备的新关系", "更自然的交互，不是增加功能，而是减少人与工具之间的距离。", square, {}),
        ("image_square_editorial", "生活随笔：记录微小的确幸", "那些不喧哗的片刻，常常比宏大的计划更接近真实生活。", square, {}),
        ("static_square_quote", "向光而行：把今天过具体", "每个日子都值得被看见；从一件小事开始，方向就会变得清楚。", None, {}),
    ]

    renders = [
        ("1080x1920", item) for item in portrait_items
    ] + [
        ("1920x1080", item) for item in landscape_items
    ] + [
        ("1080x1080", item) for item in square_items
    ]
    assert len(renders) == 19

    template_catalog.invalidate()
    print(f"Rendering all {len(renders)} active templates...")
    for size, (template_id, title, text, image_path, params) in renders:
        custom_params = {
            "author": "@Trendlume",
            "describe": "AI 短视频创作与发布工作台",
            "brand": "Trendlume",
        }
        custom_params.update(params)
        output = _preview_path(size, template_id)
        await TemplateRenderer.render(
            template_id,
            title=title,
            text=text,
            image_path=str(image_path) if image_path else None,
            custom_params=custom_params,
            output_path=output,
        )
        print(f"[OK] Rendered {size}/{output.name}")

    print("All 19 active template previews rendered successfully.")


if __name__ == "__main__":
    asyncio.run(main())
