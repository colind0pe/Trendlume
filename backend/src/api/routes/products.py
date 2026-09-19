from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from src.api.dependencies import (
    get_commerce_planning_service,
    get_product_service,
    get_task_service,
)
from src.core.exceptions import ValidationException
from src.domain.enums import AssetType, CreativeAngle, ProductionMode
from src.schemas.common import APIResponse
from src.schemas.creative_plan import (
    CreativePlanConfirmFactsRequest,
    CreativePlanDuplicateRequest,
    CreativePlanGenerateRequest,
    CreativePlanProduceRequest,
    CreativePlanResponse,
)
from src.schemas.product import (
    ProductAssetUpdate,
    ProductCreate,
    ProductImportRequest,
    ProductResponse,
    ProductTruthSheetUpdate,
    ProductUpdate,
)
from src.schemas.task import TaskCreate, TaskResponse
from src.services.commerce_planning_service import CommercePlanningService
from src.services.product_service import ProductService
from src.services.task_service import TaskService

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("", response_model=APIResponse[ProductResponse], status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductCreate, service: ProductService = Depends(get_product_service)):
    product = await service.create_product(payload)
    return APIResponse(data=ProductResponse.model_validate(product))


@router.post("/import", response_model=APIResponse[ProductResponse], status_code=status.HTTP_201_CREATED)
async def import_product(payload: ProductImportRequest, service: ProductService = Depends(get_product_service)):
    product = await service.import_from_url(payload.url)
    return APIResponse(data=ProductResponse.model_validate(product))


@router.get("", response_model=APIResponse[list[ProductResponse]])
async def list_products(
    limit: int = 50,
    offset: int = 0,
    service: ProductService = Depends(get_product_service),
):
    if not 1 <= limit <= 100 or offset < 0:
        raise ValidationException("商品列表分页参数无效。")
    products = await service.list_products(limit=limit, offset=offset)
    return APIResponse(data=[ProductResponse.model_validate(product) for product in products])


@router.get(
    "/{product_id}/creative-plans",
    response_model=APIResponse[list[CreativePlanResponse]],
)
async def list_creative_plans(
    product_id: str,
    service: CommercePlanningService = Depends(get_commerce_planning_service),
):
    plans = await service.list_plans(product_id)
    return APIResponse(data=[CreativePlanResponse.model_validate(plan) for plan in plans])


@router.post(
    "/{product_id}/creative-plans",
    response_model=APIResponse[list[CreativePlanResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def generate_creative_plans(
    product_id: str,
    payload: CreativePlanGenerateRequest | None = None,
    service: CommercePlanningService = Depends(get_commerce_planning_service),
):
    plans = await service.generate_plans(product_id, payload)
    return APIResponse(data=[CreativePlanResponse.model_validate(plan) for plan in plans])


@router.post(
    "/{product_id}/creative-plans/{plan_id}/select",
    response_model=APIResponse[CreativePlanResponse],
)
async def select_creative_plan(
    product_id: str,
    plan_id: str,
    service: CommercePlanningService = Depends(get_commerce_planning_service),
):
    plan = await service.select_plan(product_id, plan_id)
    return APIResponse(data=CreativePlanResponse.model_validate(plan))


@router.post(
    "/{product_id}/creative-plans/{plan_id}/duplicate",
    response_model=APIResponse[CreativePlanResponse],
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_creative_plan(
    product_id: str,
    plan_id: str,
    payload: CreativePlanDuplicateRequest | None = None,
    service: CommercePlanningService = Depends(get_commerce_planning_service),
):
    plan = await service.duplicate_plan(
        product_id,
        plan_id,
        payload.variant_label if payload else None,
    )
    return APIResponse(data=CreativePlanResponse.model_validate(plan))


@router.post(
    "/{product_id}/creative-plans/{plan_id}/confirm-facts",
    response_model=APIResponse[CreativePlanResponse],
)
async def confirm_creative_plan_facts(
    product_id: str,
    plan_id: str,
    payload: CreativePlanConfirmFactsRequest | None = None,
    service: CommercePlanningService = Depends(get_commerce_planning_service),
):
    if payload is not None and not payload.confirm:
        plan = await service.get_plan(plan_id, product_id)
    else:
        plan = await service.confirm_facts(product_id, plan_id)
    return APIResponse(data=CreativePlanResponse.model_validate(plan))


@router.post(
    "/{product_id}/creative-plans/{plan_id}/produce",
    response_model=APIResponse[TaskResponse],
    status_code=status.HTTP_201_CREATED,
)
async def produce_from_creative_plan(
    product_id: str,
    plan_id: str,
    payload: CreativePlanProduceRequest,
    planning_service: CommercePlanningService = Depends(get_commerce_planning_service),
    task_service: TaskService = Depends(get_task_service),
):
    plan = await planning_service.get_plan(plan_id, product_id)
    if plan.status not in {"selected", "variant"}:
        raise ValidationException("请先选择 Creative Plan，再进入 storyboard/media 生产。")
    task = await task_service.create_task(
        payload.project_id,
        TaskCreate(
            title=payload.title or f"{plan.product.title} · {plan.variant_label}",
            production_mode=ProductionMode.COMMERCE,
            product_id=product_id,
            creative_plan_id=plan.id,
            creative_angle=CreativeAngle(plan.angle),
            input_payload={
                "production_mode": ProductionMode.COMMERCE.value,
                "product_id": product_id,
                "creative_plan_id": plan.id,
                "creative_angle": plan.angle,
            },
        ),
    )
    return APIResponse(data=TaskResponse.model_validate(task))


@router.get("/{product_id}", response_model=APIResponse[ProductResponse])
async def get_product(product_id: str, service: ProductService = Depends(get_product_service)):
    product = await service.get_product(product_id)
    return APIResponse(data=ProductResponse.model_validate(product))


@router.patch("/{product_id}", response_model=APIResponse[ProductResponse])
async def update_product(
    product_id: str,
    payload: ProductUpdate,
    service: ProductService = Depends(get_product_service),
):
    product = await service.update_product(product_id, payload)
    return APIResponse(data=ProductResponse.model_validate(product))


@router.put("/{product_id}/truth-sheet", response_model=APIResponse[ProductResponse])
async def update_product_truth_sheet(
    product_id: str,
    payload: ProductTruthSheetUpdate,
    service: ProductService = Depends(get_product_service),
):
    product = await service.update_truth_sheet(product_id, payload.truth_sheet)
    return APIResponse(data=ProductResponse.model_validate(product))


@router.post("/{product_id}/assets", response_model=APIResponse[ProductResponse], status_code=status.HTTP_201_CREATED)
async def upload_product_asset(
    product_id: str,
    file: UploadFile = File(...),
    asset_type: AssetType = Form(...),
    role: str = Form("gallery"),
    alt_text: str = Form(""),
    service: ProductService = Depends(get_product_service),
):
    content = await file.read(50 * 1024 * 1024 + 1)
    if len(content) > 50 * 1024 * 1024:
        raise ValidationException("商品素材不能超过 50 MB。")
    await service.add_asset(
        product_id,
        content=content,
        file_name=file.filename or "product-asset.bin",
        mime_type=file.content_type or "application/octet-stream",
        asset_type=asset_type,
        role=role,
        alt_text=alt_text,
    )
    product = await service.get_product(product_id)
    return APIResponse(data=ProductResponse.model_validate(product))


@router.delete("/{product_id}/assets/{product_asset_id}", response_model=APIResponse[bool])
async def delete_product_asset(
    product_id: str,
    product_asset_id: str,
    service: ProductService = Depends(get_product_service),
):
    return APIResponse(data=await service.delete_asset(product_id, product_asset_id))


@router.patch("/{product_id}/assets/{product_asset_id}", response_model=APIResponse[ProductResponse])
async def update_product_asset(
    product_id: str,
    product_asset_id: str,
    payload: ProductAssetUpdate,
    service: ProductService = Depends(get_product_service),
):
    await service.update_asset(product_id, product_asset_id, payload)
    product = await service.get_product(product_id)
    return APIResponse(data=ProductResponse.model_validate(product))


@router.delete("/{product_id}", response_model=APIResponse[bool])
async def delete_product(product_id: str, service: ProductService = Depends(get_product_service)):
    return APIResponse(data=await service.delete_product(product_id))
