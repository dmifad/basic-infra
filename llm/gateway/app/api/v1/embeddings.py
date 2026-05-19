"""``POST /v1/embeddings`` route.

Phase 3 wires auth, rate limiting and validation; dispatch lands in Phase 4.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...exceptions import ModelNotFoundError
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
    # TODO(week4-phase-4): dispatch via the backend router.
    raise ModelNotFoundError(f"Model not found: {body.model}")
