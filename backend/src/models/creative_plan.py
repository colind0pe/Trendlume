from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.product import ProductModel


class CreativePlanModel(Base):
    """A low-cost, reviewable commerce direction before media generation."""

    __tablename__ = "commerce_creative_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_plan_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("commerce_creative_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    variant_label: Mapped[str] = mapped_column(String(100), default="Plan", nullable=False)
    variant_index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    angle: Mapped[str] = mapped_column(String(30), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str] = mapped_column(Text, nullable=False)
    core_message: Mapped[str] = mapped_column(Text, nullable=False)
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    scene_outline: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    cta: Mapped[str] = mapped_column(Text, nullable=False)
    truth_sheet_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    fact_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    product: Mapped[ProductModel] = relationship("ProductModel", lazy="joined")
