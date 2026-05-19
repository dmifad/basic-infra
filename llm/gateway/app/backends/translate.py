"""OpenAI <-> Anthropic request/response translation — stub (Week 5).

Per ADR-0005 an anthropic backend needs OpenAI-shaped requests rewritten to
Anthropic's native Messages API and the responses rewritten back. This lands in
Week 5 alongside the anthropic adapter.
"""
from __future__ import annotations

from typing import Any

from ..schemas.chat import ChatCompletionRequest


def openai_to_anthropic(request: ChatCompletionRequest) -> dict[str, Any]:
    """Translate an OpenAI chat request into Anthropic's Messages API shape."""
    raise NotImplementedError("week5: OpenAI -> Anthropic translation")
