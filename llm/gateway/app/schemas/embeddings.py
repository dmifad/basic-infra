"""Embedding schemas — OpenAI-compatible.

Reference: docs/api/openapi.yaml (schemas Embedding*).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class EmbeddingRequest(BaseModel):
    """Request body for ``POST /v1/embeddings``."""

    model: str
    input: str | list[str]
    dimensions: int | None = Field(default=None, ge=1)

    @field_validator("input")
    @classmethod
    def _reject_empty(cls, value: str | list[str]) -> str | list[str]:
        """An empty input array yields no embeddings — reject it up front."""
        if isinstance(value, list) and len(value) == 0:
            raise ValueError("input must contain at least one string")
        return value


class EmbeddingData(BaseModel):
    """One embedding vector, positionally aligned with the request input."""

    object: Literal["embedding"] = "embedding"
    index: int
    embedding: list[float]


class EmbeddingUsage(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    """Response body for ``POST /v1/embeddings``."""

    object: Literal["list"] = "list"
    data: list[EmbeddingData]
    model: str
    usage: EmbeddingUsage
