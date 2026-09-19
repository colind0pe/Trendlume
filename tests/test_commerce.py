from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.exceptions import ValidationException
from src.domain.enums import AssetType, CreativeAngle, ProductionMode
from src.models import ProjectModel, SceneModel, TaskModel
from src.models.workflow import WorkflowStepRunModel
from src.schemas.product import ProductClaimInput, ProductCreate, ProductTruthSheet
from src.services.generation_service import GenerationService
from src.services.product_importer import parse_product_html, validate_public_url
from src.services.product_service import ProductService
from src.services.rendering_service import RenderingService
from src.storage.local_storage import LocalStorageService
from src.tasks.executor import VideoWorkflowExecutor
from src.tasks.job import Job


class StubImporter:
    def __init__(self, markup: str):
        self.markup = markup

    async def fetch_html(self, url: str):
        return self.markup, url

    async def fetch_media(self, url: str):
        return b"product-image", "image/png", url


def test_product_parser_prioritizes_json_ld_and_keeps_sources():
    parsed = parse_product_html(
        """
        <html><head>
          <meta property="og:title" content="OG fallback">
          <meta property="og:image" content="/og.png">
          <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Product","name":"事实商品",
           "brand":{"@type":"Brand","name":"事实品牌"},"description":"真实描述",
           "image":["/hero.png"],"offers":{"price":"199","priceCurrency":"CNY"},
           "sku":"SKU-1","additionalProperty":[{"name":"容量","value":"500ml"}]}
          </script>
        </head><body><h1>页面标题</h1></body></html>
        """,
        "https://shop.example/products/1",
    )

    assert parsed.title == "事实商品"
    assert parsed.brand == "事实品牌"
    assert parsed.price == "199"
    assert parsed.field_sources["price"] == "json_ld"
    assert parsed.specifications["容量"] == "500ml"
    assert parsed.images[0] == "https://shop.example/hero.png"


def test_product_importer_rejects_private_and_unsafe_urls():
    for url in ("http://127.0.0.1/product", "http://10.0.0.2/product", "file:///tmp/product"):
        with pytest.raises(ValidationException):
            validate_public_url(url)


@pytest.mark.asyncio
async def test_product_import_builds_truth_sheet_and_downloads_local_asset(test_session, tmp_path):
    markup = """
    <script type="application/ld+json">
    {"@type":"Product","name":"导入商品","brand":"Demo","description":"可核对的描述",
     "image":["https://shop.example/hero.png"],"offers":{"price":"88","priceCurrency":"CNY"}}
    </script>
    """
    service = ProductService(
        test_session,
        storage=LocalStorageService(tmp_path / "storage"),
        importer=StubImporter(markup),
    )
    product = await service.import_from_url("https://shop.example/product/1")

    assert product.title == "导入商品"
    assert product.truth_sheet["facts"][0]["source_type"] == "json_ld"
    assert product.truth_sheet["facts"][0]["certainty"] == "source_reported"
    assert product.assets[0].asset_id
    assert product.assets[0].source_kind == "url_import"


@pytest.mark.asyncio
async def test_truth_sheet_claims_require_evidence(test_session):
    service = ProductService(test_session)
    product = await service.create_product(
        ProductCreate(
            title="手工商品",
            brand="用户输入",
            price="99",
            selling_points=[ProductClaimInput(text="用户确认的卖点")],
        )
    )

    claim = product.truth_sheet["selling_points"][0]
    assert claim["evidence_refs"] == ["user_input:claim:claim-selling-point-1"]
    assert claim["certainty"] == "user_asserted"
    with pytest.raises(ValidationException, match="可追溯证据"):
        await service.update_truth_sheet(
            product.id,
            ProductTruthSheet.model_validate(
                product.truth_sheet
                | {
                "selling_points": [
                    {"id": "claim-bad", "text": "没有证据", "evidence_refs": ["invented"]}
                ]
                }
            ),
        )


@pytest.mark.asyncio
async def test_commerce_prefix_resumes_without_rebuilding_completed_stages(test_session, tmp_path):
    project = ProjectModel(id=f"project_{uuid4().hex[:8]}", name="Commerce pipeline")
    test_session.add(project)
    await test_session.flush()
    product = await ProductService(
        test_session,
        storage=LocalStorageService(tmp_path / "product-storage"),
    ).create_product(ProductCreate(title="真实商品", brand="Demo", price="39"))
    task = TaskModel(
        id=f"task_{uuid4().hex[:8]}",
        project_id=project.id,
        product_id=product.id,
        production_mode=ProductionMode.COMMERCE.value,
        creative_angle=CreativeAngle.DEMO.value,
        title="Commerce pipeline",
        input_payload={
            "product_id": product.id,
            "creative_angle": CreativeAngle.DEMO.value,
            "content_mode": "static",
            "template_id": "static_editorial_quote",
            "target_scene_count": 8,
            "enable_research": False,
            "bgm_enabled": False,
        },
    )
    test_session.add(task)
    await test_session.commit()

    @asynccontextmanager
    async def sessions():
        yield test_session

    executor = VideoWorkflowExecutor(
        sessions,
        lambda db: RenderingService(db, LocalStorageService(tmp_path / "pipeline-storage")),
    )
    await executor.execute(Job(task_id=task.id, params={"single_step": "assets"}))
    runs = list((await test_session.scalars(select(WorkflowStepRunModel))).all())
    prefix = {run.step_key: run for run in runs if run.step_key in {"product_ingest", "product_truth", "creative_strategy", "script", "storyboard"}}
    assert set(prefix) == {"product_ingest", "product_truth", "creative_strategy", "script", "storyboard"}
    prepared_task = await test_session.get(TaskModel, task.id)
    assert prepared_task.input_payload["_commerce_prepared"] is True
    assert "knowledge_brief" not in prepared_task.input_payload

    await executor.execute(Job(task_id=task.id, params={"single_step": "assets"}))
    rerun = list((await test_session.scalars(select(WorkflowStepRunModel))).all())
    assert {
        key: len([run for run in rerun if run.step_key == key])
        for key in prefix
    } == {key: 1 for key in prefix}


@pytest.mark.asyncio
async def test_commerce_product_scenes_reuse_locked_asset_without_redraw(
    test_session,
    tmp_path,
    monkeypatch,
):
    project = ProjectModel(id=f"project_{uuid4().hex[:8]}", name="Locked product")
    test_session.add(project)
    await test_session.flush()
    storage = LocalStorageService(tmp_path / "storage")
    service = ProductService(test_session, storage=storage)
    product = await service.create_product(ProductCreate(title="真实商品"))
    product_asset = await service.add_asset(
        product.id,
        content=b"real-product-asset",
        file_name="hero.png",
        mime_type="image/png",
        asset_type=AssetType.IMAGE,
        role="hero",
    )
    task = TaskModel(
        id=f"task_{uuid4().hex[:8]}",
        project_id=project.id,
        product_id=product.id,
        production_mode=ProductionMode.COMMERCE.value,
        creative_angle=CreativeAngle.DIRECT.value,
        title="锁定真实商品素材",
        input_payload={
            "product_id": product.id,
            "creative_angle": CreativeAngle.DIRECT.value,
            "content_mode": "generated_image",
            "template_id": "image_gallery_matted",
            "target_scene_count": 8,
            "enable_research": False,
            "bgm_enabled": False,
        },
    )
    test_session.add(task)
    await test_session.commit()

    generated_scene_ids: list[str] = []
    original_generate = GenerationService.generate_scene_image

    async def record_generated_scene(self, scene_id, prompt_override=None):
        generated_scene_ids.append(scene_id)
        return await original_generate(self, scene_id, prompt_override=prompt_override)

    async def skip_media_probe(_path):
        return None

    monkeypatch.setattr(GenerationService, "generate_scene_image", record_generated_scene)
    monkeypatch.setattr("src.services.durable_pipeline.probe_file", skip_media_probe)
    monkeypatch.setattr("src.services.workflow_runtime.probe_file", skip_media_probe)

    @asynccontextmanager
    async def sessions():
        yield test_session

    executor = VideoWorkflowExecutor(
        sessions,
        lambda db: RenderingService(db, storage),
    )
    await executor.execute(Job(task_id=task.id, params={"single_step": "assets"}))

    scenes = list((await test_session.scalars(select(SceneModel).where(SceneModel.task_id == task.id))).all())
    locked_scene_ids = {
        scene.id
        for scene in scenes
        if (scene.production_metadata or {}).get("commerce", {}).get("asset_locked")
    }
    assert locked_scene_ids
    assert locked_scene_ids.isdisjoint(generated_scene_ids)
    assert all(scene.media_asset_id == product_asset.asset_id for scene in scenes if scene.id in locked_scene_ids)
