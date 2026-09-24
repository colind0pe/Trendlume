from unittest.mock import AsyncMock

import pytest

from src.providers.publishing.douyin import (
    _fill_and_verify_douyin_caption,
    _verify_douyin_caption_after_blur,
)


class CaptionEditor:
    def __init__(self, readings):
        self.readings = iter(readings)
        self.last_text = ""
        self.fill = AsyncMock()

    async def inner_text(self):
        self.last_text = next(self.readings, self.last_text)
        return self.last_text


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    monkeypatch.setattr("src.providers.publishing.douyin.asyncio.sleep", AsyncMock())


@pytest.mark.asyncio
async def test_caption_waits_for_editor_to_settle_without_refilling():
    caption = "说明文案\n#历史 #文化"
    editor = CaptionEditor(["说明文案", caption, "说明文案", caption, caption])
    await _fill_and_verify_douyin_caption(editor, caption)
    editor.fill.assert_awaited_once_with(caption)
    assert list(editor.readings) == []


@pytest.mark.asyncio
async def test_caption_accepts_layout_whitespace_and_retains_emoji():
    caption = "家庭👨\u200d👩\u200d👧\n#生活 #文化"
    editor = CaptionEditor(["\ufeff家庭👨\u200d👩\u200d👧\r\n\n#生活\u00a0#文化\u200b\n"])
    await _fill_and_verify_douyin_caption(editor, caption)
    editor.fill.assert_awaited_once_with(caption)


@pytest.mark.asyncio
async def test_caption_rejects_match_that_is_not_retained():
    caption = "说明文案\n#历史"
    editor = CaptionEditor([caption, "说明文案"])
    with pytest.raises(ValueError, match="editor text mismatch"):
        await _fill_and_verify_douyin_caption(editor, caption)


@pytest.mark.asyncio
async def test_caption_repairs_one_leading_topic_asterisk_after_blur():
    caption = "说明文案\n#宋朝 #熟水"

    class RewritingEditor:
        def __init__(self):
            self.fill_values = []
            self.readings = iter(["说明文案\n*#宋朝 #熟水"])
            self.last_text = ""

        async def press(self, key):
            return None

        async def fill(self, value):
            self.fill_values.append(value)
            self.last_text = caption
            self.readings = iter([caption])

        async def inner_text(self):
            self.last_text = next(self.readings, self.last_text)
            return self.last_text

    class BlurPage:
        async def evaluate(self, script):
            return None

    editor = RewritingEditor()
    await _verify_douyin_caption_after_blur(
        BlurPage(),
        editor,
        caption,
        phase="before publish",
        repair_leading_topic_asterisk=True,
    )
    assert editor.fill_values == [caption]
