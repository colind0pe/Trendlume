"""Versioned prompt contracts used by production LLM calls.

The registry deliberately stores the stable contract/rules text rather than a
hand-written version hash.  ``template_hash`` is calculated from that text on
every access, so changing a contract changes the durable selection snapshot.
Business data is still supplied by the generation service at call time.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from src.core.exceptions import ValidationException


class PromptVersionError(ValidationException):
    """An explicit prompt selection cannot be resolved safely."""

    def __init__(self, message: str):
        super().__init__(f"提示词版本选择无效：{message}")


@dataclass
class PromptSpec:
    prompt_id: str
    version: str
    template: str
    status: str = "stable"

    @property
    def template_hash(self) -> str:
        return hashlib.sha256(self.template.encode("utf-8")).hexdigest()

    def snapshot(self) -> dict[str, str]:
        return {
            "prompt_id": self.prompt_id,
            "prompt_version": self.version,
            "template_hash": self.template_hash,
        }


# These contracts are intentionally compact.  They contain the rules that
# define each production prompt path; request-specific content is appended by
# GenerationService and is never persisted in the registry snapshot.
_SPECS = (
    PromptSpec(
        "research.query_plan",
        "v1",
        "research query planner | complementary searchable angles | JSON queries | no URL or explanation",
    ),
    PromptSpec(
        "script.structured",
        "v1",
        "knowledge production storyboard | audience thesis viewer takeaway | source-grounded claims | visual roles | bounded scenes | metadata contract | visual mode rules",
    ),
    PromptSpec(
        "script.structured",
        "v2-candidate",
        "knowledge storyboard candidate | audience value | source-grounded hook and claims | explicit uncertainty | visual roles | bounded scenes | metadata contract | visual mode rules",
        status="candidate",
    ),
    PromptSpec(
        "script.text_fallback",
        "v1",
        "knowledge storyboard text fallback | thesis and viewer takeaway | title hook narration visual roles | parseable labelled sections",
    ),
    PromptSpec(
        "script.fixed_title",
        "v1",
        "fixed script title | preserve source wording | thirty characters | no terminal punctuation",
    ),
    PromptSpec(
        "content.title",
        "v1",
        "standalone short-video title | thirty characters | no explanation | source-faithful",
    ),
    PromptSpec(
        "content.title",
        "v2-candidate",
        "standalone title candidate | thirty characters | concrete audience value | no unsupported claim",
        status="candidate",
    ),
    PromptSpec(
        "content.narration",
        "v1",
        "spoken narration | requested scene count | natural language | source-grounded | one line per scene",
    ),
    PromptSpec(
        "visual.image",
        "v1",
        "图片画面提示词生成 | 只用中文 | 严格遵守画幅比例 | 主体与状态、环境、构图机位、光线材质、风格 | 单一主视觉 | 禁止文字标志水印 | 仅使用来源支持的信息",
    ),
    PromptSpec(
        "visual.video",
        "v1",
        "视频画面提示词生成 | 只用中文 | 严格遵守画幅比例 | 主体、连续动作、镜头运动、起止状态、节奏、光线变化 | 保持时序一致 | 禁止文字标志水印 | 仅使用来源支持的信息",
    ),
    PromptSpec(
        "visual.fixed_batch",
        "v1",
        "knowledge fixed-script visual planning | visual role follows information logic | 只用中文 | 一条旁白对应一项 | 索引从 0 连续递增 | 每条描述可见且可执行的单镜头画面 | 保持风格和画幅约束",
    ),
    PromptSpec(
        "metadata.platform",
        "v1",
        "platform metadata | facts only from script | one to three sentence description | three to five tags",
    ),
    PromptSpec(
        "metadata.regenerate",
        "v1",
        "metadata regeneration | preserve narration facts | JSON title description tags | no new scenes",
    ),
    PromptSpec(
        "structured.json_contract",
        "v1",
        "structured JSON contract | schema entity not schema definition | local parse and one repair pass",
    ),
)


class PromptRegistry:
    """Resolve stable/candidate prompt versions without rewriting history."""

    def __init__(self, specs: tuple[PromptSpec, ...] = _SPECS):
        self._specs = {(spec.prompt_id, spec.version): spec for spec in specs}
        self._stable_versions: dict[str, str] = {}
        for spec in specs:
            if spec.status == "stable" and spec.prompt_id not in self._stable_versions:
                self._stable_versions[spec.prompt_id] = spec.version
        self._active_versions = dict(self._stable_versions)

    @property
    def prompt_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._stable_versions))

    def versions(self, prompt_id: str) -> tuple[str, ...]:
        if prompt_id not in self._stable_versions:
            raise PromptVersionError(f"未知 prompt_id：{prompt_id}")
        return tuple(sorted(version for item_id, version in self._specs if item_id == prompt_id))

    def resolve(
        self,
        prompt_id: str,
        selected_versions: Mapping[str, object] | None = None,
        *,
        requested_version: str | None = None,
    ) -> PromptSpec:
        if prompt_id not in self._stable_versions:
            raise PromptVersionError(f"未知 prompt_id：{prompt_id}")
        selected = dict(selected_versions or {})
        value = requested_version
        if value is None and prompt_id in selected:
            raw_value = selected[prompt_id]
            if isinstance(raw_value, Mapping):
                value = raw_value.get("prompt_version") or raw_value.get("version")
            else:
                value = raw_value
        version = str(value or self._active_versions[prompt_id])
        spec = self._specs.get((prompt_id, version))
        if spec is None:
            available = ", ".join(self.versions(prompt_id))
            raise PromptVersionError(
                f"{prompt_id} 不支持版本 {version!r}，可选版本：{available}"
            )
        return spec

    def validate_selection(self, selected_versions: Mapping[str, object] | None) -> None:
        for prompt_id in dict(selected_versions or {}):
            self.resolve(prompt_id, selected_versions)

    def snapshot(self, selected_versions: Mapping[str, object] | None = None) -> dict[str, dict[str, str]]:
        selected = dict(selected_versions or {})
        self.validate_selection(selected)
        return {
            prompt_id: self.resolve(prompt_id, selected).snapshot()
            for prompt_id in self.prompt_ids
        }

    def version_map(self, selected_versions: Mapping[str, object] | None = None) -> dict[str, str]:
        return {
            prompt_id: value["prompt_version"]
            for prompt_id, value in self.snapshot(selected_versions).items()
        }

    def set_active_version(self, prompt_id: str, version: str) -> PromptSpec:
        spec = self.resolve(prompt_id, requested_version=version)
        self._active_versions[prompt_id] = spec.version
        return spec

    def rollback(self, prompt_id: str) -> PromptSpec:
        return self.set_active_version(prompt_id, self._stable_versions[prompt_id])

    def active_version(self, prompt_id: str) -> str:
        return self.resolve(prompt_id).version


prompt_registry = PromptRegistry()


def prompt_selection_snapshot(selected_versions: Mapping[str, object] | None = None) -> dict[str, dict[str, str]]:
    """Return a safe, durable selection containing version and template hash."""

    return prompt_registry.snapshot(selected_versions)


def prompt_version_map(selected_versions: Mapping[str, object] | None = None) -> dict[str, str]:
    return prompt_registry.version_map(selected_versions)
