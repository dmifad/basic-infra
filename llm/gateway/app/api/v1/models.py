"""``GET /v1/models`` route — models visible to the authenticated tenant."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...routing.registry import Registry
from ...schemas.models import ModelList
from ...tenancy.store import TenantRecord
from ..deps import current_tenant

router = APIRouter(tags=["models"])


@router.get("/models", response_model=ModelList)
async def list_models(
    request: Request,
    tenant: TenantRecord = Depends(current_tenant),
) -> ModelList:
    """List models available to the current tenant (filtered by ``allowed_models``)."""
    registry: Registry = request.app.state.registry
    return ModelList(data=registry.models_for(tenant))
