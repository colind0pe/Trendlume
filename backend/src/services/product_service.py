from __future__ import annotations

import mimetypes
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import ConflictException, NotFoundException, ValidationException
from src.domain.enums import AssetType
from src.models.asset import AssetModel
from src.models.product import ProductAssetModel, ProductModel
from src.models.task import TaskModel
from src.schemas.product import (
    ProductAssetUpdate,
    ProductClaim,
    ProductClaimInput,
    ProductCreate,
    ProductFact,
    ProductTruthSheet,
    ProductUpdate,
)
from src.services.asset_service import AssetService
from src.services.product_importer import (
    ParsedProduct,
    ProductImporter,
    parse_product_html,
    validate_public_url,
)
from src.storage.local_storage import LocalStorageService


class ProductService:
    """Product facts and product-specific media, separate from project assets."""

    def __init__(
        self,
        session: AsyncSession,
        storage: LocalStorageService | None = None,
        importer: ProductImporter | None = None,
    ) -> None:
        self.session = session
        self.storage = storage or LocalStorageService()
        self.importer = importer or ProductImporter()
        self.asset_service = AssetService(session, storage=self.storage)

    @staticmethod
    def _fact_id(field: str) -> str:
        return f"fact-{field.replace('.', '-').replace(' ', '-').lower()}"

    @classmethod
    def build_truth_sheet(
        cls,
        *,
        product_id: str,
        title: str,
        brand: str,
        description: str,
        price: str,
        currency: str,
        specifications: dict[str, Any],
        field_sources: dict[str, str] | None = None,
        source_url: str | None = None,
        selling_points: list[ProductClaimInput] | None = None,
    ) -> ProductTruthSheet:
        field_sources = field_sources or {}
        facts: list[ProductFact] = []
        values: list[tuple[str, Any]] = [
            ("title", title),
            ("brand", brand),
            ("description", description),
            ("price", price),
            ("currency", currency),
        ]
        values.extend((f"specifications.{key}", value) for key, value in specifications.items())
        for field_name, value in values:
            if value is None or not str(value).strip():
                continue
            source_type = field_sources.get(field_name, "user_input")
            source_ref = f"{source_type}:{field_name}"
            certainty = "source_reported" if source_type != "user_input" and source_type != "manual_correction" else "user_asserted"
            facts.append(
                ProductFact(
                    id=cls._fact_id(field_name),
                    field=field_name,
                    value=value,
                    source_type=source_type,
                    source_ref=source_ref,
                source_url=source_url,
                certainty=certainty,
                user_confirmed=certainty == "user_asserted",
            )
            )

        fact_ids = {fact.id for fact in facts}
        claims: list[ProductClaim] = []
        for index, item in enumerate(selling_points or [], start=1):
            claim_id = f"claim-selling-point-{index}"
            evidence = list(dict.fromkeys(item.evidence_refs))
            if not evidence:
                evidence = [f"user_input:claim:{claim_id}"]
            evidence = [ref for ref in evidence if ref in fact_ids or ref.startswith("user_input:")]
            claims.append(
                ProductClaim(
                    id=claim_id,
                    text=item.text.strip(),
                    claim_type=item.claim_type,
                    evidence_refs=evidence,
                    certainty="user_asserted" if evidence else "uncertain",
                )
            )

        numerical_claims: list[ProductClaim] = []
        for fact in facts:
            if fact.field == "price" or fact.field.startswith("specifications."):
                text = f"{fact.field.removeprefix('specifications.')}: {fact.value}"
                numerical_claims.append(
                    ProductClaim(
                        id=f"claim-number-{fact.id}",
                        text=text,
                        claim_type="numerical",
                        evidence_refs=[fact.id],
                        certainty=fact.certainty,
                    )
                )

        unresolved = [field for field in ("brand", "description", "price") if field not in {fact.field for fact in facts}]
        if not specifications:
            unresolved.append("specifications")
        return ProductTruthSheet(
            product_id=product_id,
            facts=facts,
            selling_points=claims,
            numerical_claims=numerical_claims,
            unresolved_fields=list(dict.fromkeys(unresolved)),
            generated_at=datetime.now(UTC).isoformat(),
        )

    @staticmethod
    def _source_fields(parsed: ParsedProduct) -> dict[str, str]:
        return dict(parsed.field_sources)

    async def _with_assets(self, product: ProductModel) -> ProductModel:
        result = await self.session.execute(
            select(ProductModel)
            .execution_options(populate_existing=True)
            .where(ProductModel.id == product.id)
            .options(selectinload(ProductModel.assets).selectinload(ProductAssetModel.asset))
        )
        return result.scalar_one()

    async def create_product(self, data: ProductCreate) -> ProductModel:
        product_id = f"prod_{uuid.uuid4().hex[:12]}"
        source_url = validate_public_url(data.source_url) if data.source_url else None
        truth = self.build_truth_sheet(
            product_id=product_id,
            title=data.title,
            brand=data.brand,
            description=data.description,
            price=data.price,
            currency=data.currency,
            specifications=data.specifications,
            source_url=source_url,
            selling_points=data.selling_points,
        )
        product = ProductModel(
            id=product_id,
            title=data.title,
            brand=data.brand,
            description=data.description,
            price=data.price,
            currency=data.currency,
            specifications=data.specifications,
            source_url=source_url,
            source_snapshot={"field_sources": {field: "user_input" for field in ("title", "brand", "description", "price", "currency")}},
            truth_sheet=truth.model_dump(mode="json"),
            status="draft",
        )
        self.session.add(product)
        await self.session.commit()
        return await self._with_assets(product)

    async def import_from_url(self, url: str) -> ProductModel:
        markup, final_url = await self.importer.fetch_html(url)
        parsed = parse_product_html(markup, final_url)
        if not parsed.title:
            raise ValidationException("商品页面没有解析出商品标题，请改用手工输入。")
        product_id = f"prod_{uuid.uuid4().hex[:12]}"
        truth = self.build_truth_sheet(
            product_id=product_id,
            title=parsed.title,
            brand=parsed.brand,
            description=parsed.description,
            price=parsed.price,
            currency=parsed.currency,
            specifications=parsed.specifications,
            field_sources=self._source_fields(parsed),
            source_url=final_url,
        )
        snapshot = {**parsed.source_snapshot, "images": parsed.images, "final_url": final_url}
        product = ProductModel(
            id=product_id,
            title=parsed.title,
            brand=parsed.brand,
            description=parsed.description,
            price=parsed.price,
            currency=parsed.currency,
            specifications=parsed.specifications,
            source_url=final_url,
            source_snapshot=snapshot,
            truth_sheet=truth.model_dump(mode="json"),
            status="imported",
        )
        self.session.add(product)
        await self.session.flush()
        asset_warnings: list[str] = []
        for index, image_url in enumerate(parsed.images[:6]):
            asset_id = None
            try:
                content, mime_type, final_asset_url = await self.importer.fetch_media(image_url)
                if not mime_type.startswith("image/"):
                    raise ValidationException("商品图片地址返回的不是图片。")
                filename = Path(urlsplit(final_asset_url).path).name or f"product-{index + 1}.jpg"
                asset = await self.asset_service.save_asset(
                    content=content,
                    file_name=filename,
                    mime_type=mime_type or mimetypes.guess_type(filename)[0] or "image/jpeg",
                    asset_type=AssetType.IMAGE,
                    project_id=None,
                    metadata={"scope": "product", "product_id": product_id, "source_url": final_asset_url},
                )
                asset_id = asset.id
                source_kind = "url_import"
                image_url = final_asset_url
            except Exception as exc:
                asset_warnings.append(f"{image_url}: {str(exc)}")
                source_kind = "url_reference"
            self.session.add(
                ProductAssetModel(
                    id=f"pasta_{uuid.uuid4().hex[:12]}",
                    product_id=product_id,
                    asset_id=asset_id,
                    asset_type="image",
                    role="hero" if index == 0 else "gallery",
                    source_kind=source_kind,
                    source_url=image_url,
                    alt_text=parsed.title,
                    sort_order=index,
                )
            )
        if asset_warnings:
            product.source_snapshot = {**snapshot, "asset_warnings": asset_warnings}
        await self.session.commit()
        return await self._with_assets(product)

    async def get_product(self, product_id: str) -> ProductModel:
        result = await self.session.execute(
            select(ProductModel)
            .execution_options(populate_existing=True)
            .where(ProductModel.id == product_id)
            .options(selectinload(ProductModel.assets).selectinload(ProductAssetModel.asset))
        )
        product = result.scalar_one_or_none()
        if not product:
            raise NotFoundException("Product", product_id)
        return product

    async def list_products(self, limit: int = 50, offset: int = 0) -> list[ProductModel]:
        result = await self.session.execute(
            select(ProductModel)
            .execution_options(populate_existing=True)
            .options(selectinload(ProductModel.assets).selectinload(ProductAssetModel.asset))
            .order_by(ProductModel.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().unique().all())

    async def update_product(self, product_id: str, data: ProductUpdate) -> ProductModel:
        product = await self.get_product(product_id)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("source_url"):
            changes["source_url"] = validate_public_url(changes["source_url"])
        old_claims = [
            ProductClaimInput(
                text=item["text"],
                claim_type=item.get("claim_type", "selling_point"),
                evidence_refs=item.get("evidence_refs", []),
            )
            for item in (product.truth_sheet or {}).get("selling_points", [])
            if isinstance(item, dict) and item.get("text")
        ]
        for key in ("title", "brand", "description", "price", "currency", "specifications", "source_url"):
            if key in changes:
                setattr(product, key, changes[key])
        claims = changes.get("selling_points", old_claims)
        field_sources = dict((product.source_snapshot or {}).get("field_sources") or {})
        for key in ("title", "brand", "description", "price", "currency"):
            if key in changes:
                field_sources[key] = "manual_correction"
        if "specifications" in changes:
            for key in (changes.get("specifications") or {}):
                field_sources[f"specifications.{key}"] = "manual_correction"
        product.source_snapshot = {**(product.source_snapshot or {}), "field_sources": field_sources}
        truth = self.build_truth_sheet(
            product_id=product.id,
            title=product.title,
            brand=product.brand,
            description=product.description,
            price=product.price,
            currency=product.currency,
            specifications=product.specifications,
            field_sources=field_sources,
            source_url=product.source_url,
            selling_points=claims,
        )
        product.truth_sheet = truth.model_dump(mode="json")
        product.status = "ready" if product.assets else product.status
        await self.session.commit()
        return await self.get_product(product.id)

    async def update_truth_sheet(self, product_id: str, truth: ProductTruthSheet) -> ProductModel:
        product = await self.get_product(product_id)
        allowed = {fact.id for fact in truth.facts} | {
            ref for fact in truth.facts for ref in (fact.source_ref,)
        }
        for claim in [*truth.selling_points, *truth.numerical_claims]:
            invalid = [ref for ref in claim.evidence_refs if ref not in allowed and not ref.startswith("user_input:")]
            if invalid:
                raise ValidationException(f"商品主张缺少可追溯证据：{', '.join(invalid)}")
        truth.product_id = product.id
        product.truth_sheet = truth.model_dump(mode="json")
        product.status = "ready" if truth.facts else product.status
        await self.session.commit()
        return await self.get_product(product.id)

    async def delete_product(self, product_id: str) -> bool:
        product = await self.get_product(product_id)
        task_id = await self.session.scalar(select(TaskModel.id).where(TaskModel.product_id == product.id).limit(1))
        if task_id:
            raise ConflictException("商品已被 Commerce 任务引用，不能删除。")
        for product_asset in product.assets:
            if product_asset.asset_id:
                asset = await self.session.get(AssetModel, product_asset.asset_id)
                if asset:
                    await self.asset_service.storage.delete_file(asset.file_path)
                    await self.session.delete(asset)
        await self.session.delete(product)
        await self.session.commit()
        return True

    async def add_asset(
        self,
        product_id: str,
        *,
        content: bytes,
        file_name: str,
        mime_type: str,
        asset_type: AssetType,
        role: str = "gallery",
        alt_text: str = "",
    ) -> ProductAssetModel:
        product = await self.get_product(product_id)
        if asset_type not in {AssetType.IMAGE, AssetType.VIDEO}:
            raise ValidationException("商品素材只支持图片或视频。")
        if len(content) > 50 * 1024 * 1024:
            raise ValidationException("商品素材不能超过 50 MB。")
        asset = await self.asset_service.save_asset(
            content=content,
            file_name=file_name,
            mime_type=mime_type or "application/octet-stream",
            asset_type=asset_type,
            project_id=None,
            metadata={"scope": "product", "product_id": product.id, "role": role},
        )
        row = ProductAssetModel(
            id=f"pasta_{uuid.uuid4().hex[:12]}",
            product_id=product.id,
            asset_id=asset.id,
            asset_type=asset_type.value,
            role=role,
            source_kind="upload",
            alt_text=alt_text or product.title,
            sort_order=len(product.assets),
        )
        self.session.add(row)
        product.status = "ready"
        await self.session.commit()
        await self.session.refresh(row)
        return await self.session.get(ProductAssetModel, row.id, options=[selectinload(ProductAssetModel.asset)])

    async def delete_asset(self, product_id: str, product_asset_id: str) -> bool:
        product = await self.get_product(product_id)
        row = next((item for item in product.assets if item.id == product_asset_id), None)
        if not row:
            raise NotFoundException("ProductAsset", product_asset_id)
        if row.asset_id:
            asset = await self.session.get(AssetModel, row.asset_id)
            if asset:
                await self.asset_service.storage.delete_file(asset.file_path)
                await self.session.delete(asset)
        # Keep the already-loaded relationship in sync. The API session is
        # reused across requests in tests and in some embedded deployments;
        # leaving the deleted row in the collection makes a later product
        # delete issue a second DELETE for the same product asset.
        product.assets.remove(row)
        await self.session.delete(row)
        await self.session.commit()
        return True

    async def update_asset(
        self,
        product_id: str,
        product_asset_id: str,
        data: ProductAssetUpdate,
    ) -> ProductAssetModel:
        product = await self.get_product(product_id)
        row = next((item for item in product.assets if item.id == product_asset_id), None)
        if not row:
            raise NotFoundException("ProductAsset", product_asset_id)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("source_url"):
            changes["source_url"] = validate_public_url(changes["source_url"])
        for key, value in changes.items():
            setattr(row, key, value)
        await self.session.commit()
        refreshed = await self.session.execute(
            select(ProductAssetModel)
            .where(ProductAssetModel.id == row.id)
            .options(selectinload(ProductAssetModel.asset))
        )
        return refreshed.scalar_one()
