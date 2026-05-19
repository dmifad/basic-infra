"""Model-listing schemas — OpenAI-compatible plus a ``capabilities`` extension.

Reference: docs/api/openapi.yaml (schemas Model, ModelList).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Capability = Literal["chat", "completions", "embeddings", "rerank", "structured"]


class Model(BaseModel):
    """A single model entry returned by ``GET /v1/models``."""

    id: str
    object: Literal["model"] = "model"
    created: int | None = None
    owned_by: str
    capabilities: list[Capability] = Field(default_factory=list)


class ModelList(BaseModel):
    """Response body for ``GET /v1/models``."""

    object: Literal["list"] = "list"
    data: list[Model]
