"""Anthropic backend adapter — stub (deferred to Week 5 per the tasklist).

Anthropic's native API differs from OpenAI's; bridging it needs the
request/response translation in ``translate.py``. Registering an anthropic
backend before that lands fails loudly rather than silently.
"""
from __future__ import annotations

from ..exceptions import GatewayError
from ..schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from .base import BackendAdapter, BackendModel


class AnthropicAdapter(BackendAdapter):
    """Anthropic Cloud adapter — not yet implemented (Week 5)."""

    kind = "anthropic"
    capabilities = frozenset({"chat", "structured"})

    async def chat_completion(
        self, request: ChatCompletionRequest, model: BackendModel
    ) -> ChatCompletionResponse:
        raise GatewayError("anthropic backend is not implemented yet (Week 5)")

    async def health(self) -> bool:
        return False
