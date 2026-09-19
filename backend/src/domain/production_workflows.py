from __future__ import annotations

from dataclasses import dataclass

from src.domain.enums import ProductionMode


@dataclass(frozen=True, slots=True)
class ProductionStage:
    """One ordered stage in a production workflow."""

    key: str
    label: str
    supports_units: bool = False


@dataclass(frozen=True, slots=True)
class ProductionWorkflow:
    """The durable stage contract shared by a production pipeline and its UI."""

    mode: ProductionMode
    stages: tuple[ProductionStage, ...]

    @property
    def stage_keys(self) -> tuple[str, ...]:
        return tuple(stage.key for stage in self.stages)

    @property
    def unit_stage_keys(self) -> frozenset[str]:
        return frozenset(stage.key for stage in self.stages if stage.supports_units)

    def has_stage(self, key: str) -> bool:
        return key in self.stage_keys

    def stage_label(self, key: str) -> str:
        return next(stage.label for stage in self.stages if stage.key == key)

    def progress_for(self, key: str, *, running: bool) -> int:
        """Return a compatible coarse progress value for a stage update."""
        index = self.stage_keys.index(key)
        slot = max(1, 100 // len(self.stages))
        offset = 1 if running else max(1, min(9, slot - 1))
        return min(99, index * slot + offset)


KNOWLEDGE_PRODUCTION_WORKFLOW = ProductionWorkflow(
    mode=ProductionMode.KNOWLEDGE,
    stages=(
        ProductionStage("topic", "主题"),
        ProductionStage("research", "研究"),
        ProductionStage("planning", "策划"),
        ProductionStage("script", "脚本"),
        ProductionStage("storyboard", "分镜"),
        ProductionStage("assets", "素材", supports_units=True),
        ProductionStage("voice", "配音", supports_units=True),
        ProductionStage("subtitles", "字幕"),
        ProductionStage("composition", "合成", supports_units=True),
        ProductionStage("export", "导出"),
    ),
)


COMMERCE_PRODUCTION_WORKFLOW = ProductionWorkflow(
    mode=ProductionMode.COMMERCE,
    stages=(
        ProductionStage("product_ingest", "商品输入"),
        ProductionStage("product_truth", "商品事实"),
        ProductionStage("creative_strategy", "Creative Planning"),
        ProductionStage("variant_selection", "Variant Selection"),
        ProductionStage("script", "脚本"),
        ProductionStage("storyboard", "商业分镜"),
        ProductionStage("assets", "商品与画面素材", supports_units=True),
        ProductionStage("voice", "配音", supports_units=True),
        ProductionStage("subtitles", "字幕"),
        ProductionStage("composition", "合成", supports_units=True),
        ProductionStage("export", "导出"),
    ),
)


DRAMA_PREPRODUCTION_WORKFLOW = ProductionWorkflow(
    mode=ProductionMode.DRAMA,
    stages=(
        ProductionStage("story", "故事"),
        ProductionStage("bible", "Drama Bible"),
        ProductionStage("assets", "角色与场景"),
        ProductionStage("episode", "单集剧本"),
        ProductionStage("storyboard", "逐 Shot Storyboard"),
        ProductionStage("approval", "批准进入制作"),
    ),
)


DRAMA_PRODUCTION_WORKFLOW = ProductionWorkflow(
    mode=ProductionMode.DRAMA,
    stages=(
        ProductionStage("qa_before", "生成前 QA"),
        ProductionStage("media", "Shot Media", supports_units=True),
        ProductionStage("audio", "Shot Audio", supports_units=True),
        ProductionStage("subtitles", "Dialogue 字幕"),
        ProductionStage("qa_after", "生成后 QA"),
        ProductionStage("composition", "Episode Video", supports_units=True),
        ProductionStage("export", "导出"),
    ),
)


PRODUCTION_WORKFLOWS: dict[ProductionMode, ProductionWorkflow] = {
    ProductionMode.KNOWLEDGE: KNOWLEDGE_PRODUCTION_WORKFLOW,
    ProductionMode.COMMERCE: COMMERCE_PRODUCTION_WORKFLOW,
    # Drama pre-production is intentionally kept as a separate contract for
    # its review workspace. A persisted Drama production Task starts only
    # after that approval gate and uses this media/audio/video workflow.
    ProductionMode.DRAMA: DRAMA_PRODUCTION_WORKFLOW,
}


def normalize_production_mode(
    mode: str | ProductionMode | None,
) -> ProductionMode:
    if isinstance(mode, ProductionMode):
        return mode
    try:
        return ProductionMode(str(mode or ProductionMode.KNOWLEDGE.value))
    except ValueError:
        return ProductionMode.KNOWLEDGE


def get_production_workflow(
    mode: str | ProductionMode | None,
) -> ProductionWorkflow:
    """Resolve a workflow while keeping legacy or incomplete rows on Knowledge."""
    normalized = normalize_production_mode(mode)
    return PRODUCTION_WORKFLOWS.get(normalized, KNOWLEDGE_PRODUCTION_WORKFLOW)
