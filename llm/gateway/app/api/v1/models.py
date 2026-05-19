"""``GET /v1/models`` route.

Returns models visible to the authenticated tenant. Until the backend registry
is wired (Phase 4) no models are registered, so the list is empty.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

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
    registry = getattr(request.app.state, "registry", None)
    if registry is None:
        return ModelList(data=[])
    # TODO(week4-phase-4): registry.models_for(tenant) — filter by allowed_models.
    return ModelList(data=registry.models_for(tenant))
