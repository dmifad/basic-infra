"""``POST /v1/chat/completions`` route.

Phase 3 wires auth, rate limiting and request validation. Backend dispatch is
added in Phase 4 when the router lands; until then no model resolves.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...exceptions import ModelNotFoundError
from ...schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from ...tenancy.store import TenantRecord
from ..deps import current_tenant, enforce_rate_limit

router = APIRouter(tags=["chat"])


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    body: ChatCompletionRequest,
    request: Request,
    tenant: TenantRecord = Depends(current_tenant),
) -> ChatCompletionResponse:
    """Create a chat completion (OpenAI-compatible)."""
    request.state.model = body.model
    await enforce_rate_limit(request, tenant, "chat.completions")
    # TODO(week4-phase-4): resolve body.model via the backend registry and
    # dispatch through the router. No models are registered until then.
    raise ModelNotFoundError(f"Model not found: {body.model}")
