import asyncio
import inspect
import json
import re
import struct
import time
import uuid
import zlib
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, ProviderException, ValidationException
from src.core.security import redact_sensitive_text
from src.domain.enums import AssetType, ProductionMode, VisualRole
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.models.workflow import WorkflowJobModel
from src.providers.image.style_presets import IMAGE_STYLE_PRESETS
from src.providers.llm.protocol import StructuredOutputException
from src.providers.registry import provider_registry
from src.repositories.project_repository import ProjectRepository
from src.repositories.scene_repository import SceneRepository
from src.repositories.task_repository import TaskRepository
from src.schemas.generation import (
    KnowledgeBrief,
    PlatformMetadata,
    ResearchQueryPlan,
    ResearchQueryRecord,
    ResearchResponse,
    ResearchSource,
    ScriptGenerateRequest,
    StructuredSceneScript,
    StructuredScript,
    VisualPromptBatch,
    format_untrusted_prompt_data,
    normalize_generated_title,
)
from src.schemas.scene import SceneCreate
from src.services.asset_service import AssetService
from src.services.media_probe import media_probe_service
from src.services.prompt_observability import PromptCallContext, PromptObservationRecorder
from src.services.prompt_registry import prompt_registry
from src.services.provider_manager import ProviderManager
from src.services.scene_service import SceneService
from src.services.template_catalog import template_catalog
from src.storage.local_storage import LocalStorageService, local_storage

ONLINE_ASSET_VISUAL_PROMPT = "online_asset_search_context"

CONTENT_QUALITY_RULES = (
    "内容质量优先级必须是：事实与来源一致性 > 不确定性表达 > 旁白自然度 > 结构 > 吸引力。"
    "不得为了钩子虚构百分比、排名、唯一性、必然性或绝对化结论；无可靠来源时，禁止具体统计断言，"
    "并明确说明资料不足、存在冲突或结论仍不确定。bold_claim 只能改写可靠来源支持的结论。"
)

_PERSON_TERMS = (
    "人物", "人像", "医生", "老师", "学生", "工人", "老人", "孩子",
    "男人", "女人", "男性", "女性", "男孩", "女孩", "男士", "女士",
)
_ENGLISH_PERSON_PATTERN = re.compile(
    r"\b(?:person|people|man|woman|doctor|worker|child|boy|girl|human|portrait)\b",
    re.IGNORECASE,
)


def _source_mentions_person(source: str) -> bool:
    source_text = str(source or "").strip()
    return any(term in source_text for term in _PERSON_TERMS) or bool(
        _ENGLISH_PERSON_PATTERN.search(source_text)
    )


def build_visual_prompt_rules(*, video: bool, aspect_ratio: str, source: str = "") -> str:
    """按媒介生成视觉规则，并避免把人物专属约束泄漏到非人物画面。"""
    ratio = aspect_ratio if aspect_ratio in {"9:16", "16:9", "1:1"} else "9:16"
    orientation = {"9:16": "竖屏", "16:9": "横屏", "1:1": "方形"}[ratio]
    shared = (
        f"成片画面必须严格使用 {ratio}（{orientation}）构图，禁止在提示词中混入其他比例。"
        "只输出一条可直接用于视觉生成的中文提示词，不要解释、不要编号、不要使用 Markdown。"
        "建议按“主体、动作或状态、环境、构图与机位、光线与材质、风格、画面限制”的顺序组织，"
        "使用具体可见的名词和动词，避免抽象口号、不可验证的细节，以及无依据的人物、道具或场景。"
        "画面中禁止出现可读文字、字幕、字母、数字、标志、水印和签名。"
        "画面必须服务旁白，只呈现旁白或可靠资料支持的关键信息。"
    )
    if video:
        return (
            "这是视频生成提示词（视频画面提示词）。描述一个镜头内连续、可执行的动作，明确主体、起始状态、动作过程、结束状态、"
            "镜头运动、景别、节奏和光线变化；保持主体身份、位置、材质和空间关系连续。"
            "避免无动机切镜、形变或突然变形、闪烁、重复肢体、身份漂移和材质突变。"
            + shared
        )
    rules = (
        "这是图片生成提示词（静态图片画面提示词）。描述主体、可见动作或状态、环境、构图与机位、光线、材质和景深；"
        "优先单一明确主视觉，最多保留 1–3 个层次清晰的焦点元素，避免把多个镜头或多个时间点塞进一张图。"
        + shared
    )
    if not video and _source_mentions_person(source):
        rules += "画面确实需要人物时，要求人物完整入镜，头部、四肢（双手和双脚）自然可见，避免肢体裁切和不必要的多人。"
    return rules


def _visual_prompt_fallback(narration: str) -> str:
    """Provider 未返回提示词时，生成一条可直接使用的中文画面提示词。"""
    subject = " ".join(str(narration or "").split()).strip()[:80] or "旁白中的核心内容"
    return (
        f"电影感单镜头画面，表现旁白中的核心主体或动作：{subject}；"
        "主体清晰突出，构图简洁，前中后景层次自然，光线与情绪贴合内容；"
        "不加入旁白未提及的关键人物、道具或事实，不出现可读文字、标志、水印或签名。"
    )


def format_knowledge_brief(payload: ScriptGenerateRequest) -> str:
    brief = knowledge_brief_for_payload(payload)
    if not brief.model_dump(exclude_none=True, exclude_defaults=True):
        return ""
    return format_untrusted_prompt_data(
        json.dumps(brief.model_dump(exclude_none=True, exclude_defaults=True), ensure_ascii=False),
        label="knowledge_brief",
        max_chars=5000,
    )

# ==================== GENRE & STYLE GUIDES ====================
GENRE_INSTRUCTIONS = {
    "science_tech": "科普解说与前沿科技：用生动的生活类比解释复杂机制，严谨清晰的逻辑推导，高信息密度与认知升级。",
    "business_wealth": "商业财经与财富思维：犀利的商业底层逻辑，认知升维，敏锐的市场动态洞察与高价值干货总结。",
    "emotion_growth": "个人成长与情感心理：深度情感共鸣，温暖治愈的叙事，透彻的心理学洞察与人生哲学启发。",
    "culture_history": "人文历史与传统文化：引人入胜的历史掌故，东方美学留白与禅意，深厚文化底蕴与哲学沉淀。",
    "humor_meme": "幽默段子与趣味吐槽：节奏紧凑，风趣幽默，口语化神吐槽与生动反差对比，引人入胜。",
    "product_review": "产品测评与种草体验：痛点驱动，真实场景体验，鲜明的对比，实用干货与直接价值交付。",
    "general": "通用随笔：亲切自然、诚恳生动的口语化表达，如同懂行的朋友分享实用见解。",
}

AUTO_GENRE_INSTRUCTION = (
    "自动匹配：请结合主题、完整文案和调研内容，先在以下已有题材方向中选择最合适的一项，"
    "再采用该方向的叙事语气、信息组织和表达重点。匹配结果只用于生成内容，不要输出"
    "单独的匹配结果字段，也不要把‘自动匹配’当作实际题材标签。可选方向："
    + "；".join(GENRE_INSTRUCTIONS.values())
)


def get_genre_instruction(genre: str, *, fallback: str = "general") -> str:
    """Return the inline genre guidance used by the existing generation call."""
    if genre == "auto":
        return AUTO_GENRE_INSTRUCTION
    return GENRE_INSTRUCTIONS.get(genre, GENRE_INSTRUCTIONS[fallback])


def infer_visual_role(text: str) -> VisualRole:
    """Choose a conservative visual role for fixed scripts without inventing claims."""
    value = str(text or "").strip()
    if any(token in value for token in ("引用", "原话", "说道", "表示", "称：", "：“")):
        return VisualRole.QUOTE
    if any(token in value for token in ("对比", "区别", "不同", "相比", "而不是", " versus ", "vs.")):
        return VisualRole.COMPARISON
    if any(token in value for token in ("时间线", "年代", "阶段", "后来", "此前", "起初", "演变")):
        return VisualRole.TIMELINE
    if any(token in value for token in ("数据", "比例", "百分比", "增长", "下降", "%", "统计")):
        return VisualRole.DATA
    if any(token in value for token in ("第一步", "第二步", "步骤", "流程", "先", "然后", "最后")):
        return VisualRole.PROCESS
    if any(token in value for token in ("例如", "比如", "案例", "场景", "试想")):
        return VisualRole.EXAMPLE
    if any(token in value for token in ("什么是", "概念", "定义", "本质", "原理")):
        return VisualRole.CONCEPT
    return VisualRole.B_ROLL


def knowledge_brief_for_payload(payload: ScriptGenerateRequest) -> KnowledgeBrief:
    """Resolve the Knowledge Mode brief used by the canonical script contract."""
    brief = KnowledgeBrief.from_payload(payload.knowledge_brief)
    if not brief.genre or brief.genre == "auto":
        brief.genre = payload.genre or "auto"
    return brief


def normalize_knowledge_script(
    script: StructuredScript,
    *,
    payload: ScriptGenerateRequest,
) -> StructuredScript:
    """Keep claim/source references closed over the brief and source snapshot."""
    brief = script.knowledge_brief or knowledge_brief_for_payload(payload)
    requested = knowledge_brief_for_payload(payload)
    if not brief.audience and requested.audience:
        brief.audience = requested.audience
    if not brief.thesis and requested.thesis:
        brief.thesis = requested.thesis
    if not brief.viewer_takeaway and requested.viewer_takeaway:
        brief.viewer_takeaway = requested.viewer_takeaway
    if not brief.key_claims and requested.key_claims:
        brief.key_claims = list(requested.key_claims)
    if not brief.source_refs and requested.source_refs:
        brief.source_refs = list(requested.source_refs)
    if not brief.genre or brief.genre == "auto":
        brief.genre = payload.genre or requested.genre or "auto"

    allowed_sources = {
        ref
        for source in payload.research_sources
        for ref in (source.ref_id, source.url)
        if ref
    }
    source_aliases = {
        source.url: source.ref_id
        for source in payload.research_sources
        if source.url and source.ref_id
    }
    if payload.research_sources and not brief.source_refs:
        # Fixed scripts do not invent claim-level matches, but they should
        # still retain the research snapshot for later review instead of
        # silently dropping all provenance between research and storyboard.
        brief.source_refs = [source.ref_id for source in payload.research_sources if source.ref_id]
    for claim in brief.key_claims:
        claim.source_refs = list(
            dict.fromkeys(source_aliases.get(ref, ref) for ref in claim.source_refs if ref)
        )[:20]
    brief.source_refs = list(
        dict.fromkeys(source_aliases.get(ref, ref) for ref in brief.source_refs if ref)
    )[:20]
    brief.source_refs = list(
        dict.fromkeys(
            [*brief.source_refs, *(ref for claim in brief.key_claims for ref in claim.source_refs)]
        )
    )[:20]
    if allowed_sources:
        # Keep only references present in the research snapshot. User-provided
        # refs remain valid when no snapshot was supplied, preserving explicit
        # manual provenance instead of silently inventing a match.
        brief.source_refs = [ref for ref in brief.source_refs if ref in allowed_sources]
        for claim in brief.key_claims:
            claim.source_refs = [ref for ref in claim.source_refs if ref in allowed_sources]

    for scene in script.scenes:
        scene.source_refs = list(
            dict.fromkeys(source_aliases.get(ref, ref) for ref in scene.source_refs if ref)
        )
    brief.source_refs = list(
        dict.fromkeys(
            [*brief.source_refs, *(ref for scene in script.scenes for ref in scene.source_refs)]
        )
    )[:20]
    if allowed_sources:
        brief.source_refs = [ref for ref in brief.source_refs if ref in allowed_sources]

    claim_ids = {claim.id for claim in brief.key_claims}
    source_refs = set(brief.source_refs)
    for scene in script.scenes:
        scene.visual_role = infer_visual_role(scene.narration_text) if not scene.visual_role else scene.visual_role
        scene.claim_refs = list(dict.fromkeys(ref for ref in scene.claim_refs if ref in claim_ids))
        scene.source_refs = [ref for ref in scene.source_refs if ref in source_refs]
    script.knowledge_brief = brief
    return script


# ==================== 3-SECOND GOLDEN HOOK STRATEGIES ====================
HOOK_INSTRUCTIONS = {
    "bold_claim": "第一分镜可用来源充分支持的反直觉结论开篇；来源不足时改用问题或有限结论，不得夸大。",
    "curiosity_gap": "第一分镜黄金3秒必须以极具悬念的反问或反直觉谜题开篇，制造强烈的求知欲与好奇心。",
    "mistake_warning": "第一分镜以有事实依据的避坑警示或常见误区开篇，不虚构比例或普遍性。",
    "story_twist": "第一分镜黄金3秒必须直接切入充满戏剧性冲突或紧张悬念的故事高潮现场，迅速抓人。",
    "pain_point": "第一分镜黄金3秒必须精准刺中受众日常最感同身受的焦虑或痛点难题，引发强烈共鸣。",
}

PLATFORM_METADATA_TAGS = {
    "science_tech": ["科普", "科技"],
    "business_wealth": ["商业", "财经"],
    "emotion_growth": ["个人成长", "情感"],
    "culture_history": ["历史", "传统文化"],
    "humor_meme": ["搞笑", "幽默"],
    "product_review": ["产品测评", "好物推荐"],
    "general": ["生活分享"],
}

PLATFORM_TAG_RULES = (
    "tags 根据完整旁白提炼 3-5 个独立、简短的高价值检索话题（严格控制在 3-5 个，数量绝不能超过 5 个），不要带 #，不要重复；"
    "标签必须是纯文本，不要使用星号、反引号或 Markdown 加粗、斜体格式。"
    "优先提炼核心概念、具体实体或专业术语，再搭配 1 个领域大类标签，严禁使用整句或无意义泛词。"
    "禁止直接复用完整标题、按空格或标点拆分标题作为标签，也不要使用悬念句、评价句或营销口号。"
    "每个标签都必须有旁白内容依据，不要蹭无关热点、影视作品或人物；不要仅因视频由 AI 生成就加 AI创作。"
)

# These are intentionally static so offline tests can audit the logical LLM
# budget without introducing a persistence or workflow-observability layer.
PROMPT_CALL_BUDGETS = {
    "research_query": {"max_calls": 1, "temperature": 0.0, "max_tokens": 1200},
    "script_structured": {"max_calls": 1, "temperature": 0.7, "max_tokens": 6000},
    "script_format_fallback": {"max_calls": 1, "temperature": 0.2, "max_tokens": 4000},
    "fixed_title": {"max_calls": 1, "temperature": 0.4, "max_tokens": 120},
    "fixed_visual_batch": {"max_calls": 1, "temperature": 0.5, "max_tokens": 3600},
    "platform_metadata": {"max_calls": 1, "temperature": 0.2, "max_tokens": 800},
    "metadata_regenerate": {"max_calls": 1, "temperature": 0.2, "max_tokens": 1000},
}


def split_narration_script(text: str, split_mode: str = "paragraph") -> list[str]:
    """Split raw text script into scene narrations according to split_mode"""
    if not text or not text.strip():
        return []
    cleaned = text.strip()

    if split_mode == "line":
        parts = [p.strip() for p in cleaned.splitlines() if p.strip()]
    elif split_mode == "sentence":
        # Split by punctuation
        raw_parts = [p.strip() for p in re.split(r"([。！？!?;；\n]+)", cleaned) if p.strip()]
        parts = []
        temp = ""
        for p in raw_parts:
            temp += p
            if len(temp) >= 12 or any(punct in p for punct in "。！？!?\n"):
                parts.append(temp.strip())
                temp = ""
        if temp.strip():
            parts.append(temp.strip())
    else:  # paragraph
        parts = [p.strip() for p in re.split(r"\n\s*\n+", cleaned) if p.strip()]

    return parts or [cleaned]


def create_solid_color_png(
    width: int = 720, height: int = 1280, color: tuple[int, int, int] = (24, 24, 30)
) -> bytes:
    """Generate a valid solid color PNG in pure Python with zero external dependencies"""
    r, g, b = color
    row_bytes = b"\x00" + bytes([r, g, b] * width)
    raw_data = row_bytes * height
    compressed_data = zlib.compress(raw_data, 9)

    png = b"\x89PNG\r\n\x1a\n"
    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png += struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data))
    # IDAT
    png += struct.pack(">I", len(compressed_data)) + b"IDAT" + compressed_data + struct.pack(">I", zlib.crc32(b"IDAT" + compressed_data))
    # IEND
    png += struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    return png


def parse_script_from_text(
    raw_text: str, default_topic: str = "短视频创作", style_desc: str = ""
) -> StructuredScript:
    """从 Markdown 或自由格式的模型文本中解析结构化脚本。"""
    # The text fallback keeps the structured-generation system prompt, so a
    # provider may still return a JSON entity. Parse that shape before the
    # line-oriented compatibility parser; otherwise the whole JSON document is
    # mistaken for one narration and the requested scene count is lost.
    json_candidates: list[str] = []
    stripped = raw_text.strip().lstrip("\ufeff")
    json_candidates.append(stripped)
    json_candidates.extend(
        match.group(1).strip()
        for match in re.finditer(
            r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, re.IGNORECASE
        )
    )
    decoder = json.JSONDecoder()
    for candidate in dict.fromkeys(item for item in json_candidates if item):
        parsed_values: list[Any] = []
        try:
            parsed_values.append(json.loads(candidate))
        except (TypeError, json.JSONDecodeError):
            pass
        for match in re.finditer(r"\{", candidate):
            try:
                parsed, _ = decoder.raw_decode(candidate[match.start() :])
            except json.JSONDecodeError:
                continue
            parsed_values.append(parsed)
        for parsed in parsed_values:
            if not isinstance(parsed, dict) or not isinstance(parsed.get("scenes"), list):
                continue
            values = dict(parsed)
            values.setdefault("title", default_topic)
            values.setdefault("hook", "先从已有信息梳理这个问题")
            values.setdefault(
                "narration",
                "\n".join(
                    str(scene.get("narration_text", "")).strip()
                    for scene in values["scenes"]
                    if isinstance(scene, dict) and scene.get("narration_text")
                ),
            )
            try:
                script = StructuredScript.model_validate(values)
            except Exception:
                # A malformed optional Knowledge Brief must not discard valid
                # scenes produced by the compatibility fallback.
                values.pop("knowledge_brief", None)
                try:
                    script = StructuredScript.model_validate(values)
                except Exception:
                    continue
            for scene in script.scenes:
                if style_desc and style_desc not in scene.visual_prompt:
                    scene.visual_prompt = f"{style_desc}, {scene.visual_prompt}"
            return script

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    title = default_topic
    hook = "先从已有信息梳理这个问题"
    narration_lines = []
    scenes = []

    current_narration = ""
    current_visual = ""
    current_badge = ""

    for line in lines:
        if line.startswith("#") or "标题" in line or "Title" in line:
            clean = re.sub(r"^[#\s*]*[标题Title]*[:：\s]*", "", line).strip().strip('"').strip("'")
            if clean:
                title = clean
        elif "钩子" in line or "Hook" in line:
            clean = re.sub(r"^[#\s*]*[黄金3秒钩子Hook]*[:：\s]*", "", line).strip()
            if clean:
                hook = clean
        elif re.match(r"^分镜\s*\d+|^\d+[\.、]|^Scene\s*\d+", line, re.IGNORECASE):
            if current_narration:
                vp = current_visual or _visual_prompt_fallback(current_narration)
                if style_desc and style_desc not in vp:
                    vp = f"{style_desc}, {vp}"
                scenes.append(
                    StructuredSceneScript(
                        sequence_index=len(scenes),
                        narration_text=current_narration,
                        visual_prompt=vp,
                        badge_text=current_badge or f"Part {len(scenes) + 1}",
                        visual_role=infer_visual_role(current_narration),
                    )
                )
                narration_lines.append(current_narration)
                current_narration = ""
                current_visual = ""
                current_badge = ""
            current_badge = line[:15]
        elif "旁白" in line or "台词" in line or "Narration" in line:
            clean = re.sub(r"^[*#\s]*[旁白台词Narration]*[:：\s]*", "", line).strip()
            current_narration = clean
        elif "画面" in line or "Prompt" in line or "Visual" in line:
            clean = re.sub(r"^[*#\s]*[画面提示词Visual Prompt]*[:：\s]*", "", line).strip()
            current_visual = clean
        else:
            if not current_narration and len(line) > 5 and not line.startswith("{") and not line.startswith("}"):
                current_narration = line

    if current_narration:
        vp = current_visual or _visual_prompt_fallback(current_narration)
        if style_desc and style_desc not in vp:
            vp = f"{style_desc}, {vp}"
        scenes.append(
            StructuredSceneScript(
                sequence_index=len(scenes),
                narration_text=current_narration,
                visual_prompt=vp,
                badge_text=current_badge or f"Part {len(scenes) + 1}",
                visual_role=infer_visual_role(current_narration),
            )
        )
        narration_lines.append(current_narration)

    if not scenes:
        parts = split_narration_script(raw_text, "paragraph")
        scenes = [
            StructuredSceneScript(
                sequence_index=i,
                narration_text=p,
                visual_prompt=(
                    f"{style_desc}, {_visual_prompt_fallback(p)}"
                    if style_desc
                    else _visual_prompt_fallback(p)
                ),
                badge_text=f"Part {i + 1}",
                visual_role=infer_visual_role(p),
            )
            for i, p in enumerate(parts)
        ]
        narration_lines = parts

    return StructuredScript(
        title=title,
        hook=hook or (scenes[0].narration_text if scenes else "精彩内容即将呈现"),
        narration="\n".join(narration_lines) or raw_text[:200],
        scenes=scenes or [
            StructuredSceneScript(
                sequence_index=0,
                narration_text=default_topic,
                visual_prompt=(
                    f"{style_desc}, {_visual_prompt_fallback(default_topic)}"
                    if style_desc
                    else _visual_prompt_fallback(default_topic)
                ),
                visual_role=infer_visual_role(default_topic),
            )
        ],
        knowledge_brief=KnowledgeBrief(thesis=title, genre="auto"),
    )


class GenerationService:
    """Application service orchestrating AI providers for Research, Script, TTS, Image, and Video"""

    def __init__(
        self,
        session: AsyncSession,
        storage: LocalStorageService = local_storage,
        provider_manager: ProviderManager | None = None,
        execution_context=None,
        task_id: str | None = None,
        job_id: str | None = None,
        production_settings: dict[str, Any] | None = None,
    ):
        self.session = session
        self.execution_context = execution_context
        self.storage = storage
        self.provider_manager = provider_manager or ProviderManager(session)
        self.production_settings = production_settings
        self.task_repo = TaskRepository(session)
        self.scene_repo = SceneRepository(session)
        self.project_repo = ProjectRepository(session)
        self.scene_service = SceneService(session, execution_context=execution_context)
        self.asset_service = AssetService(session, storage=storage, execution_context=execution_context)
        self.prompt_downgrade_counts: dict[str, int] = {}
        self.prompt_observations = PromptObservationRecorder(
            session, task_id=task_id, job_id=job_id
        )

    def _task_settings(self, task: TaskModel | None) -> dict[str, Any]:
        if self.production_settings is not None:
            return self.production_settings
        return (task.generation_settings if task else {}) or {}

    @staticmethod
    def _prompt_spec(prompt_id: str, prompt_versions: dict[str, str] | None = None):
        return prompt_registry.resolve(prompt_id, prompt_versions)

    async def _llm_text(
        self,
        provider,
        prompt_id: str,
        prompt: str,
        *,
        prompt_versions: dict[str, str] | None = None,
        system_prompt: str | None = None,
        temperature: float,
        max_tokens: int,
    ) -> str:
        spec = self._prompt_spec(prompt_id, prompt_versions)
        rendered_prompt = f"[prompt_contract:{spec.prompt_id}/{spec.version}]\n{spec.template}\n\n{prompt}"
        context = PromptCallContext(
            spec,
            temperature=temperature,
            max_tokens=max_tokens,
            mode="text",
        )
        self._last_prompt_context = context
        kwargs = {"temperature": temperature, "max_tokens": max_tokens}
        if system_prompt is not None:
            kwargs["system_prompt"] = system_prompt
        return await self.prompt_observations.observe(
            provider,
            context,
            prompt=rendered_prompt,
            system_prompt=system_prompt,
            operation=lambda: provider.generate_text(prompt=rendered_prompt, **kwargs),
        )

    async def _llm_structured(
        self,
        provider,
        prompt_id: str,
        prompt: str,
        schema_class,
        *,
        prompt_versions: dict[str, str] | None = None,
        system_prompt: str | None = None,
        temperature: float,
        max_tokens: int,
    ):
        spec = self._prompt_spec(prompt_id, prompt_versions)
        rendered_prompt = f"[prompt_contract:{spec.prompt_id}/{spec.version}]\n{spec.template}\n\n{prompt}"
        context = PromptCallContext(
            spec,
            temperature=temperature,
            max_tokens=max_tokens,
            mode="structured",
            native_json_schema=bool(getattr(provider, "supports_native_json_schema", False)),
        )
        self._last_prompt_context = context
        kwargs = {
            "prompt": rendered_prompt,
            "schema_class": schema_class,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt is not None:
            kwargs["system_prompt"] = system_prompt

        async def awaitable():
            return await provider.generate_structured(**kwargs)

        result = await self.prompt_observations.observe(
            provider,
            context,
            prompt=rendered_prompt,
            system_prompt=system_prompt,
            operation=awaitable,
        )
        return result

    async def _mark_prompt_fallback(
        self, context: PromptCallContext | None, count: int = 1
    ) -> None:
        if context is not None:
            await self.prompt_observations.mark_fallback(context, count)

    def _record_prompt_downgrade(self, name: str, count: int, reason: str) -> None:
        if count <= 0:
            return
        self.prompt_downgrade_counts[name] = self.prompt_downgrade_counts.get(name, 0) + count
        logger.warning(
            "Prompt batch downgraded deterministically: name={}, items={}, reason={}",
            name,
            count,
            redact_sensitive_text(reason) or type(reason).__name__,
        )

    @staticmethod
    def _fixed_visual_fallback(narration: str, style_desc: str) -> str:
        prompt = _visual_prompt_fallback(narration)
        return f"{style_desc}, {prompt}" if style_desc else prompt

    @staticmethod
    def _normalize_visual_batch(
        batch: VisualPromptBatch, expected_count: int
    ) -> tuple[list[str | None], list[int]]:
        items = getattr(batch, "items", None)
        if not isinstance(items, list) or len(items) != expected_count:
            actual = len(items) if isinstance(items, list) else 0
            raise ValueError(f"批量视觉提示词数量错误：期望 {expected_count} 项，实际 {actual} 项。")

        indexes = [item.sequence_index for item in items]
        expected_indexes = list(range(expected_count))
        if indexes != expected_indexes:
            raise ValueError(
                f"批量视觉提示词索引错误：期望连续索引 {expected_indexes}，实际 {indexes}。"
            )

        prompts: list[str | None] = [None] * expected_count
        blank_indexes: list[int] = []
        for item in items:
            prompt = (item.visual_prompt or "").strip()
            prompts[item.sequence_index] = prompt or None
            if not prompt:
                blank_indexes.append(item.sequence_index)
        return prompts, blank_indexes

    async def _generate_fixed_visual_prompts(
        self,
        llm_provider,
        *,
        narrations: list[str],
        style_desc: str,
        content_mode: str | None,
        aspect_ratio: str,
        research_hint: str,
        prompt_versions: dict[str, str] | None = None,
    ) -> list[str]:
        """一次生成固定文案的画面提示词，并保持旁白与索引一一对应。"""
        visual_rules = build_visual_prompt_rules(
            video=content_mode == "generated_video",
            aspect_ratio=aspect_ratio,
            source="\n".join(narrations),
        )
        system_prompt = (
            "你是短视频分镜的批量视觉提示词编辑。只处理输入的旁白，不改写、合并、复制或编造旁白。"
            "必须返回一个 JSON 数据对象，顶层字段为 items；每个输入 sequence_index 恰好对应一个输出项，"
            "索引必须从 0 连续递增，visual_prompt 必须是非空、可直接用于视觉生成的中文提示词。"
            "画面规划先判断信息角色，再决定构图；可使用 concept、process、comparison、timeline、data、example、quote、b_roll。"
            f"\n{visual_rules}\n"
            "输出对象不能包含 Markdown、解释或额外字段。"
        )
        batch_input = [
            {
                "sequence_index": index,
                "narration_text": narration,
                "suggested_visual_role": infer_visual_role(narration).value,
            }
            for index, narration in enumerate(narrations)
        ]
        prompt = (
            "请为下列固定旁白批量生成画面提示词。每一项只描述对应旁白可支持的画面，"
            "不得改变旁白顺序或为缺失项编造内容。\n"
            f"目标视觉风格：{format_untrusted_prompt_data(style_desc, label='visual_style', max_chars=1200)}\n"
            f"分镜输入：{format_untrusted_prompt_data(json.dumps(batch_input, ensure_ascii=False), label='scene_batch', max_chars=10000)}"
        )
        if research_hint:
            prompt += (
                "\n研究资料只能用于补充可核对的视觉细节，不得改写旁白：\n"
                + format_untrusted_prompt_data(research_hint, max_chars=1800)
            )

        try:
            batch = await self._llm_structured(
                llm_provider,
                "visual.fixed_batch",
                prompt,
                VisualPromptBatch,
                prompt_versions=prompt_versions,
                system_prompt=system_prompt,
                temperature=PROMPT_CALL_BUDGETS["fixed_visual_batch"]["temperature"],
                max_tokens=PROMPT_CALL_BUDGETS["fixed_visual_batch"]["max_tokens"],
            )
            batch_context = self._last_prompt_context
            prompts, blank_indexes = self._normalize_visual_batch(batch, len(narrations))
            if blank_indexes:
                self._record_prompt_downgrade(
                    "fixed_visual_batch",
                    len(blank_indexes),
                    f"空 visual_prompt 索引={blank_indexes}",
                )
                await self._mark_prompt_fallback(batch_context, len(blank_indexes))
            return [
                (
                    f"{style_desc}, {prompt}" if style_desc and prompt and style_desc not in prompt else prompt
                )
                if prompt
                else self._fixed_visual_fallback(narration, style_desc)
                for narration, prompt in zip(narrations, prompts, strict=True)
            ]
        except ProviderException:
            raise
        except ValidationException:
            raise
        except StructuredOutputException as exc:
            self._record_prompt_downgrade(
                "fixed_visual_batch",
                len(narrations),
                f"结构化输出失败：{redact_sensitive_text(str(exc)) or type(exc).__name__}",
            )
            await self._mark_prompt_fallback(
                getattr(self, "_last_prompt_context", None), len(narrations)
            )
        except Exception as exc:
            self._record_prompt_downgrade(
                "fixed_visual_batch",
                len(narrations),
                f"批量契约校验失败：{redact_sensitive_text(str(exc)) or type(exc).__name__}",
            )
            await self._mark_prompt_fallback(
                getattr(self, "_last_prompt_context", None), len(narrations)
            )

        return [self._fixed_visual_fallback(narration, style_desc) for narration in narrations]

    async def _set_scene_generation_status(
        self, scene: SceneModel, kind: str, status: str, error: str | None = None
    ) -> None:
        """Persist scene-level generation state for UI diagnostics and retries."""
        params = dict(scene.layout_params or {})
        params[f"{kind}_status"] = status
        if error:
            params[f"{kind}_error"] = error[:1000]
        else:
            params.pop(f"{kind}_error", None)
        scene.layout_params = params
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.scene_repo.update(scene)
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.session.flush()
        await self.session.commit()

    async def _get_search_provider(self, provider_id: str | None = None):
        """Resolve search in task-specific, persisted, then runtime order.

        A provider row with usable credentials is authoritative.  The registry
        is kept as a dependency-injection fallback for the test/mock runtime
        when the bootstrap Tavily row is only an unconfigured placeholder; a
        configured provider exception is never replaced after a request fails.
        """
        if provider_id:
            return await self.provider_manager.get_search(provider_id)

        configured = await self.provider_manager.resolve_config("search")
        if configured:
            if configured.has_credentials:
                return await self.provider_manager.get_search()
            # The bundled bootstrap row has no secret in a local/test install.
            # An injected mock is an explicit runtime adapter, not a silent
            # fallback after a configured network request has failed.
            if provider_registry._search_provider is not None:
                return provider_registry.search
            return await self.provider_manager.get_search()

        if provider_registry._search_provider is not None:
            return provider_registry.search
        return None

    async def _get_llm_provider(self):
        if provider_registry._llm_provider is not None:
            return provider_registry.llm
        return await self.provider_manager.get_llm()

    async def _get_tts_provider(self):
        if getattr(provider_registry._tts_provider, "name", None) == "mock":
            return provider_registry.tts
        return await self.provider_manager.get_tts()

    async def _get_image_provider(self):
        configured = await self.provider_manager.resolve_config("image")
        if getattr(provider_registry._image_provider, "name", None) == "mock":
            return provider_registry.image
        return await self.provider_manager.get_image() if configured is not None else None

    async def _get_video_provider(self):
        configured = await self.provider_manager.resolve_config("video")
        if getattr(provider_registry._video_provider, "name", None) == "mock":
            return provider_registry.video
        return await self.provider_manager.get_video() if configured is not None else None

    @staticmethod
    def _default_media_dimensions(aspect_ratio: str) -> tuple[int, int]:
        return {
            "9:16": (720, 1280),
            "16:9": (1280, 720),
            "1:1": (1024, 1024),
        }.get(aspect_ratio, (1024, 1024))

    def _resolve_template_media(
        self, task: TaskModel | None, project_aspect_ratio: str
    ) -> tuple[str, int, int]:
        """Use the selected template's media contract, as the Demo does."""
        payload = self._task_settings(task)
        template_id = payload.get("template_id", "image_gallery_matted")
        template = template_catalog.get(template_id)
        if not template:
            width, height = self._default_media_dimensions(project_aspect_ratio)
            return project_aspect_ratio, width, height

        width, height = template_catalog.get_media_size(template_id)
        aspect_ratio = template_catalog.get_media_aspect_ratio(
            template_id, project_aspect_ratio
        )
        return aspect_ratio, width, height

    @staticmethod
    def _parse_platform_metadata_response(raw_response: str) -> PlatformMetadata:
        """Parse the small JSON contract used for platform publishing metadata."""
        if not raw_response or not raw_response.strip():
            raise ValueError("LLM 未返回平台发布元数据。")

        text = raw_response.strip()
        candidates = [text]
        code_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if code_match:
            candidates.insert(0, code_match.group(1).strip())
        object_start, object_end = text.find("{"), text.rfind("}")
        if object_start >= 0 and object_end > object_start:
            candidates.append(text[object_start : object_end + 1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(parsed, dict):
                continue
            metadata = parsed.get("metadata")
            if isinstance(metadata, dict):
                parsed = metadata
            return PlatformMetadata.model_validate(parsed)

        raise ValueError("LLM 平台发布元数据不是有效的 JSON 对象。")

    @staticmethod
    def _filter_platform_tags(tags: list[str], title: str) -> list[str]:
        """Reject whole-title echoes and long title clauses, retaining topic nouns."""
        def key(text: str) -> str:
            return re.sub(r"[\W_]+", "", text).casefold()

        title_keys = {key(title)}
        title_keys.update(
            key(part) for part in re.split(r"[\s，。！？!?：:；;、,.]+", title)
            if len(key(part)) >= 6
        )
        # Filter before the schema's five-tag limit. Otherwise a title echo in
        # the first five candidates can hide valid topic tags that follow it.
        values = [tags] if isinstance(tags, str) else tags or []
        normalized = []
        seen = set()
        for value in values:
            tag = str(value).strip().lstrip("#")
            tag = re.sub(r"[\s,，。！？!?：:；;、]+", "", tag)
            tag_key = key(tag)
            if not tag_key or tag_key in seen or tag_key in title_keys:
                continue
            seen.add(tag_key)
            normalized.append(tag)
        return normalized

    @staticmethod
    def _default_platform_metadata(
        *, title: str, hook: str, narration: str, topic: str, genre: str
    ) -> PlatformMetadata:
        """Create a publishable fallback when a provider omits metadata."""
        tags = list(PLATFORM_METADATA_TAGS.get(genre, PLATFORM_METADATA_TAGS["general"]))
        description = (hook or narration or f"一起了解{topic or '这个主题'}。").strip()
        if description and "评论" not in description:
            description = f"{description} 欢迎在评论区分享你的看法。"
        return PlatformMetadata(
            title=title,
            description=description,
            tags=tags,
            declaration="内容由AI生成",
        )

    @classmethod
    def _finalize_script_metadata(
        cls, script: StructuredScript, *, topic: str, genre: str
    ) -> StructuredScript:
        """Normalize generated metadata and keep it aligned with the script title."""
        clean_title = normalize_generated_title(script.title or topic or "精彩短视频") or "精彩短视频"
        script.title = clean_title

        metadata = script.metadata or PlatformMetadata()
        metadata.tags = cls._filter_platform_tags(metadata.tags, script.title)[:5]
        if not metadata.description or not metadata.tags:
            fallback = cls._default_platform_metadata(
                title=clean_title,
                hook=script.hook,
                narration=script.narration,
                topic=topic,
                genre=genre,
            )
            if not metadata.description:
                metadata.description = fallback.description
            if not metadata.tags:
                metadata.tags = cls._filter_platform_tags(fallback.tags, script.title)[:5]
            if not metadata.declaration:
                metadata.declaration = fallback.declaration

        metadata.title = clean_title
        # Re-validate after mutating an LLM response so tags are deduplicated,
        # hash-prefixed tags are removed, and platform limits are enforced.
        script.metadata = PlatformMetadata.model_validate(metadata.model_dump())
        return script

    async def _generate_platform_metadata(
        self,
        llm_provider,
        *,
        title: str,
        hook: str,
        narration: str,
        topic: str,
        genre: str,
        research_hint: str = "",
        prompt_versions: dict[str, str] | None = None,
    ) -> PlatformMetadata | None:
        """Generate the platform publishing fields for fixed/raw-script mode."""
        genre_hint = get_genre_instruction(genre)
        genre_guidance = (
            f"内容领域与表达方向：{genre_hint}\n" if genre == "auto" else ""
        )
        system_prompt = (
            "你是短视频平台运营编辑。请为下面的抖音短视频生成发布元数据，"
            "元数据只能重组标题和旁白中已有的事实，不得补充新结论。只输出合法 JSON 对象："
            '{"description":"...","tags":["标签1","标签2"],"declaration":"内容由AI生成"}。\n'
            "要求：description 用与内容相同的语言写 1-3 句自然、有信息量的发布文案，"
            "概括核心价值；邀请用户评论是可选的，不要强行互动。"
            f"{CONTENT_QUALITY_RULES}"
            f"{PLATFORM_TAG_RULES}\n"
            f"{genre_guidance}"
            "declaration 从‘内容由AI生成’、‘内容取材网络’、"
            "‘个人观点，仅供参考’中选择最合适的一项。"
        )
        prompt = (
            "发布元数据输入：\n"
            f"主题：{topic or '短视频创作'}\n"
            f"内容领域：{'自动匹配' if genre == 'auto' else genre}\n"
            f"标题：{title}\n"
            f"钩子：{hook}\n"
            f"完整旁白：{narration[:4000]}"
        )
        if genre == "auto":
            prompt += f"\n题材表达方向：{genre_hint}"
        if research_hint:
            prompt += "\n" + format_untrusted_prompt_data(research_hint, max_chars=1800)
        try:
            raw_response = await self._llm_text(
                llm_provider,
                "metadata.platform",
                prompt,
                prompt_versions=prompt_versions,
                system_prompt=system_prompt,
                temperature=PROMPT_CALL_BUDGETS["platform_metadata"]["temperature"],
                max_tokens=PROMPT_CALL_BUDGETS["platform_metadata"]["max_tokens"],
            )
            return self._parse_platform_metadata_response(raw_response)
        except ProviderException:
            raise
        except ValidationException:
            raise
        except Exception as exc:
            logger.warning(
                "Platform metadata generation failed, using deterministic fallback: {}",
                redact_sensitive_text(str(exc)) or type(exc).__name__,
            )
            await self._mark_prompt_fallback(
                getattr(self, "_last_prompt_context", None), 1
            )
            return None

    @staticmethod
    def _research_topic_keywords(topic: str) -> list[str]:
        """Extract short anchors so fallback queries never copy the full topic."""
        text = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff-]+", " ", topic.strip())
        stop_phrases = (
            "请帮我写一篇",
            "请介绍一下",
            "我想知道",
            "短视频文案",
            "短视频脚本",
            "视频文案",
            "视频脚本",
            "介绍一下",
            "什么是",
            "请介绍",
            "帮我写",
            "帮我",
            "关于",
            "介绍",
            "讲讲",
            "如何",
            "为什么",
            "生成",
            "创作",
            "分析",
            "探讨",
            "了解",
            "的",
            "和",
            "与",
            "及",
        )
        for phrase in sorted(stop_phrases, key=len, reverse=True):
            text = text.replace(phrase, " ")

        fragments: list[str] = []
        for token in re.findall(r"[A-Za-z0-9-]+|[\u4e00-\u9fff]+", text):
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                if len(token) <= 2:
                    parts = [token]
                else:
                    split_at = max(2, (len(token) + 1) // 2)
                    parts = [token[:split_at], token[split_at:]]
            else:
                parts = [token]
            fragments.extend(part for part in parts if part)

        return list(dict.fromkeys(fragments))

    @staticmethod
    def _research_query_key(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", " ", value).strip().casefold()

    @classmethod
    def _is_topic_echo(cls, query: str, topic: str) -> bool:
        topic_key = cls._research_query_key(topic)
        query_key = cls._research_query_key(query)
        if not topic_key or not query_key:
            return False
        topic_compact = topic_key.replace(" ", "")
        query_compact = query_key.replace(" ", "")
        return topic_key in query_key or (
            len(topic_compact) >= 2 and topic_compact in query_compact
        )

    @classmethod
    def _filter_research_queries(
        cls, queries: list[str], topic: str, max_queries: int
    ) -> list[str]:
        filtered: list[str] = []
        for query in queries:
            if cls._is_topic_echo(query, topic):
                continue
            if query not in filtered:
                filtered.append(query)
        return filtered[:max_queries]

    @classmethod
    def _heuristic_research_queries(cls, topic: str, max_queries: int) -> list[str]:
        if not topic.strip():
            return []

        keywords = cls._research_topic_keywords(topic)
        aspects = ("核心机制 权威资料", "关键数据 研究进展", "争议应用 案例")
        candidates = []
        for index, aspect in enumerate(aspects):
            anchor = keywords[index % len(keywords)] if keywords else ""
            query = " ".join(part for part in (anchor, aspect) if part)
            if not cls._is_topic_echo(query, topic):
                candidates.append(query)

        if not candidates:
            candidates = list(aspects)
        return list(dict.fromkeys(candidates))[:max_queries]

    @staticmethod
    def _parse_research_query_response(raw_response: str, max_queries: int) -> list[str]:
        """Parse the query-planning JSON contract from common provider shapes."""
        if not isinstance(raw_response, str) or not raw_response.strip():
            raise ValueError("LLM 未返回查询语句。")

        text = raw_response.strip().lstrip("\ufeff")
        text_without_thinking = re.sub(
            r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE
        ).strip()
        code_matches = re.findall(
            r"```(?:json)?\s*([\s\S]*?)\s*```",
            text_without_thinking,
            re.IGNORECASE,
        )
        candidates = [*code_matches]
        if text_without_thinking and text_without_thinking != text:
            candidates.append(text_without_thinking)
        candidates.append(text)
        decoder = json.JSONDecoder()
        saw_json_start = False

        def extract_queries(parsed: object) -> list[str] | None:
            if isinstance(parsed, dict):
                raw_queries = parsed.get("queries")
                if raw_queries is None:
                    raw_queries = parsed.get("data")
                if raw_queries is None:
                    response = parsed.get("response")
                    if isinstance(response, dict):
                        raw_queries = response.get("queries")
                        if raw_queries is None:
                            raw_queries = response.get("data")
            else:
                raw_queries = parsed

            if not isinstance(raw_queries, list):
                return None

            queries: list[str] = []
            for value in raw_queries:
                if not isinstance(value, str):
                    continue
                query = re.sub(r"\s+", " ", value).strip().strip('"\'')
                if re.fullmatch(r"(?:查询语句|query)\s*\d+", query, re.IGNORECASE):
                    continue
                if query and query not in queries:
                    queries.append(query[:300])
            return queries

        for candidate in candidates:
            variants = [
                candidate.strip(),
                re.sub(r",\s*([}\]])", r"\1", candidate.strip()),
            ]
            parsed = None
            for variant in dict.fromkeys(variants):
                if not variant:
                    continue
                try:
                    parsed = json.loads(variant)
                except (TypeError, json.JSONDecodeError):
                    parsed = None

                if parsed is not None:
                    queries = extract_queries(parsed)
                    if queries:
                        return queries[:max_queries]

                for match in re.finditer(r"[\[{]", variant):
                    saw_json_start = True
                    try:
                        parsed, _ = decoder.raw_decode(variant[match.start() :])
                    except json.JSONDecodeError:
                        continue

                    queries = extract_queries(parsed)
                    if queries:
                        return queries[:max_queries]

        if saw_json_start:
            raise ValueError("LLM 未找到有效查询列表（JSON 可能被截断或格式不兼容）。")
        raise ValueError("LLM 未找到有效查询列表。")

    async def _generate_research_queries(
        self,
        topic: str,
        max_queries: int,
        prompt_versions: dict[str, str] | None = None,
    ) -> ResearchQueryPlan:
        """Ask the first LLM call for search queries, with a deterministic fallback."""
        fallback = self._heuristic_research_queries(topic, max_queries)
        try:
            llm_provider = await self._get_llm_provider()
            raw_response = await self._llm_text(
                llm_provider,
                "research.query_plan",
                format_untrusted_prompt_data(
                    topic, label="user_topic", max_chars=700
                ),
                prompt_versions=prompt_versions,
                system_prompt=(
                    "你是联网研究的检索策划师。请根据用户主题设计互补、可检索、尽量具体的查询语句，"
                    f"最多生成 {max_queries} 条。覆盖主题定义/核心事实、最新进展或数据、争议与应用中的不同角度。"
                    "不要把用户主题原样作为查询，也不要在完整主题后面简单拼接‘最新进展’等后缀；"
                    "应先提炼短关键词，再组合不同研究角度。不要生成 URL，不要回答主题，不要输出解释，只输出合法 JSON："
                    '{"queries":["查询语句1","查询语句2"]}。'
                ),
                temperature=PROMPT_CALL_BUDGETS["research_query"]["temperature"],
                max_tokens=PROMPT_CALL_BUDGETS["research_query"]["max_tokens"],
            )
            queries = self._parse_research_query_response(raw_response, max_queries)
            queries = self._filter_research_queries(queries, topic, max_queries)
            if not queries:
                raise ValueError("LLM 查询结果原样复用了用户主题。")
            return ResearchQueryPlan(queries=queries, query_source="llm")
        except ValidationException:
            raise
        except Exception as exc:
            safe_error = redact_sensitive_text(str(exc)) or type(exc).__name__
            logger.warning("LLM query planning failed, using heuristic queries: {}", safe_error)
            await self._mark_prompt_fallback(
                getattr(self, "_last_prompt_context", None), 1
            )
            return ResearchQueryPlan(
                queries=fallback,
                query_source="heuristic",
                warnings=[f"LLM 查询规划失败，已使用启发式查询：{safe_error}"],
            )

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URLs enough to deduplicate equivalent source links."""
        value = (url or "").strip()
        if not value:
            return ""
        try:
            parts = urlsplit(value)
            if not parts.scheme or not parts.netloc:
                return value.rstrip("/")
            scheme = parts.scheme.lower()
            netloc = parts.netloc.lower()
            if (scheme == "https" and netloc.endswith(":443")) or (
                scheme == "http" and netloc.endswith(":80")
            ):
                netloc = netloc.rsplit(":", 1)[0]
            query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
            path = parts.path.rstrip("/") or "/"
            return urlunsplit((scheme, netloc, path, query, ""))
        except ValueError:
            return value.rstrip("/")

    async def research_topic(
        self,
        topic: str,
        max_results: int = 5,
        *,
        max_queries: int = 3,
        search_provider_id: str | None = None,
        prompt_versions: dict[str, str] | None = None,
    ) -> ResearchResponse:
        """Run bounded multi-query research without hiding provider failures."""
        topic = topic.strip()
        max_queries = max(1, min(3, int(max_queries or 3)))
        max_results = max(1, min(5, int(max_results or 5)))
        try:
            search_provider = await self._get_search_provider(search_provider_id)
        except Exception as exc:
            safe_error = redact_sensitive_text(str(exc)) or type(exc).__name__
            logger.warning("Search provider resolution failed: {}", safe_error)
            return ResearchResponse(
                topic=topic,
                status="failed",
                provider=None,
                summary="实时资料未使用，搜索 Provider 配置不可用。",
                error_message=safe_error,
            )

        if not search_provider:
            logger.info("Search provider not configured, skipping web research for topic: '{}'", topic)
            return ResearchResponse(
                topic=topic,
                status="skipped",
                summary="未配置可用的 Search Provider，已跳过实时检索，直接根据大模型知识库生成内容。",
                error_message="未配置可用的 Search Provider。",
            )

        if prompt_versions is None:
            query_plan = await self._generate_research_queries(topic, max_queries)
        else:
            query_plan = await self._generate_research_queries(
                topic, max_queries, prompt_versions=prompt_versions
            )
        queries = query_plan.queries[:max_queries]
        query_source = query_plan.query_source
        warnings = list(query_plan.warnings)

        logger.info(
            "Researching topic with {}: '{}' ({} queries, query_source={})",
            getattr(search_provider, "name", type(search_provider).__name__),
            topic,
            len(queries),
            query_source,
        )

        async def execute_query(query: str) -> tuple[ResearchQueryRecord, list]:
            try:
                results = list(await search_provider.search(query, max_results=max_results) or [])
                return (
                    ResearchQueryRecord(
                        query=query,
                        status="completed",
                        result_count=len(results),
                    ),
                    results,
                )
            except Exception as exc:
                safe_error = redact_sensitive_text(str(exc)) or type(exc).__name__
                logger.warning("Search query failed for '{}': {}", query, safe_error)
                return (
                    ResearchQueryRecord(
                        query=query,
                        status="failed",
                        result_count=0,
                        error_message=safe_error[:1000],
                    ),
                    [],
                )

        # Do not enter content generation until every planned search request
        # has completed, including failed requests.
        query_runs = await asyncio.gather(*(execute_query(query) for query in queries))
        query_records = [record for record, _ in query_runs]
        sources: list[ResearchSource] = []
        seen_urls: set[str] = set()
        for _, results in query_runs:
            for result in results:
                normalized_url = self._normalize_url(getattr(result, "url", ""))
                if not normalized_url or normalized_url in seen_urls:
                    continue
                seen_urls.add(normalized_url)
                score = getattr(result, "score", None)
                try:
                    score = float(score) if score is not None else None
                except (TypeError, ValueError):
                    score = None
                sources.append(
                    ResearchSource(
                        title=(getattr(result, "title", "") or normalized_url)[:500],
                        url=normalized_url,
                        snippet=(getattr(result, "snippet", "") or "")[:2000],
                        domain=urlsplit(normalized_url).netloc or None,
                        published_at=getattr(result, "published_at", None),
                        score=score,
                    )
                )

        errors = [
            f"{record.query}: {record.error_message}"
            for record in query_records
            if record.status == "failed" and record.error_message
        ]
        warnings.extend(errors)
        if not sources and not errors:
            warnings.append("所有查询均未返回有效参考源。")

        snippets = " ".join(source.snippet for source in sources[:5] if source.snippet)
        provider_name = getattr(search_provider, "name", type(search_provider).__name__)
        if sources:
            summary = f"围绕【{topic}】的核心调研发现：{snippets[:1200]}"
            if errors:
                summary += "（部分查询失败，以上为已获取资料。）"
            status = "completed"
        else:
            summary = "实时资料未使用，将继续根据大模型通用知识库创作。"
            status = "failed"

        return ResearchResponse(
            topic=topic,
            status=status,
            provider=provider_name,
            queries=queries,
            query_records=query_records,
            sources=sources,
            summary=summary,
            query_source=query_source,
            warnings=warnings,
            error_message="；".join(errors)[:2000] if errors else None,
        )

    @staticmethod
    def _research_from_payload(
        data: dict,
        *,
        topic: str | None = None,
        from_cache: bool = True,
    ) -> ResearchResponse:
        """Validate stored research while repairing records from older runs."""
        normalized = dict(data)
        resolved_topic = str(normalized.get("topic") or topic or "短视频创作").strip()
        normalized["topic"] = resolved_topic or "短视频创作"
        return ResearchResponse.model_validate({**normalized, "from_cache": from_cache})

    async def research_task(
        self,
        task_id: str,
        *,
        force: bool = False,
    ) -> ResearchResponse:
        """Persist task research and make automatic retries idempotent."""
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundException("Task", task_id)
        payload = dict(self._task_settings(task))
        topic = str(payload.get("topic") or task.title or "短视频创作").strip() or "短视频创作"
        cached = payload.get("research")
        if isinstance(cached, dict) and not force and cached.get("status") in {
            "completed", "failed", "skipped"
        }:
            return self._research_from_payload(cached, topic=topic)

        now = datetime.now(UTC).isoformat()
        started_monotonic = time.monotonic()
        pending = {
            "topic": topic,
            "status": "pending",
            "provider": None,
            "queries": [],
            "query_records": [],
            "sources": [],
            "summary": "正在准备实时资料检索。",
            "query_source": "heuristic",
            "warnings": [],
            "error_message": None,
            "started_at": now,
            "completed_at": None,
        }
        payload["research"] = pending
        task.generation_settings = payload
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.task_repo.update(task)
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.session.commit()

        if not payload.get("enable_research", True):
            result = ResearchResponse(
                topic=topic,
                status="skipped",
                summary="任务已关闭实时资料检索。",
                error_message=None,
            )
        else:
            result = await self.research_topic(
                topic,
                max_results=int(payload.get("research_max_results", 5)),
                max_queries=int(payload.get("research_max_queries", 3)),
                search_provider_id=payload.get("search_provider_id"),
                prompt_versions=payload.get("prompt_versions"),
            )

        completed = result.model_dump()
        completed.update(
            {
                "started_at": now,
                "completed_at": datetime.now(UTC).isoformat(),
                "duration_seconds": round(time.monotonic() - started_monotonic, 3),
            }
        )
        payload["research"] = completed
        persisted_result = ResearchResponse.model_validate(
            {**completed, "from_cache": False}
        )
        if persisted_result.status == "completed" and persisted_result.sources:
            payload["research_context"] = persisted_result.format_for_prompt()
        else:
            payload.pop("research_context", None)
        task.generation_settings = payload
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.task_repo.update(task)
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.session.commit()

        return persisted_result

    async def get_task_research(self, task_id: str) -> ResearchResponse:
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundException("Task", task_id)
        payload = dict(self._task_settings(task))
        topic = str(payload.get("topic") or task.title or "短视频创作").strip() or "短视频创作"
        cached = payload.get("research")
        if isinstance(cached, dict):
            return self._research_from_payload(cached, topic=topic)
        return ResearchResponse(
            topic=topic,
            status="pending",
            summary="该任务尚未执行资料检索。",
        )

    async def generate_script(self, payload: ScriptGenerateRequest) -> StructuredScript:
        """Generate structured video storyboard script using LLM or fixed text splitting"""
        llm_provider = await self._get_llm_provider()
        if not llm_provider:
            raise ValidationException(
                "未配置大语言模型服务，请前往【设置中心】配置 OpenAI / DeepSeek / Claude / Cloudflare / Ollama 等 LLM 服务。"
            )

        # 1. Mode: Fixed (Existing script split)
        if payload.mode == "fixed" and (payload.raw_script or payload.topic):
            raw_text = payload.raw_script or payload.topic
            narrations = split_narration_script(raw_text, split_mode=payload.split_mode)
            logger.info(
                f"Splitting fixed script into {len(narrations)} narrations (mode={payload.split_mode})"
            )

            research_hint = (payload.research_context or "").strip()
            title_prompt = (
                "请为以下短视频旁白文案拟定一个清晰、有吸引力且符合平台表达的标题"
                "（30字以内，不要标点符号）。不要改写旁白。"
                f"{CONTENT_QUALITY_RULES}\n"
                + format_untrusted_prompt_data(
                    raw_text, label="user_script", max_chars=600
                )
            )
            if research_hint:
                title_prompt += "\n" + format_untrusted_prompt_data(
                    research_hint, max_chars=1200
                )
            try:
                title = await self._llm_text(
                    llm_provider,
                    "script.fixed_title",
                    title_prompt,
                    prompt_versions=payload.prompt_versions,
                    temperature=PROMPT_CALL_BUDGETS["fixed_title"]["temperature"],
                    max_tokens=PROMPT_CALL_BUDGETS["fixed_title"]["max_tokens"],
                )
                title = title.strip().strip('"').strip("'").strip("《》")
            except ProviderException:
                raise
            except ValidationException:
                raise
            except Exception:
                title = raw_text[:20]
                await self._mark_prompt_fallback(
                    getattr(self, "_last_prompt_context", None), 1
                )

            hook = narrations[0] if narrations else "精彩内容即将呈现"

            # Build style prefix
            online_asset = payload.content_mode == "online_asset"
            style_desc = (
                payload.prompt_prefix
                or IMAGE_STYLE_PRESETS.get(payload.style_preset, {}).get("description", "")
            ) if not online_asset else ""
            if online_asset:
                visual_prompts = [ONLINE_ASSET_VISUAL_PROMPT] * len(narrations)
            else:
                visual_prompts = await self._generate_fixed_visual_prompts(
                    llm_provider,
                    narrations=narrations,
                    style_desc=style_desc,
                    content_mode=payload.content_mode,
                    aspect_ratio=payload.aspect_ratio,
                    research_hint=research_hint,
                    prompt_versions=payload.prompt_versions,
                )
            scenes = [
                StructuredSceneScript(
                    sequence_index=index,
                    narration_text=narration,
                    visual_prompt=visual_prompt,
                    badge_text=f"Part {index + 1}",
                    visual_role=infer_visual_role(narration),
                )
                for index, (narration, visual_prompt) in enumerate(
                    zip(narrations, visual_prompts, strict=True)
                )
            ]

            generated_metadata = await self._generate_platform_metadata(
                llm_provider,
                title=title,
                hook=hook,
                narration=raw_text,
                topic=payload.topic or raw_text[:100],
                genre=payload.genre,
                research_hint=research_hint,
                prompt_versions=payload.prompt_versions,
            )
            script = StructuredScript(
                title=title,
                hook=hook,
                narration=raw_text,
                scenes=scenes,
                knowledge_brief=KnowledgeBrief(
                    **knowledge_brief_for_payload(payload).model_dump()
                ),
                metadata=generated_metadata or PlatformMetadata(title=title),
            )
            script = normalize_knowledge_script(script, payload=payload)
            return self._finalize_script_metadata(
                script,
                topic=payload.topic or raw_text,
                genre=payload.genre,
            )

        # 2. Mode: Generate (AI Topic Creation)
        logger.info(
            f"Generating structured script for topic: '{payload.topic}' (genre: {payload.genre}, style: {payload.style_preset})"
        )

        genre_hint = get_genre_instruction(payload.genre, fallback="science_tech")
        hook_hint = HOOK_INSTRUCTIONS.get(
            payload.hook_type or "auto", HOOK_INSTRUCTIONS["bold_claim"]
        )
        preset_style_desc = IMAGE_STYLE_PRESETS.get(payload.style_preset, {}).get(
            "description", ""
        )
        style_desc = payload.prompt_prefix or preset_style_desc
        online_asset = payload.content_mode == "online_asset"
        if online_asset:
            visual_section = (
                "【在线素材字段要求】\n"
                f"online_asset 模式的 visual_prompt 只填写固定兼容占位 `{ONLINE_ASSET_VISUAL_PROMPT}`，"
                "该字段仅供历史结构读取，素材检索从分镜旁白和脚本上下文获取依据。\n\n"
            )
            scene_visual_field = (
                f"visual_prompt 使用固定兼容值 `{ONLINE_ASSET_VISUAL_PROMPT}`（仅用于兼容历史字段）"
            )
        else:
            visual_rules = build_visual_prompt_rules(
                video=payload.content_mode == "generated_video",
                aspect_ratio=payload.aspect_ratio,
                source=payload.topic,
            )
            visual_section = (
                "【视觉风格要求】\n每个分镜的 visual_prompt 必须遵循指定视觉风格。"
                f"{('默认预设：' + preset_style_desc) if not payload.prompt_prefix else ''}\n"
                f"{visual_rules}\n\n"
            )
            scene_visual_field = "中文画面提示词 (visual_prompt)"

        system_prompt = (
            "你是一名资深的短视频编剧与视觉导演。\n"
            "你需要根据用户提供的主题、Knowledge Brief、赛道指引与调研素材，创作一条表达清晰、节奏自然、画面明确的知识视频结构化分镜脚本。\n\n"
            f"【内容质量】\n{CONTENT_QUALITY_RULES}\n\n"
            f"【题材赛道要求】\n{genre_hint}\n\n"
            f"【黄金3秒钩子要求】\n{hook_hint}\n\n"
            "【知识表达要求】\n"
            "先明确 audience、thesis、viewer_takeaway，再拆出 key_claims。每个 key_claims 项必须有稳定 id、statement 和 source_refs；"
            "source_refs 只能使用调研资料中给出的 source ref_id，无法核验的主张保持空引用并在表达中说明不确定性。"
            "每个 scene 必须选择一个 visual_role，并用 claim_refs/source_refs 表明它解释或使用的关系；不要只生成与旁白相关的漂亮图片。\n"
            "visual_role 只能是 concept、process、comparison、timeline、data、example、quote、b_roll；"
            "concept 解释定义，process 表达步骤，comparison 表达差异，timeline 表达时间顺序，data 承载已有数据，example 落地案例，quote 保留引用关系，b_roll 仅作不承载新事实的补充画面。\n\n"
            + visual_section
            +
            "【输出字段要求】\n"
            "1. title: 清晰、有吸引力且符合平台表达的标题（<= 30 字，末尾无标点）；\n"
            "2. hook: 第一分镜黄金 3 秒抓人文案；\n"
            "3. narration: 完整的口播旁白总览；\n"
            "4. knowledge_brief: audience、thesis、viewer_takeaway、key_claims、source_refs；\n"
            f"5. scenes: 包含分镜序号、精练口语化旁白 (narration_text)、{scene_visual_field}、角标 (badge_text)、visual_role、claim_refs、source_refs、production_metadata；\n"
            "6. metadata: 抖音发布元数据；title 必须与视频 title 一致，description 用与主题相同的语言写 1-3 句发布文案，"
            "只能重组脚本已有事实；概括核心价值，评论邀请可选。"
            f"{PLATFORM_TAG_RULES}\n"
            "declaration 从‘内容由AI生成’、‘内容取材网络’、‘个人观点，仅供参考’中选择合适的一项；"
            "visibility 只能填写枚举值 public、friend 或 private，不得填写中文或其他同义词；"
            "allow_download 必须是 true 或 false。knowledge_brief 必须是对象或 null，"
            "其中 audience、thesis、viewer_takeaway 必须是字符串，key_claims 必须是数组。"
        )

        user_prompt = (
            format_untrusted_prompt_data(payload.topic, label="user_topic", max_chars=700)
            + f"\n期望分镜数量: {payload.target_scene_count} 个分镜\n"
        )

        if payload.research_context:
            user_prompt += "\n" + format_untrusted_prompt_data(payload.research_context) + "\n"
        if payload.research_sources:
            source_index = [
                {
                    "ref_id": source.ref_id,
                    "title": source.title,
                    "url": source.url,
                }
                for source in payload.research_sources
            ]
            user_prompt += "\n可用来源 ref_id（只能从中选择）：\n" + format_untrusted_prompt_data(
                json.dumps(source_index, ensure_ascii=False),
                label="source_index",
                max_chars=3000,
            ) + "\n"
        brief = format_knowledge_brief(payload)
        if brief:
            user_prompt += "\n" + brief + "\n"
        if payload.prompt_prefix and not online_asset:
            user_prompt += "\n" + format_untrusted_prompt_data(
                payload.prompt_prefix, label="user_visual_style", max_chars=1000
            ) + "\n"
        if payload.language:
            user_prompt += "\n" + format_untrusted_prompt_data(
                payload.language, label="output_language", max_chars=300
            ) + "\n"

        user_prompt += "\n请严格按照 StructuredScript JSON 格式生成结构化分镜脚本。"

        try:
            script = await self._llm_structured(
                llm_provider,
                "script.structured",
                user_prompt,
                StructuredScript,
                prompt_versions=payload.prompt_versions,
                system_prompt=system_prompt,
                temperature=PROMPT_CALL_BUDGETS["script_structured"]["temperature"],
                max_tokens=PROMPT_CALL_BUDGETS["script_structured"]["max_tokens"],
            )
        except ProviderException:
            raise
        except ValidationException:
            raise
        except StructuredOutputException as e:
            await self._mark_prompt_fallback(
                getattr(self, "_last_prompt_context", None), 1
            )
            logger.warning(
                "Structured script generation failed schema validation: "
                f"{redact_sensitive_text(str(e))}. Attempting smart text parsing fallback..."
            )
            try:
                fallback_visual = (
                    f"画面：{ONLINE_ASSET_VISUAL_PROMPT}"
                    if online_asset
                    else "画面：<中文画面提示词>"
                )
                text_prompt = (
                    f"{user_prompt}\n\n"
                    "请按以下格式输出短视频分镜脚本：\n"
                    f"必须输出恰好 {payload.target_scene_count} 个分镜，编号从 1 到 {payload.target_scene_count}；"
                    "下面仅展示格式示例，不是数量限制。\n"
                    "标题：<视频标题>\n"
                    "钩子：<黄金3秒文案>\n"
                    f"分镜 1：\n旁白：<台词>\n{fallback_visual}\n"
                    f"分镜 2：\n旁白：<台词>\n{fallback_visual}\n"
                )
                raw_text = await self._llm_text(
                    llm_provider,
                    "script.text_fallback",
                    text_prompt,
                    prompt_versions=payload.prompt_versions,
                    system_prompt=system_prompt,
                    temperature=PROMPT_CALL_BUDGETS["script_format_fallback"]["temperature"],
                    max_tokens=PROMPT_CALL_BUDGETS["script_format_fallback"]["max_tokens"],
                )
                script = parse_script_from_text(raw_text, default_topic=payload.topic, style_desc=style_desc)
            except Exception as inner_e:
                logger.error(f"Text fallback generation also failed: {redact_sensitive_text(str(inner_e))}")
                raise

        if (
            "target_scene_count" in payload.model_fields_set
            and len(script.scenes) != payload.target_scene_count
        ):
            raise ValidationException(
                f"分镜数量不符合请求：期望 {payload.target_scene_count} 个分镜，实际 {len(script.scenes)} 个。"
            )

        script = normalize_knowledge_script(script, payload=payload)

        # Repair missing/title-derived tags once, without replacing valid metadata.
        valid_tags = self._filter_platform_tags(script.metadata.tags, script.title)
        if not valid_tags or valid_tags != script.metadata.tags:
            regenerated = await self._generate_platform_metadata(
                llm_provider,
                title=script.title,
                hook=script.hook,
                narration=script.narration or "\n".join(sc.narration_text for sc in script.scenes),
                topic=payload.topic,
                genre=payload.genre,
                research_hint=payload.research_context or "",
                prompt_versions=payload.prompt_versions,
            )
            repaired_tags = self._filter_platform_tags(regenerated.tags, script.title) if regenerated else []
            script.metadata.tags = repaired_tags or valid_tags
            if regenerated and not script.metadata.description:
                script.metadata.description = regenerated.description

        # Post-process visual prompts with style prefix if not already present
        if style_desc and not online_asset:
            for sc in script.scenes:
                if style_desc not in sc.visual_prompt:
                    sc.visual_prompt = f"{style_desc}, {sc.visual_prompt}"

        if online_asset:
            for sc in script.scenes:
                sc.visual_prompt = ONLINE_ASSET_VISUAL_PROMPT

        return self._finalize_script_metadata(
            script,
            topic=payload.topic,
            genre=payload.genre,
        )

    async def regenerate_task_metadata(self, task_id: str) -> PlatformMetadata:
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundException("Task", task_id)
        active = await self.session.scalar(select(WorkflowJobModel.id).where(
            WorkflowJobModel.task_id == task_id,
            WorkflowJobModel.job_type != "publish",
            WorkflowJobModel.status.in_(["queued", "running", "retrying", "pending"]),
        ).limit(1))
        if active:
            raise ValidationException("请等待视频生成完成后再重新生成发布信息。")
        scenes = await self.scene_repo.list_by_task_id(task_id)
        narration = "\n".join(scene.narration_text for scene in scenes if scene.narration_text.strip())
        narration = narration or self._task_settings(task).get("narration") or ""
        if not narration.strip():
            raise ValidationException("请先保存视频旁白，再重新生成发布信息。")
        provider = await self._get_llm_provider()
        if not provider:
            raise ValidationException("请先配置大语言模型服务。")
        prompt_versions = self._task_settings(task).get("prompt_versions")
        prompt = (
            "根据视频旁白重新生成平台发布信息，保留旁白事实，不生成新分镜。只输出 JSON："
            '{"title":"30字以内的新标题","description":"1-3句发布描述","tags":["话题"]}。\n'
            f"{CONTENT_QUALITY_RULES}{PLATFORM_TAG_RULES}\n"
            "元数据只能重组脚本已有事实，评论邀请可选。\n"
            + format_untrusted_prompt_data(
                f"原标题：{task.title}\n完整旁白：{narration}",
                label="script_content",
                max_chars=6500,
            )
        )
        raw = await self._llm_text(
            provider,
            "metadata.regenerate",
            prompt,
            prompt_versions=prompt_versions,
            temperature=PROMPT_CALL_BUDGETS["metadata_regenerate"]["temperature"],
            max_tokens=PROMPT_CALL_BUDGETS["metadata_regenerate"]["max_tokens"],
        )
        metadata = self._parse_platform_metadata_response(raw)
        metadata.tags = self._filter_platform_tags(metadata.tags, metadata.title)[:5]
        if not metadata.title or not metadata.description or not metadata.tags:
            raise ValidationException("模型未返回完整有效的标题、描述和话题，原发布信息已保留。")
        previous = dict(self._task_settings(task).get("metadata") or {})
        merged = PlatformMetadata.model_validate({
            **previous, "title": metadata.title, "description": metadata.description, "tags": metadata.tags,
        })
        task.title = merged.title
        task.description = merged.description
        task.generation_settings = {**(task.generation_settings or {}), "metadata": merged.model_dump()}
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.session.commit()
        return merged

    async def apply_script_to_task(self, task_id: str, script: StructuredScript) -> TaskModel:
        """Apply generated structured script directly to a Task's scenes"""
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundException("Task", task_id)

        # Update task title and payload
        task.title = script.title
        task.description = script.hook
        metadata_payload = script.metadata.model_dump()
        if self._task_settings(task).get("content_mode") == "online_asset":
            metadata_payload["declaration"] = "内容取材网络"
        script_payload = {
            "hook": script.hook,
            "narration": script.narration,
            "metadata": metadata_payload,
        }
        if task.project.mode == ProductionMode.KNOWLEDGE.value:
            script_payload["knowledge_brief"] = (
                script.knowledge_brief or KnowledgeBrief()
            ).model_dump()
        task.generation_settings = {
            **(task.generation_settings or {}),
            **script_payload,
        }
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.task_repo.update(task)

        # Convert to SceneCreate DTOs
        scenes_data = [
            SceneCreate(
                sequence_index=sc.sequence_index if sc.sequence_index is not None else i,
                narration_text=sc.narration_text,
                visual_prompt=sc.visual_prompt,
                layout_params={
                    **({"badge_text": sc.badge_text} if sc.badge_text else {}),
                },
                visual_role=sc.visual_role,
                claim_refs=list(sc.claim_refs),
                source_refs=list(sc.source_refs),
                production_metadata=(
                    dict(sc.production_metadata)
                    if sc.production_metadata
                    else (
                        {
                            "knowledge": {
                                "visual_role": sc.visual_role.value,
                                "claim_refs": list(sc.claim_refs),
                                "source_refs": list(sc.source_refs),
                            }
                        }
                        if task.project.mode == ProductionMode.KNOWLEDGE.value
                        else {}
                    )
                ),
            )
            for i, sc in enumerate(script.scenes)
        ]

        await self.scene_service.replace_task_scenes(task_id, scenes_data)
        return await self.task_repo.get_with_scenes(task_id)  # type: ignore

    async def generate_scene_audio(
        self, scene_id: str, voice_id: str | None = None, speed: float | None = None
    ) -> SceneModel:
        """Synthesize TTS audio for a scene, save as Asset, and bind to Scene"""
        scene = await self.scene_repo.get_by_id(scene_id)
        if not scene:
            raise NotFoundException("Scene", scene_id)

        if not scene.narration_text.strip():
            raise ValidationException("该分镜没有旁白台词，无法生成配音。")

        await self._set_scene_generation_status(scene, "tts", "generating")

        # Get parent project / task payload for default voice
        task = await self.task_repo.get_by_id(scene.task_id)
        target_voice = voice_id
        if not target_voice and task:
            target_voice = self._task_settings(task).get("voice_id")
        target_voice = target_voice or await self.provider_manager.get_default_tts_voice()

        target_speed = speed or self._task_settings(task).get("speed") or 1.0

        try:
            tts_provider = await self._get_tts_provider()
        except Exception as exc:
            await self._set_scene_generation_status(scene, "tts", "failed", str(exc))
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise

        try:
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            tts_result = await tts_provider.synthesize(
                scene.narration_text, voice_id=target_voice, speed=float(target_speed)
            )
        except Exception as exc:
            await self._set_scene_generation_status(scene, "tts", "failed", str(exc))
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise

        if not tts_result.audio_bytes:
            message = "TTS Provider 返回空音频"
            await self._set_scene_generation_status(scene, "tts", "failed", message)
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise ValidationException(message)

        # Save audio file to storage & asset database
        file_name = f"tts_{scene.id}_{uuid.uuid4().hex[:6]}.{tts_result.format}"
        declared_duration = float(tts_result.duration_seconds or 0.0)
        try:
            asset = await self.asset_service.save_asset(
                content=tts_result.audio_bytes,
                file_name=file_name,
                mime_type=tts_result.mime_type,
                asset_type=AssetType.AUDIO,
                project_id=task.project_id if task else None,
                duration_seconds=declared_duration or None,
                metadata={
                    "voice_id": target_voice,
                    "speed": target_speed,
                    "scene_id": scene.id,
                    "provider": getattr(tts_provider, "name", "unknown"),
                    "declared_duration_seconds": declared_duration or None,
                    "duration_source": "provider_declared",
                },
            )
        except Exception as exc:
            await self._set_scene_generation_status(scene, "tts", "failed", str(exc))
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise

        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.session.commit()
        try:
            audio_probe = await media_probe_service.probe(self.storage.get_path(asset.file_path))
            if not audio_probe.has_audio or not audio_probe.audio_duration:
                raise ValidationException("TTS 文件没有可用的音频流或真实时长。")
            actual_duration = audio_probe.audio_duration
        except Exception as exc:
            await self.asset_service.delete_asset(asset.id)
            await self._set_scene_generation_status(scene, "tts", "failed", str(exc))
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise ValidationException(f"TTS 音频探测失败，未使用伪造时长: {exc}") from exc

        # Update scene
        scene.audio_asset_id = asset.id
        scene.duration_seconds = actual_duration
        asset.duration_seconds = actual_duration
        asset.metadata_json = {
            **(asset.metadata_json or {}),
            "actual_duration_seconds": actual_duration,
            "duration_source": "tts_probe",
        }
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.asset_service.asset_repo.update(asset)
        scene.layout_params = {
            **(scene.layout_params or {}),
            "tts_provider": getattr(tts_provider, "name", "unknown"),
            "tts_declared_duration_seconds": declared_duration or None,
            "tts_actual_duration_seconds": actual_duration,
            "actual_duration_seconds": actual_duration,
            "duration_source": "tts_probe",
        }
        await self._set_scene_generation_status(scene, "tts", "completed")
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.scene_repo.update(scene)
        return scene

    @staticmethod
    def _provider_accepts(
        provider,
        parameter: str,
        method: str = "generate_image",
        *,
        strict: bool = False,
    ) -> bool:
        """Detect optional capability without treating ``**kwargs`` as proof.

        Legacy providers can still receive non-semantic optional context via
        ``**kwargs``. Explicit reference-frame inputs use ``strict=True`` so a
        provider must declare and implement the capability visibly.
        """
        try:
            signature = inspect.signature(getattr(provider, method))
        except (AttributeError, TypeError, ValueError):
            return False
        return parameter in signature.parameters or (
            not strict
            and any(item.kind == inspect.Parameter.VAR_KEYWORD for item in signature.parameters.values())
        )

    async def generate_scene_image(
        self,
        scene_id: str,
        prompt_override: str | None = None,
        *,
        reference_image_path: str | None = None,
        reference_image_paths: list[str] | None = None,
        continuity_input: dict | None = None,
    ) -> SceneModel:
        """Generate a real visual image for a scene and bind it to the scene."""
        scene = await self.scene_repo.get_by_id(scene_id)
        if not scene:
            raise NotFoundException("Scene", scene_id)

        prompt = prompt_override or scene.visual_prompt or scene.narration_text
        if not prompt.strip():
            prompt = _visual_prompt_fallback(scene.narration_text)

        await self._set_scene_generation_status(scene, "image", "generating")

        # Get aspect ratio from project
        aspect_ratio = "9:16"
        task = await self.task_repo.get_by_id(scene.task_id)
        workflow_target = None
        if task:
            project = await self.project_repo.get_by_id(task.project_id)
            if project:
                aspect_ratio = project.aspect_ratio
            workflow_snapshot = self._task_settings(task).get("image_workflow_snapshot") or {}
            workflow_target = workflow_snapshot.get("path") or self._task_settings(task).get(
                "image_workflow_id"
            )

        aspect_ratio, media_width, media_height = self._resolve_template_media(task, aspect_ratio)

        image_provider = await self._get_image_provider()
        if not image_provider:
            await self._set_scene_generation_status(scene, "image", "failed", "未配置可用的图片 Provider")
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise ValidationException("未配置可用的图片 Provider，无法生成真实分镜画面。")
        reference_paths = [item for item in (reference_image_paths or []) if item]
        if reference_image_path and reference_image_path not in reference_paths:
            reference_paths.insert(0, reference_image_path)
        accepts_multiple_references = self._provider_accepts(
            image_provider, "reference_image_paths", "generate_image", strict=True
        )
        if len(reference_paths) > 1 and not accepts_multiple_references:
            message = "当前图片 Provider 不支持多参考图输入；不能只取第一张并静默丢弃角色或场景约束。"
            await self._set_scene_generation_status(scene, "image", "failed", message)
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise ValidationException(message)
        if reference_paths and not accepts_multiple_references and not self._provider_accepts(
            image_provider, "reference_image_path", "generate_image", strict=True
        ):
            message = (
                "当前图片 Provider 不支持参考图输入；请配置支持 img2img 的工作流，"
                "不能静默退化为文生图。"
            )
            await self._set_scene_generation_status(scene, "image", "failed", message)
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise ValidationException(message)
        img_bytes = None
        width, height = media_width, media_height
        fmt = "png"
        mime = "image/png"

        # Release the SQLite write lock before waiting on an external provider.
        # Heartbeats and queue polling use independent database sessions.
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.session.commit()

        try:
            img_result = await image_provider.generate_image(
                prompt,
                **{
                    "aspect_ratio": aspect_ratio,
                    "workflow": workflow_target,
                    "width": media_width,
                    "height": media_height,
                    **(
                        {"reference_image_paths": reference_paths}
                        if reference_paths and accepts_multiple_references
                        else {"reference_image_path": reference_paths[0]}
                        if reference_paths and self._provider_accepts(image_provider, "reference_image_path", "generate_image", strict=True)
                        else {}
                    ),
                    **(
                        {"continuity_input": continuity_input}
                        if continuity_input and self._provider_accepts(image_provider, "continuity_input", "generate_image")
                        else {}
                    ),
                },
            )
            img_bytes = img_result.image_bytes
            width = img_result.width
            height = img_result.height
            fmt = img_result.format
            mime = img_result.mime_type
        except Exception as e:
            logger.error(f"Image generation failed for scene {scene_id}: {e}")
            await self._set_scene_generation_status(scene, "image", "failed", str(e))
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise ValidationException(f"分镜图片生成失败: {e}") from e

        if not img_bytes:
            message = "图片 Provider 返回空文件"
            await self._set_scene_generation_status(scene, "image", "failed", message)
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise ValidationException(message)

        file_name = f"img_{scene.id}_{uuid.uuid4().hex[:6]}.{fmt}"
        try:
            asset = await self.asset_service.save_asset(
                content=img_bytes,
                file_name=file_name,
                mime_type=mime,
                asset_type=AssetType.IMAGE,
                project_id=task.project_id if task else None,
                width=width,
                height=height,
                metadata={
                    "prompt": prompt,
                    "scene_id": scene.id,
                    "provider": getattr(image_provider, "name", "unknown"),
                    "reference_strategy": (
                        "provider_reference"
                        if reference_paths
                        else "deterministic_prompt_anchor"
                    ),
                    "reference_image_paths": reference_paths,
                    "continuity_input": continuity_input or {},
                },
            )
        except Exception as exc:
            await self._set_scene_generation_status(scene, "image", "failed", str(exc))
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise

        scene.media_asset_id = asset.id
        scene.layout_params = {
            **(scene.layout_params or {}),
            "media_type": "image",
            "media_source": "generated",
            "generated_content_mode": "generated_image",
            "image_provider": getattr(image_provider, "name", "unknown"),
        }
        await self._set_scene_generation_status(scene, "image", "completed")
        if self.execution_context:
            await self.execution_context.fence(self.session)
        await self.scene_repo.update(scene)
        return scene

    async def generate_scene_video(
        self,
        scene_id: str,
        prompt_override: str | None = None,
        *,
        continuity_input: dict | None = None,
    ) -> SceneModel:
        """Generate video clip for a scene, save as Asset, and bind to Scene"""
        scene = await self.scene_repo.get_by_id(scene_id)
        if not scene:
            raise NotFoundException("Scene", scene_id)

        prompt = prompt_override or scene.visual_prompt or scene.narration_text
        if not prompt.strip():
            raise ValidationException("分镜缺少视频生成提示词。")

        await self._set_scene_generation_status(scene, "video", "generating")

        video_provider = await self._get_video_provider()
        if not video_provider:
            await self._set_scene_generation_status(scene, "video", "failed", "未配置可用的视频 Provider")
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise ValidationException("未配置可用的视频 Provider，无法生成动态分镜画面。")

        aspect_ratio = "9:16"
        task = await self.task_repo.get_by_id(scene.task_id)
        workflow_target = None
        if task:
            project = await self.project_repo.get_by_id(task.project_id)
            if project:
                aspect_ratio = project.aspect_ratio
            workflow_snapshot = self._task_settings(task).get("video_workflow_snapshot") or {}
            workflow_target = workflow_snapshot.get("path") or self._task_settings(task).get(
                "video_workflow_id"
            )

        aspect_ratio, media_width, media_height = self._resolve_template_media(task, aspect_ratio)
        first_frame_path = None
        if scene.media_asset_id:
            source_asset = await self.asset_service.asset_repo.get_by_id(scene.media_asset_id)
            if source_asset and source_asset.mime_type.startswith("image/"):
                first_frame_path = str(self.storage.get_path(source_asset.file_path))

        last_frame_path = (continuity_input or {}).get("last_frame_path")
        reference_image_paths = [
            item for item in ((continuity_input or {}).get("reference_image_paths") or []) if item
        ]
        accepts_video_references = self._provider_accepts(
            video_provider, "reference_image_urls", "generate_video", strict=True
        )
        if reference_image_paths and not accepts_video_references and not first_frame_path:
            if self._provider_accepts(video_provider, "image_url", "generate_video", strict=True):
                first_frame_path = reference_image_paths[0]
                reference_image_paths = []
            else:
                message = "当前视频 Provider 不支持短剧参考图输入；不能静默退化为纯文生视频。"
                await self._set_scene_generation_status(scene, "video", "failed", message)
                if self.execution_context:
                    await self.execution_context.fence(self.session)
                await self.session.commit()
                raise ValidationException(message)
        if first_frame_path and not self._provider_accepts(video_provider, "image_url", "generate_video", strict=True):
            message = (
                "当前视频 Provider 不支持首帧参考图输入；请配置 image-to-video 工作流，"
                "不能静默退化为文生视频。"
            )
            await self._set_scene_generation_status(scene, "video", "failed", message)
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise ValidationException(message)
        if (
            last_frame_path
            and not first_frame_path
            and not self._provider_accepts(video_provider, "last_frame_url", "generate_video", strict=True)
            and not self._provider_accepts(video_provider, "image_url", "generate_video", strict=True)
        ):
            message = (
                "当前视频 Provider 不支持连续性参考帧输入；请配置支持首帧或末帧的工作流。"
            )
            await self._set_scene_generation_status(scene, "video", "failed", message)
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise ValidationException(message)

        try:
            requested_duration = float(scene.duration_seconds or 4.0)
            video_kwargs = {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "duration_seconds": requested_duration,
                "workflow": workflow_target,
                "width": media_width,
                "height": media_height,
            }
            if first_frame_path:
                video_kwargs["image_url"] = first_frame_path
            if last_frame_path and self._provider_accepts(video_provider, "last_frame_url", "generate_video", strict=True):
                video_kwargs["last_frame_url"] = last_frame_path
            elif last_frame_path and not first_frame_path and self._provider_accepts(video_provider, "image_url", "generate_video", strict=True):
                # Existing video Providers expose first-frame input as
                # image_url. Use it as a generic continuity hand-off when a
                # dedicated last-frame parameter is unavailable.
                video_kwargs["image_url"] = last_frame_path
            if reference_image_paths and accepts_video_references:
                video_kwargs["reference_image_urls"] = reference_image_paths
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            vid_result = await video_provider.generate_video(**video_kwargs)

            if not vid_result.video_bytes:
                raise ValidationException("视频 Provider 返回空文件")

            file_name = f"vid_{scene.id}_{uuid.uuid4().hex[:6]}.{vid_result.format}"
            asset = await self.asset_service.save_asset(
                content=vid_result.video_bytes,
                file_name=file_name,
                mime_type=vid_result.mime_type,
                asset_type=AssetType.VIDEO,
                project_id=task.project_id if task else None,
                duration_seconds=float(vid_result.duration_seconds or 0.0) or None,
                width=vid_result.width,
                height=vid_result.height,
                metadata={
                    "prompt": prompt,
                    "scene_id": scene.id,
                    "provider": getattr(video_provider, "name", "unknown"),
                    "continuity_strategy": (
                        "provider_last_frame"
                        if last_frame_path and self._provider_accepts(video_provider, "last_frame_url", "generate_video", strict=True)
                        else "provider_first_frame"
                        if first_frame_path or last_frame_path
                        else "deterministic_prompt_anchor"
                    ),
                    "continuity_input": continuity_input or {},
                    "declared_duration_seconds": vid_result.duration_seconds,
                    "duration_source": "provider_declared",
                },
            )

            try:
                video_probe = await media_probe_service.probe(self.storage.get_path(asset.file_path))
                if not video_probe.has_video or not video_probe.video_duration:
                    raise ValidationException("视频文件没有可用的视频流或真实时长。")
            except Exception as exc:
                await self.asset_service.delete_asset(asset.id)
                raise ValidationException(f"视频素材探测失败: {exc}") from exc
            actual_video_duration = video_probe.video_duration
            asset.duration_seconds = actual_video_duration
            asset.width = video_probe.width or asset.width
            asset.height = video_probe.height or asset.height
            asset.metadata_json = {
                **(asset.metadata_json or {}),
                "actual_duration_seconds": actual_video_duration,
                "duration_source": "ffprobe",
            }
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.asset_service.asset_repo.update(asset)

            scene.media_asset_id = asset.id
            # Keep the generated source available until the composition stage
            # replaces it with the subtitle/audio-aware scene clip.
            scene.rendered_segment_asset_id = asset.id
            scene.layout_params = {
                **(scene.layout_params or {}),
                "media_type": "video",
                "media_source": "generated",
                "generated_content_mode": "generated_video",
                "video_provider": getattr(video_provider, "name", "unknown"),
                "video_declared_duration_seconds": vid_result.duration_seconds,
                "video_actual_duration_seconds": actual_video_duration,
                "video_duration_source": "ffprobe",
            }
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.scene_repo.update(scene)
            return scene
        except Exception as e:
            logger.error(f"Video generation failed for scene {scene_id}: {e}")
            await self._set_scene_generation_status(scene, "video", "failed", str(e))
            if self.execution_context:
                await self.execution_context.fence(self.session)
            await self.session.commit()
            raise ValidationException(f"分镜视频生成失败: {e}") from e
