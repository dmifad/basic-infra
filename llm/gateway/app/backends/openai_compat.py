"""OpenAI-compatible backend adapter — llama.cpp server and generic OpenAI-compat.

Per ADR-0005: llama.cpp's server speaks the OpenAI API, so this adapter is
mostly a pass-through. It swaps the platform model id for the backend's native
model name and forwards the payload; ``response_format`` rides through verbatim
(llama.cpp honours ``json_object`` and ``json_schema``).
"""
from __future__ import annotations

from typing import Any, TypeVar

import httpx
from pydantic import ValidationError

from ..exceptions import GatewayError
from ..schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from ..schemas.completions import CompletionRequest, CompletionResponse
from .base import BackendAdapter, BackendModel

_HEALTH_TIMEOUT = 5.0

_Response = TypeVar("_Response", ChatCompletionResponse, CompletionResponse)


class OpenAICompatAdapter(BackendAdapter):
    """Adapter for backends that already speak the OpenAI chat/completions API."""

    kind = "openai_compat"
    capabilities = frozenset({"chat", "completions", "structured"})

    async def chat_completion(
        self, request: ChatCompletionRequest, model: BackendModel
    ) -> ChatCompletionResponse:
        payload = request.model_dump(by_alias=True, exclude_none=True)
        payload["model"] = model.backend_model_name
        data = await self._request_json("POST", "/chat/completions", json=payload)
        return self._finalize(ChatCompletionResponse, data, request.model)

    async def completion(
        self, request: CompletionRequest, model: BackendModel
    ) -> CompletionResponse:
        payload = request.model_dump(by_alias=True, exclude_none=True)
        payload["model"] = model.backend_model_name
        data = await self._request_json("POST", "/completions", json=payload)
        return self._finalize(CompletionResponse, data, request.model)

    async def health(self) -> bool:
        """Probe ``GET /models`` — cheap and present on every OpenAI-compat server."""
        try:
            resp = await self._client.get(
                f"{self.base_url}/models", headers=self._headers(), timeout=_HEALTH_TIMEOUT
            )
        except httpx.HTTPError:
            return False
        return resp.status_code == 200

    def _finalize(
        self, model_cls: type[_Response], data: Any, platform_model_id: str
    ) -> _Response:
        """Attach gateway metadata and the platform model id, then validate."""
        if not isinstance(data, dict):
            raise GatewayError(f"{self.name} returned a non-object response")
        data["model"] = platform_model_id
        data["metadata"] = {"backend": self.name, "response_format_fallback": False}
        try:
            return model_cls.model_validate(data)
        except ValidationError as exc:
            raise GatewayError(f"{self.name} returned an unparseable response: {exc}") from exc
