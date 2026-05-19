"""``POST /v1/completions`` route — legacy text completions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...routing.router import Router
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
    gateway_router: Router = request.app.state.router
    response = await gateway_router.completion(body, tenant)
    request.state.backend = response.metadata.backend
    return response
