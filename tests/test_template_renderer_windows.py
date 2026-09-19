import asyncio
import sys

import pytest

from src.services.template_renderer import TemplateRenderer

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows SelectorEventLoop compatibility is only relevant on Windows",
)


def test_template_renderer_reuses_browser_on_selector_loop(tmp_path):
    loop = asyncio.SelectorEventLoop()
    asyncio.set_event_loop(loop)
    worker_thread = None
    try:
        loop.run_until_complete(TemplateRenderer.close())
        availability = loop.run_until_complete(
            asyncio.gather(
                TemplateRenderer.check_available(),
                TemplateRenderer.check_available(),
            )
        )
        assert availability == [True, True]

        worker_thread = TemplateRenderer._worker._thread
        worker_loop = TemplateRenderer._worker._loop
        worker_browser = TemplateRenderer._worker_browser
        assert worker_thread is not None and worker_thread.is_alive()
        assert worker_loop is not None
        assert worker_browser is not None
        assert "Proactor" in type(worker_loop).__name__

        first, second = loop.run_until_complete(
            asyncio.gather(
                TemplateRenderer.render("image_gallery_matted", output_path=tmp_path / "first.png"),
                TemplateRenderer.render("image_gallery_matted", output_path=tmp_path / "second.png"),
            )
        )

        assert first.exists() and first.stat().st_size > 0
        assert second.exists() and second.stat().st_size > 0
        assert TemplateRenderer._worker._thread is worker_thread
        assert TemplateRenderer._worker._loop is worker_loop
        assert TemplateRenderer._worker_browser is worker_browser
    finally:
        loop.run_until_complete(TemplateRenderer.close())
        if worker_thread is not None:
            assert not worker_thread.is_alive()
        loop.close()
        asyncio.set_event_loop(None)
