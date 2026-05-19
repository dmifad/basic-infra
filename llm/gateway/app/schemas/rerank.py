"""Rerank schemas — Cohere-style (per ADR-0002).

OpenAI does not have a rerank endpoint; we adopt Cohere's contract since
it is the de-facto standard.

Reference: https://docs.cohere.com/reference/rerank
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ─── Request ───────────────────────────────────────────────────────────────

class RerankRequest(BaseModel):
    model: str
    query: str
    documents: list[str] = Field(min_length=1, max_length=1000)
    top_n: int | None = Field(default=None, ge=1)
    return_documents: bool = False


# ─── Response ──────────────────────────────────────────────────────────────

class RerankedDocument(BaseModel):
    text: str


class RerankResult(BaseModel):
    index: int
    relevance_score: float = Field(ge=0.0, le=1.0)
    document: RerankedDocument | None = None  # populated if return_documents=true


class RerankResponse(BaseModel):
    id: str
    object: Literal["rerank"] = "rerank"
    model: str
    results: list[RerankResult]
