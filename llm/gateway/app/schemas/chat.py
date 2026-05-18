"""Chat completion schemas — OpenAI-compatible (subset).

Reference: https://platform.openai.com/docs/api-reference/chat
Spec: docs/api/openapi.yaml (after Phase 1)
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ─── Messages ──────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str
    name: str | None = None


# ─── Response format (structured output) ───────────────────────────────────

class JsonSchemaSpec(BaseModel):
    name: str
    schema: dict[str, Any]
    strict: bool = True
    description: str | None = None


class JsonObjectFormat(BaseModel):
    type: Literal["json_object"]


class JsonSchemaFormat(BaseModel):
    type: Literal["json_schema"]
    json_schema: JsonSchemaSpec


class TextFormat(BaseModel):
    type: Literal["text"] = "text"


ResponseFormat = JsonObjectFormat | JsonSchemaFormat | TextFormat


# ─── Request ───────────────────────────────────────────────────────────────

class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
    stop: list[str] | str | None = None
    seed: int | None = None
    n: int = Field(default=1, ge=1, le=1)  # only n=1 supported in v1
    response_format: ResponseFormat | None = None
    # `stream` not supported in v1 — see ADR-0002


# ─── Response ──────────────────────────────────────────────────────────────

class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: Literal["stop", "length", "content_filter", "tool_calls"] | None


class GatewayMetadata(BaseModel):
    """Vendor extension — not part of OpenAI spec.

    Clients that use openai-python SDK can read this via extra fields.
    """
    backend: str
    response_format_fallback: bool = False
    tenant_id: str | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int  # unix timestamp
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage
    metadata: GatewayMetadata
