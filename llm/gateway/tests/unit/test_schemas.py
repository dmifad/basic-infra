"""Unit tests — Pydantic schema validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatCompletionRequest, JsonObjectFormat, JsonSchemaFormat
from app.schemas.embeddings import EmbeddingRequest
from app.schemas.errors import ErrorDetail, ErrorEnvelope
from app.schemas.rerank import RerankRequest


def test_chat_request_minimal_valid() -> None:
    req = ChatCompletionRequest.model_validate(
        {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    )
    assert req.temperature == 0.1
    assert req.n == 1


def test_chat_request_rejects_n_above_one() -> None:
    with pytest.raises(ValidationError):
        ChatCompletionRequest.model_validate(
            {"model": "m", "messages": [{"role": "user", "content": "hi"}], "n": 2}
        )


def test_chat_request_rejects_out_of_range_temperature() -> None:
    with pytest.raises(ValidationError):
        ChatCompletionRequest.model_validate(
            {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 5}
        )


def test_response_format_json_schema_uses_schema_alias() -> None:
    fmt = JsonSchemaFormat.model_validate(
        {
            "type": "json_schema",
            "json_schema": {"name": "out", "schema": {"type": "object"}},
        }
    )
    assert fmt.json_schema.json_schema_def == {"type": "object"}
    # The wire name round-trips back to `schema`.
    assert fmt.model_dump(by_alias=True)["json_schema"]["schema"] == {"type": "object"}


def test_chat_request_accepts_response_format() -> None:
    req = ChatCompletionRequest.model_validate(
        {
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": {"type": "json_object"},
        }
    )
    assert isinstance(req.response_format, JsonObjectFormat)


def test_embedding_request_rejects_empty_input_list() -> None:
    with pytest.raises(ValidationError):
        EmbeddingRequest.model_validate({"model": "bge-m3", "input": []})


def test_embedding_request_accepts_string_and_list() -> None:
    assert EmbeddingRequest.model_validate({"model": "bge-m3", "input": "x"}).input == "x"
    assert EmbeddingRequest.model_validate(
        {"model": "bge-m3", "input": ["a", "b"]}
    ).input == ["a", "b"]


def test_rerank_request_rejects_empty_documents() -> None:
    with pytest.raises(ValidationError):
        RerankRequest.model_validate({"model": "r", "query": "q", "documents": []})


def test_error_envelope_shape() -> None:
    env = ErrorEnvelope(error=ErrorDetail(message="boom", type="api_error"))
    dumped = env.model_dump()
    assert dumped == {"error": {"message": "boom", "type": "api_error", "code": None, "param": None}}
