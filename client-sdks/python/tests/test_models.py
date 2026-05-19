"""Unit tests — SDK response models."""
from __future__ import annotations

from vams_llm_client.models import (
    ChatChoice,
    ChatMessage,
    ChatResponse,
    EmbeddingItem,
    EmbeddingResponse,
)


def test_chat_response_content_shortcut() -> None:
    resp = ChatResponse(
        model="m",
        choices=[ChatChoice(index=0, message=ChatMessage(role="assistant", content="hi"))],
    )
    assert resp.content == "hi"


def test_chat_response_content_empty_without_choices() -> None:
    assert ChatResponse(model="m", choices=[]).content == ""


def test_embedding_vectors_returned_in_index_order() -> None:
    resp = EmbeddingResponse(
        model="m",
        data=[
            EmbeddingItem(index=1, embedding=[0.2]),
            EmbeddingItem(index=0, embedding=[0.1]),
        ],
    )
    assert resp.vectors == [[0.1], [0.2]]
