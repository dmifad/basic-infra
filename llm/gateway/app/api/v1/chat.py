"""``POST /v1/chat/completions`` route."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...routing.router import Router
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
    gateway_router: Router = request.app.state.router
    response = await gateway_router.chat_completion(body, tenant)
    request.state.backend = response.metadata.backend
    return response
