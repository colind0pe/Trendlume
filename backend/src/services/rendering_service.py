import asyncio
import subprocess
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, ValidationException
from src.domain.content_modes import is_content_mode_supported, resolve_content_mode
from src.domain.enums import AssetType
from src.models.asset import AssetModel
from src.models.project import ProjectAssetBindingModel
from src.repositories.asset_repository import AssetRepository
from src.repositories.project_repository import ProjectRepository
from src.repositories.scene_repository import SceneRepository
from src.repositories.task_repository import TaskRepository
from src.services.asset_service import AssetService
from src.services.media_probe import MediaProbeResult, media_probe_service
from src.services.system_asset_service import is_bgm_asset, is_system_asset
from src.services.template_catalog import template_catalog
from src.services.template_renderer import TemplateRenderer
from src.storage.local_storage import LocalStorageService, local_storage


class RenderingService:
    """Independent service for real FFmpeg-based video clip rendering, audio-video merging, and full video composition"""

    DURATION_TOLERANCE_SECONDS = 0.25
    COMPOSITION_FORMAT_VERSION = "4"
    ONLINE_SCENE_RENDER_FORMAT_VERSION = "online-layout-v1"

    def __init__(
        self,
        session: AsyncSession,
        storage: LocalStorageService = local_storage,
        ffmpeg_runner: Callable[[list[str], Path], Coroutine[Any, Any, bool]] | None = None,
        execution_context=None,
        durable: bool = False,
        production_settings: dict[str, Any] | None = None,
    ):
        self.session = session
        self.execution_context = execution_context
        self.durable = durable
        self.production_settings = production_settings
        self.commands: list[list[str]] = []
        self.storage = storage
        self.ffmpeg_runner = ffmpeg_runner
        self.task_repo = TaskRepository(session)
        self.scene_repo = SceneRepository(session)
        self.project_repo = ProjectRepository(session)
        self.asset_repo = AssetRepository(session)
        self.asset_service = AssetService(session, storage=storage, execution_context=execution_context)

    async def _run_ffmpeg_command(self, cmd: list[str], output_path: Path, timeout: float = 60.0) -> bool:
        """Run FFmpeg subprocess in a thread with timeout and verify valid output production"""
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.session.commit()
        self.commands.append(list(cmd))
        if self.ffmpeg_runner:
            return await self.ffmpeg_runner(cmd, output_path)

        def _exec():
            return subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                check=False,
            )

        try:
            res = await asyncio.to_thread(_exec)
            if res.returncode != 0:
                err_text = res.stderr.decode("utf-8", errors="ignore")
                logger.error(f"FFmpeg command failed (code {res.returncode}): {err_text[:300]}")
                raise ValidationException(f"FFmpeg 渲染执行失败 (code {res.returncode}): {err_text[:200]}")

            if not output_path.exists() or output_path.stat().st_size == 0:
                raise ValidationException(f"FFmpeg 执行完成但未生成有效媒体文件: {output_path.name}")

            return True
        except FileNotFoundError as e:
            logger.error("FFmpeg 未在系统中安装或未配置在 PATH 环境变量中")
            raise ValidationException("服务器未检测到 FFmpeg 命令行工具，请先在宿主机安装 FFmpeg。") from e
        except subprocess.TimeoutExpired as e:
            logger.error(f"FFmpeg 执行超时 ({timeout}s)")
            raise ValidationException(f"FFmpeg 渲染执行超时 ({timeout}s)，请检查输入素材分辨率与时长。") from e

    async def render_scene_clip(self, scene_id: str) -> str:
        """Render a single scene into a real MP4 clip with its HTML template overlay."""
        scene = await self.scene_repo.get_by_id(scene_id)
        if not scene:
            raise NotFoundException("Scene", scene_id)
        task = await self.task_repo.get_by_id(scene.task_id)

        # TTS providers persist their measured duration on the scene.  Preserve
        # that value for A/V sync (only guard against an invalid zero/negative
        # duration when a hand-authored scene has not been synthesized yet).
        duration = max(0.1, float(scene.duration_seconds or 4.0))
        output_rel_path = f"cache/scene_{scene.id}_{uuid.uuid4().hex[:6]}.mp4"
        output_abs_path = self.storage.get_path(output_rel_path)
        output_abs_path.parent.mkdir(parents=True, exist_ok=True)

        # Get visual asset and audio asset
        media_asset = (
            await self.asset_repo.get_by_id(scene.media_asset_id) if scene.media_asset_id else None
        )
        audio_asset = (
            await self.asset_repo.get_by_id(scene.audio_asset_id) if scene.audio_asset_id else None
        )

        generation_settings = self.production_settings or (task.generation_settings if task else {}) or {}
        template_id = generation_settings.get("template_id", "image_gallery_matted")
        template_item = template_catalog.get(template_id)
        if not template_item:
            raise ValidationException(f"模板不存在: {template_id}")
        content_mode = resolve_content_mode(
            generation_settings.get("content_mode"),
            template_type=template_item["template_type"],
        )
        if not is_content_mode_supported(content_mode, template_item["template_type"]):
            raise ValidationException(f"模板 {template_id} 不支持内容模式 {content_mode}")
        external_material_mode = content_mode == "online_asset"

        canvas_width = int(template_item.get("width") or 1080)
        canvas_height = int(template_item.get("height") or 1920)
        video_frame = template_catalog.get_video_frame(
            template_id,
            fallback=(0, 0, canvas_width, canvas_height),
        )
        frame_x, frame_y, frame_width, frame_height = video_frame

        media_path = self.storage.get_path(media_asset.file_path) if media_asset else None
        audio_path = self.storage.get_path(audio_asset.file_path) if audio_asset else None

        if media_path and (not media_path.exists() or media_path.stat().st_size == 0):
            raise ValidationException(f"分镜画面文件不存在: {media_asset.file_path}")

        template_params = dict(generation_settings.get("template_params") or {})
        template_params.update((scene.layout_params or {}).get("template_params") or {})
        template_params.setdefault("index", int(scene.sequence_index or 0) + 1)
        rendered_frame = self.storage.get_path(
            f"cache/template_scene_{scene.id}_{uuid.uuid4().hex[:6]}.png"
        )
        subtitle_file: Path | None = None
        subtitle_line_count = 0
        subtitle_timeline = (scene.layout_params or {}).get("dialogue_timeline") or []
        subtitle_items: list[dict[str, Any]] = []
        for item in subtitle_timeline:
            try:
                text = str(item.get("text") or "").strip()
                start = max(0.0, min(duration, float(item.get("start", 0.0))))
                end = max(start, min(duration, float(item.get("end", duration))))
            except (AttributeError, TypeError, ValueError):
                continue
            if text and end > start:
                subtitle_items.append({"text": text, "start": start, "end": end})
        if subtitle_items:
            subtitle_line_count = len(subtitle_items)
            subtitle_file = self.storage.get_path(
                f"cache/scene_subtitles_{scene.id}_{uuid.uuid4().hex[:6]}.ass"
            )
            subtitle_file.parent.mkdir(parents=True, exist_ok=True)
            subtitle_file.write_text(
                self._ass_subtitles(subtitle_items, duration), encoding="utf-8"
            )
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.session.commit()
        try:
            # Dispatch by the actual bound asset type.  A scene created in
            # online_asset mode may be explicitly rebound to a local image,
            # and that image must take the frame path instead of the video
            # overlay path.
            media_is_image = bool(media_asset and media_asset.asset_type == AssetType.IMAGE)
            media_is_video = bool(media_asset and media_asset.asset_type == AssetType.VIDEO)
            if media_asset and not (media_is_image or media_is_video):
                raise ValidationException("分镜画面素材必须是图片或视频。")
            if not media_asset and content_mode not in {"static", "generated_image"}:
                raise ValidationException("视频内容模式缺少视频素材。")
            frame_media = media_path if media_is_image else None
            resolved_title = str(template_params.get("title") or "").strip()
            if not resolved_title and task and task.title:
                candidate = str(task.title).strip()
                if candidate and candidate not in {"Trendlume", "未命名任务", "未命名短视频任务"}:
                    resolved_title = candidate

            await TemplateRenderer.render(
                template_id,
                title=resolved_title,
                text=scene.narration_text,
                image_path=frame_media,
                custom_params=template_params,
                custom_css=(generation_settings.get("custom_css") if task else None),
                transparent=media_is_video,
                output_path=rendered_frame,
            )

            if not media_is_video:
                if not rendered_frame.exists():
                    raise ValidationException("模板未生成有效画面帧。")
                cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(rendered_frame)]
                video_map = "0:v:0"
                audio_input_index = 1
            else:
                if not media_path:
                    raise ValidationException("视频内容模式缺少视频素材。")
                cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(media_path), "-i", str(rendered_frame)]
                video_map = "[v]"
                audio_input_index = 2

            if audio_path and audio_path.exists() and audio_path.stat().st_size > 0:
                cmd += ["-i", str(audio_path)]
            else:
                cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

            if video_map == "[v]":
                is_full_canvas_frame = (
                    frame_x == 0
                    and frame_y == 0
                    and frame_width == canvas_width
                    and frame_height == canvas_height
                )
                if is_full_canvas_frame:
                    filter_graph = (
                        f"[0:v]scale={canvas_width}:{canvas_height}:force_original_aspect_ratio=increase,"
                        f"crop={canvas_width}:{canvas_height},setsar=1[media];"
                        "[media][1:v]overlay=0:0:format=auto:eof_action=repeat[v]"
                    )
                else:
                    filter_graph = (
                        "[0:v]split=2[ambient_src][main_src];"
                        f"[ambient_src]scale={canvas_width}:{canvas_height}:"
                        "force_original_aspect_ratio=increase,"
                        f"crop={canvas_width}:{canvas_height},"
                        "boxblur=luma_radius=18:luma_power=2:"
                        "chroma_radius=10:chroma_power=2,"
                        "eq=brightness=-0.18:saturation=0.82,setsar=1[ambient];"
                        f"[main_src]scale={frame_width}:{frame_height}:"
                        "force_original_aspect_ratio=increase,"
                        f"crop={frame_width}:{frame_height},setsar=1[main];"
                        f"[ambient][main]overlay={frame_x}:{frame_y}:format=auto:"
                        "eof_action=repeat[media];"
                        "[media][1:v]overlay=0:0:format=auto:eof_action=repeat[v]"
                    )
                if subtitle_file:
                    filter_graph += (
                        f";[v]ass=filename='{self._ffmpeg_filter_path(subtitle_file)}'[v_subtitled]"
                    )
                    video_map = "[v_subtitled]"
                cmd += ["-filter_complex", filter_graph, "-map", video_map]
            else:
                if subtitle_file:
                    cmd += [
                        "-filter_complex",
                        f"[0:v]ass=filename='{self._ffmpeg_filter_path(subtitle_file)}'[v_subtitled]",
                        "-map",
                        "[v_subtitled]",
                    ]
                else:
                    cmd += ["-map", video_map]
            cmd += [
                "-map", f"{audio_input_index}:a:0",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                # Keep the video at the scene duration even when the source
                # audio is shorter.  ``apad`` supplies silence and ``atrim``
                # gives both streams the same bounded duration.
                "-af", f"aresample=async=1:first_pts=0,apad,atrim=duration={duration:.3f}",
                "-t", f"{duration:.3f}", str(output_abs_path),
            ]
            await self._run_ffmpeg_command(cmd, output_abs_path, timeout=120.0)
            rendered_probe = await self._validate_media_file(
                output_abs_path,
                require_audio=True,
                expected_width=canvas_width,
                expected_height=canvas_height,
                expected_duration=duration,
            )
        finally:
            rendered_frame.unlink(missing_ok=True)
            if subtitle_file:
                subtitle_file.unlink(missing_ok=True)

        # Update scene rendered_segment_asset_id
        clip_asset = await self.asset_service.save_asset(
            content=output_abs_path.read_bytes(),
            file_name=f"scene_{scene.sequence_index}.mp4",
            mime_type="video/mp4",
            asset_type=AssetType.VIDEO,
            duration_seconds=(
                rendered_probe.duration_seconds
                if rendered_probe and rendered_probe.duration_seconds
                else duration
            ),
            project_id=task.project_id if task else None,
            metadata={
                "scene_id": scene.id,
                "type": "scene_clip",
                "ffmpeg_commands": list(self.commands),
                "template_id": template_id,
                "content_mode": content_mode,
                "layout_strategy": (
                    "online_cover_blurred_background"
                    if content_mode == "online_asset" and media_is_video
                    else "cover_blurred_background"
                    if media_is_video
                    else "online_template_image"
                    if content_mode == "online_asset"
                    else "template_full_canvas"
                ),
                "media_frame": {
                    "x": frame_x,
                    "y": frame_y,
                    "width": frame_width,
                    "height": frame_height,
                    "canvas_width": canvas_width,
                    "canvas_height": canvas_height,
                } if (external_material_mode or media_is_video) else None,
                "scene_render_format_version": (
                    self.ONLINE_SCENE_RENDER_FORMAT_VERSION
                    if external_material_mode
                    else None
                ),
                "actual_duration_seconds": (
                    rendered_probe.duration_seconds if rendered_probe else duration
                ),
                "duration_source": "ffprobe" if rendered_probe else "scene_duration",
                "subtitle_burned": subtitle_line_count > 0,
                "subtitle_line_count": subtitle_line_count,
            },
        )
        scene.rendered_segment_asset_id = clip_asset.id
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.scene_repo.update(scene)
        await self.session.commit()

        logger.info(f"Scene #{scene.sequence_index + 1} clip rendered successfully: {clip_asset.id}")
        return output_rel_path

    @staticmethod
    def _srt_timestamp(seconds: float) -> str:
        millis = int(round(max(0.0, seconds) * 1000))
        hours, remainder = divmod(millis, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, millis = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _ass_timestamp(seconds: float) -> str:
        centiseconds = int(round(max(0.0, seconds) * 100))
        hours, remainder = divmod(centiseconds, 360000)
        minutes, remainder = divmod(remainder, 6000)
        secs, centis = divmod(remainder, 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

    @classmethod
    def _ass_subtitle(cls, text: str, duration: float) -> str:
        # Escape ASS override-tag delimiters while retaining intentional line
        # breaks.  The text is already user-controlled and must never become
        # executable ASS markup.
        safe_text = (
            text.replace("\\", "\\\\")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\n", r"\N")
        )
        return (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1080\n"
            "PlayResY: 1920\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Noto Sans CJK SC,46,&H00FFFFFF,&H00FFFFFF,&H80000000,"
            "&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,60,60,160,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            f"Dialogue: 0,0:00:00.00,{cls._ass_timestamp(duration)},Default,,0,0,0,,{safe_text}\n"
        )

    @classmethod
    def _ass_subtitles(cls, timeline: list[dict[str, Any]], duration: float) -> str:
        """Build an ASS file for a scene's measured DialogueLine timeline."""

        header = cls._ass_subtitle("", 0).split("Dialogue:", 1)[0]
        events = []
        for item in timeline:
            text = str(item.get("text") or "")
            start = max(0.0, min(duration, float(item.get("start", 0.0))))
            end = max(start, min(duration, float(item.get("end", duration))))
            safe_text = (
                text.replace("\\", "\\\\")
                .replace("{", "\\{")
                .replace("}", "\\}")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
                .replace("\n", r"\N")
            )
            events.append(
                f"Dialogue: 0,{cls._ass_timestamp(start)},{cls._ass_timestamp(end)},"
                f"Default,,0,0,0,,{safe_text}"
            )
        return header + "\n".join(events) + "\n"

    @staticmethod
    def _ffmpeg_filter_path(path: Path) -> str:
        """Escape a local path for FFmpeg's filtergraph parser on Windows."""

        return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")

    async def _validate_media_file(
        self,
        path: Path,
        require_audio: bool = False,
        require_video: bool = True,
        expected_width: int | None = None,
        expected_height: int | None = None,
        expected_duration: float | None = None,
        expected_audio_duration: float | None = None,
    ) -> MediaProbeResult | None:
        if not path.exists() or path.stat().st_size == 0:
            raise ValidationException(f"媒体文件不存在或为空: {path.name}")
        if self.ffmpeg_runner:
            return
        probe = await media_probe_service.probe(path)
        if require_video and not probe.has_video:
            raise ValidationException(f"媒体文件缺少必要的视频流: {path.name}")
        if require_audio and not probe.has_audio:
            raise ValidationException(f"媒体文件缺少必要的音频流: {path.name}")
        duration = probe.duration_seconds or 0.0
        if (require_video or require_audio) and duration <= 0:
            raise ValidationException(f"媒体文件缺少有效时长: {path.name}")
        if expected_width and probe.width != expected_width:
            raise ValidationException(f"媒体文件宽度不符合要求: {path.name}")
        if expected_height and probe.height != expected_height:
            raise ValidationException(f"媒体文件高度不符合要求: {path.name}")
        if expected_duration is not None and abs(duration - expected_duration) > self.DURATION_TOLERANCE_SECONDS:
            raise ValidationException(
                f"媒体时长校验失败: path={path}, 实际={duration:.3f}s, 目标={expected_duration:.3f}s, "
                f"允许误差={self.DURATION_TOLERANCE_SECONDS:.2f}s"
            )
        if expected_audio_duration is not None:
            audio_duration = probe.audio_duration or 0.0
            if abs(audio_duration - expected_audio_duration) > self.DURATION_TOLERANCE_SECONDS:
                raise ValidationException(
                    f"媒体音频时长校验失败: path={path}, 实际={audio_duration:.3f}s, "
                    f"目标={expected_audio_duration:.3f}s, "
                    f"允许误差={self.DURATION_TOLERANCE_SECONDS:.2f}s"
                )
        return probe

    async def compose_task_video(
        self,
        task_id: str,
        bgm_asset_id: str | None = None,
    ) -> AssetModel:
        """Compose all scene clips of a task into the final complete MP4 video"""
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundException("Task", task_id)

        scenes = await self.scene_repo.list_by_task_id(task_id)
        if not scenes:
            raise ValidationException("该任务没有任何分镜片段，无法合成视频。")

        generation_settings = self.production_settings or task.generation_settings or {}
        explicit_bgm_override = bgm_asset_id is not None
        template_id = generation_settings.get("template_id", "image_gallery_matted")
        template_item = template_catalog.get(template_id)
        content_mode = resolve_content_mode(
            generation_settings.get("content_mode"),
            template_type=(template_item or {}).get("template_type"),
        )
        expected_scene_render_version = (
            self.ONLINE_SCENE_RENDER_FORMAT_VERSION
            if content_mode == "online_asset"
            else None
        )

        # 1. Ensure all scene segments are rendered
        clip_paths: list[Path] = []
        clip_durations: list[float] = []
        total_duration = 0.0
        subtitle_burned = False
        subtitle_line_count = 0

        for sc in scenes:
            existing_clip = (
                await self.asset_repo.get_by_id(sc.rendered_segment_asset_id)
                if sc.rendered_segment_asset_id
                else None
            )
            clip_valid = False
            existing_clip_metadata = (existing_clip.metadata_json or {}) if existing_clip else {}
            if (
                existing_clip
                and existing_clip_metadata.get("type") == "scene_clip"
                and (
                    expected_scene_render_version is None
                    or existing_clip_metadata.get("scene_render_format_version")
                    == expected_scene_render_version
                )
            ):
                clip_path = self.storage.get_path(existing_clip.file_path)
                try:
                    await self._validate_media_file(clip_path, require_audio=True)
                    clip_valid = True
                except Exception:
                    clip_valid = False
            if not clip_valid:
                if self.durable:
                    raise ValidationException("阶段校验后的片段不可用，请重试合成阶段。")
                await self.render_scene_clip(sc.id)
                await self.session.refresh(sc)

            clip_asset = await self.asset_repo.get_by_id(sc.rendered_segment_asset_id)  # type: ignore
            if clip_asset:
                clip_path = self.storage.get_path(clip_asset.file_path)
                if clip_path.exists():
                    clip_metadata = clip_asset.metadata_json or {}
                    subtitle_burned = subtitle_burned or bool(clip_metadata.get("subtitle_burned"))
                    subtitle_line_count += int(clip_metadata.get("subtitle_line_count") or 0)
                    clip_paths.append(clip_path)
                    clip_probe = await self._validate_media_file(
                        clip_path,
                        require_audio=True,
                        require_video=True,
                    )
                    actual_duration = (
                        clip_probe.duration_seconds
                        if clip_probe and clip_probe.duration_seconds
                        else float(sc.duration_seconds or clip_asset.duration_seconds or 4.0)
                    )
                    clip_durations.append(actual_duration)
                    total_duration += actual_duration

        if not clip_paths:
            raise ValidationException("未能找到任何有效的分镜视频片段，请先生成各分镜画面与配音素材。")

        # 2. Intermediate and final output paths
        suffix = uuid.uuid4().hex[:6]
        concat_rel_path = f"cache/concat_{task_id}_{suffix}.mp4"
        concat_abs_path = self.storage.get_path(concat_rel_path)
        final_rel_path = f"videos/final_{task_id}_{suffix}.mp4"
        final_abs_path = self.storage.get_path(final_rel_path)
        concat_abs_path.parent.mkdir(parents=True, exist_ok=True)
        final_abs_path.parent.mkdir(parents=True, exist_ok=True)

        # 3. Normalize every clip before concatenating.  The scene renderer can
        # preserve the source frame rate/time base, so stream-copy concat can
        # produce non-monotonic DTS or large video timestamp gaps when online
        # clips use different encodings.  Resetting PTS and making all inputs
        # share the same FPS/SAR gives the concat filter one continuous clock.
        filter_parts: list[str] = []
        concat_streams: list[str] = []
        ffmpeg_cmd = ["ffmpeg", "-y"]
        for index, clip_path in enumerate(clip_paths):
            ffmpeg_cmd.extend(["-i", str(clip_path)])
            filter_parts.append(
                f"[{index}:v:0]fps=30,format=yuv420p,setsar=1,setpts=PTS-STARTPTS[v{index}]"
            )
            filter_parts.append(
                f"[{index}:a:0]aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS[a{index}]"
            )
            concat_streams.extend([f"[v{index}]", f"[a{index}]"])

        filter_parts.append(
            "".join(concat_streams)
            + f"concat=n={len(clip_paths)}:v=1:a=1[video_concat][audio_concat]"
        )
        filter_parts.append(
            f"[audio_concat]aresample=async=1:first_pts=0,apad,"
            f"atrim=duration={total_duration:.3f}[audio]"
        )
        ffmpeg_cmd.extend(
            [
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                "[video_concat]",
                "-map",
                "[audio]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-t",
                f"{total_duration:.3f}",
                str(concat_abs_path),
            ]
        )
        await self._run_ffmpeg_command(ffmpeg_cmd, concat_abs_path, timeout=120.0)

        await self._validate_media_file(
            concat_abs_path,
            require_audio=True,
            expected_duration=total_duration,
            expected_audio_duration=total_duration,
        )

        # 4b. Optionally mix project/task BGM below the narration volume.
        # Missing BGM settings mean that this render has no task-level BGM.
        project = await self.project_repo.get_by_id(task.project_id)
        raw_bgm_enabled = generation_settings.get("bgm_enabled", False)
        if isinstance(raw_bgm_enabled, str):
            bgm_enabled = raw_bgm_enabled.strip().lower() in {"true", "1", "yes", "on"}
        else:
            bgm_enabled = bool(raw_bgm_enabled)
        selected_bgm_id = bgm_asset_id if explicit_bgm_override else generation_settings.get("bgm_asset_id")
        if explicit_bgm_override:
            bgm_enabled = bool(bgm_asset_id)
        elif bgm_enabled and not selected_bgm_id:
            selected_bgm_id = (
                (project.default_production_settings or {}).get("bgm_asset_id")
                if project
                else None
            )

        try:
            bgm_volume = float(generation_settings.get("bgm_volume", 0.20))
        except (TypeError, ValueError) as exc:
            raise ValidationException("BGM 音量必须是 0.0 到 0.5 之间的数字。") from exc
        if not 0.0 <= bgm_volume <= 0.5:
            raise ValidationException("BGM 音量必须在 0.0 到 0.5 之间。")

        bgm_asset = await self.asset_repo.get_by_id(selected_bgm_id) if bgm_enabled and selected_bgm_id else None
        bgm_probe: MediaProbeResult | None = None
        if bgm_enabled and selected_bgm_id and not bgm_asset:
            raise ValidationException("背景音乐不存在或已被删除。")
        if bgm_asset:
            project_binding = await self.session.scalar(
                select(ProjectAssetBindingModel.id).where(
                    ProjectAssetBindingModel.project_id == task.project_id,
                    ProjectAssetBindingModel.asset_id == bgm_asset.id,
                    ProjectAssetBindingModel.purpose == "bgm",
                )
            )
            if not project_binding and not is_system_asset(bgm_asset):
                raise ValidationException("BGM 素材不属于当前项目。")
            if not is_bgm_asset(bgm_asset):
                raise ValidationException("BGM 素材必须位于 audio/bgm/ 目录并登记为 BGM 素材。")
            bgm_path = self.storage.get_path(bgm_asset.file_path)
            if not bgm_path.exists():
                raise ValidationException(f"BGM 文件不存在: {bgm_asset.file_path}")
            bgm_probe = await media_probe_service.probe(bgm_path)
            if not bgm_probe.has_audio or not bgm_probe.audio_duration:
                raise ValidationException(f"BGM 文件没有可用的音频流: {bgm_asset.file_path}")

            mix_duration = max(total_duration, 0.1)
            mix_cmd = [
                "ffmpeg", "-y", "-i", str(concat_abs_path),
                "-stream_loop", "-1", "-i", str(bgm_path),
                "-filter_complex",
                (
                    f"[0:a]aresample=async=1:first_pts=0,apad,atrim=duration={mix_duration:.3f}[voice];"
                    f"[1:a]aresample=async=1:first_pts=0,volume={bgm_volume:.3f},"
                    f"apad,atrim=duration={mix_duration:.3f}[bgm];"
                    f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
                    f"atrim=duration={mix_duration:.3f}[a]"
                ),
                "-map", "0:v:0", "-map", "[a]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-t", f"{mix_duration:.3f}", str(final_abs_path),
            ]
            await self._run_ffmpeg_command(mix_cmd, final_abs_path, timeout=120.0)
        else:
            # The intermediate is already a normalized, strictly validated
            # composition.  Copying it here avoids a second encode when no BGM
            # mix is required.
            final_abs_path.write_bytes(concat_abs_path.read_bytes())

        final_probe = await self._validate_media_file(
            final_abs_path,
            require_audio=True,
            expected_duration=total_duration,
            expected_audio_duration=total_duration,
        )
        actual_final_duration = (
            final_probe.duration_seconds
            if final_probe and final_probe.duration_seconds
            else total_duration
        )

        # 5. Save Final Video Asset
        final_asset = await self.asset_service.save_asset(
            content=final_abs_path.read_bytes(),
            file_name=f"{task.title or 'video'}.mp4",
            mime_type="video/mp4",
            asset_type=AssetType.VIDEO,
            project_id=task.project_id,
            duration_seconds=round(actual_final_duration, 2),
            metadata={
                "task_id": task_id,
                "type": "final_composition",
                "ffmpeg_commands": list(self.commands),
                "template_id": (task.generation_settings or {}).get("template_id", "image_gallery_matted"),
                "template_version": (task.generation_settings or {}).get("template_version", "1"),
                "content_mode": content_mode,
                "layout_strategy": (
                    "online_cover_blurred_background"
                    if content_mode == "online_asset"
                    else "template_full_canvas"
                ),
                "scene_render_format_version": expected_scene_render_version,
                "bgm_enabled": bool(bgm_asset),
                "bgm_asset_id": selected_bgm_id if bgm_asset else None,
                "bgm_volume": round(bgm_volume, 3) if bgm_asset else 0.0,
                "bgm_duration_seconds": bgm_probe.audio_duration if bgm_probe else None,
                "actual_duration_seconds": round(actual_final_duration, 3),
                "duration_source": "ffprobe" if final_probe else "segment_probe",
                "segment_durations_seconds": [round(value, 3) for value in clip_durations],
                "subtitle_burned": subtitle_burned,
                "subtitle_line_count": subtitle_line_count,
                "composition_format_version": self.COMPOSITION_FORMAT_VERSION,
            },
        )

        final_result = {
            "video_status": "ready",
            "final_video_asset_id": final_asset.id,
            "final_video_url": self.storage.get_url(final_asset.file_path),
            "final_video_path": final_asset.file_path,
            "template_id": (task.generation_settings or {}).get("template_id", "image_gallery_matted"),
            "template_version": (task.generation_settings or {}).get("template_version", "1"),
            "content_mode": (task.generation_settings or {}).get("content_mode", "generated_image"),
            "total_duration": round(actual_final_duration, 2),
            "total_duration_seconds": round(actual_final_duration, 2),
            "bgm_enabled": bool(bgm_asset),
            "bgm_asset_id": selected_bgm_id if bgm_asset else None,
            "bgm_volume": round(bgm_volume, 3) if bgm_asset else 0.0,
            "subtitle_burned": subtitle_burned,
            "subtitle_line_count": subtitle_line_count,
            "research": (task.generation_settings or {}).get("research"),
            "metadata": (task.generation_settings or {}).get("metadata"),
            "composed_at": datetime.now(UTC).isoformat(),
        }
        final_asset.metadata_json = {
            **(final_asset.metadata_json or {}),
            "production_result": final_result,
        }
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.session.commit()

        logger.info(
            f"Final task video composed successfully: {final_asset.id} (URL: {self.storage.get_url(final_asset.file_path)})"
        )
        return final_asset
