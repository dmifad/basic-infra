"""SDK response models — a uniform shape across all providers.

Every provider normalizes its backend's response into these, so project code
sees the same objects regardless of ``LLM_PROVIDER``.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    """Result of a chat completion."""

    id: str = ""
    model: str
    choices: list[ChatChoice]
    usage: Usage = Field(default_factory=Usage)

    @property
    def content(self) -> str:
        """Shortcut for the first choice's message content."""
        return self.choices[0].message.content if self.choices else ""


class EmbeddingItem(BaseModel):
    index: int
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    """Result of an embeddings call — vectors aligned with the request inputs."""

    model: str
    data: list[EmbeddingItem]

    @property
    def vectors(self) -> list[list[float]]:
        """All embedding vectors in input order."""
        return [item.embedding for item in sorted(self.data, key=lambda d: d.index)]


class RerankItem(BaseModel):
    index: int
    relevance_score: float
    document: str | None = None


class RerankResponse(BaseModel):
    """Result of a rerank call — items sorted by descending relevance."""

    model: str
    results: list[RerankItem]
