"""``POST /v1/completions`` route — legacy text completions.

Phase 3 wires auth, rate limiting and validation; dispatch lands in Phase 4.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...exceptions import ModelNotFoundError
from ...schemas.completions import CompletionRequest, CompletionResponse
from ...tenancy.store import TenantRecord
from ..deps import current_tenant, enforce_rate_limit

router = APIRouter(tags=["chat"])


@router.post("/completions", response_model=CompletionResponse)
async def create_completion(
    body: CompletionRequest,
    request: Request,
    tenant: TenantRecord = Depends(current_tenant),
) -> CompletionResponse:
    """Create a legacy text completion (OpenAI-compatible)."""
    request.state.model = body.model
    await enforce_rate_limit(request, tenant, "completions")
    # TODO(week4-phase-4): dispatch via the backend router.
    raise ModelNotFoundError(f"Model not found: {body.model}")
