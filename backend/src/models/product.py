from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.asset import AssetModel
    from src.models.project import ProjectModel


class ProductModel(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_project", "project_id"),
        UniqueConstraint("project_id", name="uq_products_project"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    currency: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    specifications: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    truth_sheet: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    assets: Mapped[list[ProductAssetModel]] = relationship(
        "ProductAssetModel",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductAssetModel.sort_order, ProductAssetModel.created_at",
        lazy="selectin",
    )
    project: Mapped[ProjectModel] = relationship("ProjectModel", back_populates="products")


class ProductAssetModel(Base):
    __tablename__ = "product_assets"

    __table_args__ = (Index("ix_product_assets_product_order", "product_id", "sort_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="gallery", nullable=False)
    source_kind: Mapped[str] = mapped_column(String(30), default="upload", nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    alt_text: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    product: Mapped[ProductModel] = relationship("ProductModel", back_populates="assets")
    asset: Mapped[AssetModel | None] = relationship("AssetModel", lazy="joined")
