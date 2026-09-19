from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from src.core.exceptions import ValidationException
from src.domain.enums import ProductionMode
from src.domain.production_workflows import ProductionWorkflow, normalize_production_mode


@runtime_checkable
class ProductionPipeline(Protocol):
    production_mode: ProductionMode
    workflow: ProductionWorkflow

    async def execute(self) -> dict[str, Any]: ...


class BaseProductionPipeline(ABC):
    production_mode: ProductionMode
    workflow: ProductionWorkflow

    @abstractmethod
    async def execute(self) -> dict[str, Any]:
        raise NotImplementedError


PipelineFactory = Callable[..., ProductionPipeline]


class ProductionPipelineRegistry:
    """Maps a persisted production mode to its production implementation."""

    def __init__(self) -> None:
        self._factories: dict[ProductionMode, PipelineFactory] = {}

    def register(
        self,
        mode: str | ProductionMode,
        factory: PipelineFactory,
        *,
        replace: bool = False,
    ) -> None:
        normalized = normalize_production_mode(mode)
        if normalized in self._factories and not replace:
            raise ValueError(f"Production pipeline already registered: {normalized.value}")
        self._factories[normalized] = factory

    def _ensure_builtin_pipelines(self) -> None:
        # Import lazily so the registry remains independent from the default
        # implementation and can be used by TaskService during test setup.
        from src.services.commerce_pipeline import CommerceProductionPipeline
        from src.services.drama_production_pipeline import DramaProductionPipeline
        from src.services.durable_pipeline import DurableVideoPipeline

        builtins = {
            ProductionMode.KNOWLEDGE: DurableVideoPipeline,
            ProductionMode.COMMERCE: CommerceProductionPipeline,
            ProductionMode.DRAMA: DramaProductionPipeline,
        }
        for mode, factory in builtins.items():
            if mode not in self._factories:
                self.register(mode, factory)

    def is_registered(self, mode: str | ProductionMode | None) -> bool:
        self._ensure_builtin_pipelines()
        return normalize_production_mode(mode) in self._factories

    def available_modes(self) -> tuple[ProductionMode, ...]:
        self._ensure_builtin_pipelines()
        return tuple(self._factories)

    def create(
        self,
        mode: str | ProductionMode | None,
        session,
        job,
        rendering_service_factory: Callable | None = None,
    ) -> ProductionPipeline:
        self._ensure_builtin_pipelines()
        normalized = normalize_production_mode(mode)
        factory = self._factories.get(normalized)
        if factory is None:
            raise ValidationException(f"生产模式 {normalized.value} 暂未开放。")
        return factory(session, job, rendering_service_factory)


production_pipeline_registry = ProductionPipelineRegistry()
