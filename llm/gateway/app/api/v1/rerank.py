"""``POST /v1/rerank`` route — Cohere-style reranking (ADR-0002)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...routing.router import Router
from ...schemas.rerank import RerankRequest, RerankResponse
from ...tenancy.store import TenantRecord
from ..deps import current_tenant, enforce_rate_limit

router = APIRouter(tags=["rerank"])


@router.post("/rerank", response_model=RerankResponse)
async def create_rerank(
    body: RerankRequest,
    request: Request,
    tenant: TenantRecord = Depends(current_tenant),
) -> RerankResponse:
    """Rerank documents against a query (Cohere-style)."""
    request.state.model = body.model
    await enforce_rate_limit(request, tenant, "rerank")
    gateway_router: Router = request.app.state.router
    return await gateway_router.rerank(body, tenant)
