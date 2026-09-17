import pytest

from src.core.exceptions import ProviderException
from src.providers.image.reference_frame import (
    _build_filter_graph,
    normalize_reference_frame_options,
    reference_frame_signature,
)


def test_reference_frame_normalizes_fixed_canvas_and_face_anchor():
    options = normalize_reference_frame_options(
        {
            "enabled": True,
            "width": 720,
            "height": 1280,
            "face_alignment": {
                "enabled": True,
                "face_box": {"x": 0.4, "y": 0.08, "width": 0.2, "height": 0.12},
            },
        },
        default_width=1080,
        default_height=1920,
    )

    assert options["width"] == 720
    assert options["height"] == 1280
    assert options["face_alignment"]["source_box"]["width"] == pytest.approx(0.2)
    assert "scale=" in _build_filter_graph(1000, 1600, options)
    assert "crop=720:1280" in _build_filter_graph(1000, 1600, options)
    assert reference_frame_signature(options) == reference_frame_signature(dict(options))


def test_reference_frame_requires_face_box_when_alignment_is_enabled():
    with pytest.raises(ProviderException, match="source_box"):
        normalize_reference_frame_options(
            {
                "enabled": True,
                "face_alignment": {"enabled": True},
            },
            default_width=720,
            default_height=1280,
        )
