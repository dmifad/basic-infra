"""Legacy text-completion schemas — OpenAI-compatible (subset).

Kept for older clients; new code should use chat completions. See ADR-0002.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .chat import ChatCompletionUsage, GatewayMetadata


class CompletionRequest(BaseModel):
    """Request body for ``POST /v1/completions``."""

    model: str
    prompt: str | list[str]
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
    stop: list[str] | str | None = None
    seed: int | None = None
    n: int = Field(default=1, ge=1, le=1)  # only n=1 supported in v1


class CompletionChoice(BaseModel):
    index: int
    text: str
    finish_reason: Literal["stop", "length", "content_filter"] | None


class CompletionResponse(BaseModel):
    """Response body for ``POST /v1/completions``."""

    id: str
    object: Literal["text_completion"] = "text_completion"
    created: int  # unix timestamp
    model: str
    choices: list[CompletionChoice]
    usage: ChatCompletionUsage
    metadata: GatewayMetadata
