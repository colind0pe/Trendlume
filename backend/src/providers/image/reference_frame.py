"""Dependency-light reference-image framing for ComfyUI img2img."""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.exceptions import ProviderException


@dataclass
class PreparedReferenceImage:
    """A reference path plus the temporary directory that owns it, if any."""

    path: Path
    temporary_directory: tempfile.TemporaryDirectory[str] | None = None

    def cleanup(self) -> None:
        if self.temporary_directory is not None:
            self.temporary_directory.cleanup()


def normalize_reference_frame_options(
    options: dict[str, Any] | None,
    *,
    default_width: int,
    default_height: int,
) -> dict[str, Any] | None:
    """Validate and canonicalize the public reference-frame options.

    The provider accepts a dict so old callers remain source-compatible. Scene
    API validation happens in ``SceneReferenceFrameSpec``; this second boundary
    keeps direct Provider calls safe as well.
    """

    if options is None:
        return None
    if not isinstance(options, dict):
        raise ProviderException("ComfyUI", "reference_image_options 必须是对象。")
    if not bool(options.get("enabled", False)):
        return None

    width = _bounded_int(options.get("width", default_width), "width", 256, 4096)
    height = _bounded_int(options.get("height", default_height), "height", 256, 4096)
    fit = str(options.get("fit", "contain")).strip().lower()
    if fit not in {"contain", "cover"}:
        raise ProviderException("ComfyUI", "reference_image_options.fit 只能是 contain 或 cover。")
    padding_color = str(options.get("padding_color", "black")).strip().lower()
    if padding_color not in {"black", "white"}:
        raise ProviderException(
            "ComfyUI", "reference_image_options.padding_color 只能是 black 或 white。"
        )

    raw_face = options.get("face_alignment")
    if raw_face is None:
        raw_face = {}
    if not isinstance(raw_face, dict):
        raise ProviderException("ComfyUI", "reference_image_options.face_alignment 必须是对象。")

    face_enabled = bool(raw_face.get("enabled", False))
    face: dict[str, Any] = {"enabled": face_enabled}
    if face_enabled:
        source_box = raw_face.get("source_box")
        if source_box is None:
            source_box = raw_face.get("face_box") or raw_face.get("bbox")
        face["source_box"] = _normalize_rect(source_box)
        face["target_center_x"] = _bounded_float(
            raw_face.get("target_center_x", 0.5), "target_center_x", 0.0, 1.0
        )
        face["target_center_y"] = _bounded_float(
            raw_face.get("target_center_y", 0.18), "target_center_y", 0.0, 1.0
        )
        face["target_width"] = _bounded_float(
            raw_face.get("target_width", 0.12), "target_width", 0.01, 1.0
        )

    return {
        "enabled": True,
        "width": width,
        "height": height,
        "fit": fit,
        "padding_color": padding_color,
        "face_alignment": face,
    }


def reference_frame_signature(options: dict[str, Any] | None) -> str:
    """Return a stable cache suffix for a normalized transform."""

    return json.dumps(options or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


async def prepare_reference_image(
    image_path: Path,
    options: dict[str, Any] | None,
) -> PreparedReferenceImage:
    """Create a fixed-canvas PNG when framing is enabled."""

    if options is None:
        return PreparedReferenceImage(path=image_path)
    return await asyncio.to_thread(_prepare_reference_image, image_path, options)


def _prepare_reference_image(image_path: Path, options: dict[str, Any]) -> PreparedReferenceImage:
    temporary_directory = tempfile.TemporaryDirectory(prefix="trendlume-reference-")
    output_path = Path(temporary_directory.name) / "framed_reference.png"
    try:
        source_width, source_height = _probe_image_size(image_path)
        filter_graph = _build_filter_graph(
            source_width,
            source_height,
            options,
        )
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(image_path),
            "-vf",
            filter_graph,
            "-frames:v",
            "1",
            "-c:v",
            "png",
            str(output_path),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=60,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProviderException("ComfyUI", "固定构图需要服务器安装 FFmpeg。") from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderException("ComfyUI", "参考图固定构图处理超时。") from exc

        if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
            detail = result.stderr.decode("utf-8", errors="ignore").strip()
            raise ProviderException(
                "ComfyUI",
                f"参考图固定构图处理失败{f': {detail[:300]}' if detail else ''}。",
            )
        logger.info(
            "Prepared ComfyUI reference image: source={}x{}, target={}x{}",
            source_width,
            source_height,
            options["width"],
            options["height"],
        )
        return PreparedReferenceImage(
            path=output_path,
            temporary_directory=temporary_directory,
        )
    except Exception:
        temporary_directory.cleanup()
        raise


def _probe_image_size(image_path: Path) -> tuple[int, int]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0:s=x",
                str(image_path),
            ],
            capture_output=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ProviderException("ComfyUI", "固定构图需要服务器安装 ffprobe。") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProviderException("ComfyUI", "参考图尺寸探测超时。") from exc

    raw_size = result.stdout.decode("utf-8", errors="ignore").strip()
    try:
        width_text, height_text = raw_size.split("x", 1)
        width, height = int(width_text), int(height_text)
    except (ValueError, AttributeError) as exc:
        detail = result.stderr.decode("utf-8", errors="ignore").strip()
        raise ProviderException(
            "ComfyUI",
            f"无法读取参考图尺寸{f': {detail[:200]}' if detail else ''}。",
        ) from exc
    if width <= 0 or height <= 0:
        raise ProviderException("ComfyUI", "参考图尺寸无效。")
    return width, height


def _build_filter_graph(
    source_width: int,
    source_height: int,
    options: dict[str, Any],
) -> str:
    target_width = int(options["width"])
    target_height = int(options["height"])
    padding_color = str(options["padding_color"])
    face = options.get("face_alignment") or {}
    if not face.get("enabled"):
        if options["fit"] == "cover":
            return (
                f"scale={target_width}:{target_height}:"
                "force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={target_width}:{target_height}:(iw-ow)/2:(ih-oh)/2"
            )
        return (
            f"scale={target_width}:{target_height}:"
            "force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color={padding_color}"
        )

    source_box = face["source_box"]
    source_face_center_x = (source_box["x"] + source_box["width"] / 2.0) * source_width
    source_face_center_y = (source_box["y"] + source_box["height"] / 2.0) * source_height
    target_face_width = float(face["target_width"]) * target_width
    scale = target_face_width / (float(source_box["width"]) * source_width)
    if options["fit"] == "cover":
        scale = max(scale, target_width / source_width, target_height / source_height)
    scaled_width = max(2, round(source_width * scale))
    scaled_height = max(2, round(source_height * scale))

    target_face_center_x = float(face["target_center_x"]) * target_width
    target_face_center_y = float(face["target_center_y"]) * target_height
    left = round(target_face_center_x - source_face_center_x * scale)
    top = round(target_face_center_y - source_face_center_y * scale)
    pad_left = max(0, left)
    pad_top = max(0, top)
    crop_x = max(0, -left)
    crop_y = max(0, -top)
    canvas_width = max(target_width, crop_x + target_width, pad_left + scaled_width)
    canvas_height = max(target_height, crop_y + target_height, pad_top + scaled_height)
    return (
        f"scale={scaled_width}:{scaled_height}:flags=lanczos,"
        f"pad={canvas_width}:{canvas_height}:{pad_left}:{pad_top}:color={padding_color},"
        f"crop={target_width}:{target_height}:{crop_x}:{crop_y}"
    )


def _normalize_rect(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ProviderException("ComfyUI", "face_alignment.source_box 必须是对象。")
    rect = {
        key: _bounded_float(value.get(key), f"source_box.{key}", 0.0, 1.0)
        for key in ("x", "y", "width", "height")
    }
    if rect["width"] <= 0 or rect["height"] <= 0:
        raise ProviderException("ComfyUI", "face_alignment.source_box 的宽高必须大于 0。")
    if rect["x"] + rect["width"] > 1.0 or rect["y"] + rect["height"] > 1.0:
        raise ProviderException("ComfyUI", "face_alignment.source_box 必须位于参考图范围内。")
    return rect


def _bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ProviderException("ComfyUI", f"reference_image_options.{name} 无效。")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ProviderException("ComfyUI", f"reference_image_options.{name} 无效。") from exc
    if parsed < minimum or parsed > maximum:
        raise ProviderException(
            "ComfyUI", f"reference_image_options.{name} 必须在 {minimum} 到 {maximum} 之间。"
        )
    return parsed


def _bounded_float(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ProviderException("ComfyUI", f"reference_image_options.{name} 无效。")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ProviderException("ComfyUI", f"reference_image_options.{name} 无效。") from exc
    if parsed < minimum or parsed > maximum:
        raise ProviderException(
            "ComfyUI", f"reference_image_options.{name} 必须在 {minimum} 到 {maximum} 之间。"
        )
    return parsed
