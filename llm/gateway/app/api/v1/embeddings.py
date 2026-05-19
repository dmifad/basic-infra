"""``POST /v1/embeddings`` route."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...routing.router import Router
from ...schemas.embeddings import EmbeddingRequest, EmbeddingResponse
from ...tenancy.store import TenantRecord
from ..deps import current_tenant, enforce_rate_limit

router = APIRouter(tags=["embeddings"])


@router.post("/embeddings", response_model=EmbeddingResponse)
async def create_embedding(
    body: EmbeddingRequest,
    request: Request,
    tenant: TenantRecord = Depends(current_tenant),
) -> EmbeddingResponse:
    """Create embeddings (OpenAI-compatible)."""
    request.state.model = body.model
    await enforce_rate_limit(request, tenant, "embeddings")
    gateway_router: Router = request.app.state.router
    return await gateway_router.embedding(body, tenant)
