"""Abstract backend adapter interface + per-adapter health state.

Per ADR-0005: every backend kind (openai_compat, tei, tei_rerank, vllm,
anthropic) implements this contract. The router invokes an adapter; the adapter
translates platform-shape calls into backend-specific HTTP calls.

Operations default to "not supported" — a subclass overrides only the
operations its kind actually serves. The router gates on model capabilities
before dispatching, so the defaults are a defensive backstop.

Concrete implementations live next to this file:
    openai_compat.py    — llama.cpp server, generic OpenAI-compatible
    tei.py              — TEI embeddings
    tei_rerank.py       — TEI rerank
    vllm.py             — vLLM (extends openai_compat)
    anthropic.py        — Anthropic native API (stub — Week 5)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from ..exceptions import BackendTimeoutError, BackendUnavailableError, InvalidRequestError
from ..schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from ..schemas.completions import CompletionRequest, CompletionResponse
from ..schemas.embeddings import EmbeddingRequest, EmbeddingResponse
from ..schemas.rerank import RerankRequest, RerankResponse

_HEALTH_TIMEOUT = 5.0


@dataclass(frozen=True)
class BackendModel:
    """A model entry within a backend, as declared in ``backends.yaml``."""

    id: str  # platform-facing model ID, e.g. "t-pro-it-2.1-q8"
    backend_model_name: str  # backend's native name, e.g. "T-pro-it-2.1-Q8_0.gguf"
    capabilities: frozenset[str]  # subset of {chat, completions, embeddings, rerank, structured}


class BackendAdapter(ABC):
    """Abstract base for all backend adapters.

    Subclasses set ``kind`` and ``capabilities`` and override the operations
    their backend serves. Health state is tracked here and updated by the
    background health checker.
    """

    kind: ClassVar[str] = ""
    capabilities: ClassVar[frozenset[str]] = frozenset()

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        timeout_seconds: int = 900,
        api_key: str | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=float(timeout_seconds))
        self._healthy = True  # optimistic until the first health check
        self._consecutive_failures = 0
        self._last_checked: datetime | None = None

    # ─── health state ───────────────────────────────────────────────────────

    @property
    def is_healthy(self) -> bool:
        """Whether the router may dispatch to this backend."""
        return self._healthy

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def last_checked(self) -> datetime | None:
        return self._last_checked

    def record_health(self, ok: bool, *, unhealthy_threshold: int) -> None:
        """Fold one health-probe result into this adapter's state.

        A backend is marked unhealthy only after ``unhealthy_threshold``
        consecutive failures; a single success clears the streak.
        """
        self._last_checked = datetime.now(UTC)
        if ok:
            self._healthy = True
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1
            if self._consecutive_failures >= unhealthy_threshold:
                self._healthy = False

    def supports(self, capability: str) -> bool:
        """Whether this adapter kind serves ``capability``."""
        return capability in self.capabilities

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        """Auth headers for the backend, if it needs an API key."""
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def _request_json(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> Any:
        """Issue an HTTP request to the backend and return the parsed JSON body.

        Maps transport failures to gateway errors: a timeout becomes 504, an
        unreachable host or 5xx becomes 503, a 4xx becomes 400.
        """
        url = f"{self.base_url}{path}"
        try:
            resp = await self._client.request(method, url, json=json, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise BackendTimeoutError(f"{self.name} timed out") from exc
        except httpx.HTTPError as exc:
            raise BackendUnavailableError(f"{self.name} unreachable: {exc}") from exc
        if resp.status_code >= 500:
            raise BackendUnavailableError(f"{self.name} returned HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise InvalidRequestError(
                f"{self.name} rejected the request (HTTP {resp.status_code})", param="model"
            )
        return resp.json()

    # ─── operations (override per kind) ─────────────────────────────────────

    async def chat_completion(
        self, request: ChatCompletionRequest, model: BackendModel
    ) -> ChatCompletionResponse:
        """Forward a chat completion. Default: not supported by this kind."""
        raise InvalidRequestError(
            f"backend kind '{self.kind}' does not support chat", param="model"
        )

    async def completion(
        self, request: CompletionRequest, model: BackendModel
    ) -> CompletionResponse:
        """Forward a legacy text completion. Default: not supported by this kind."""
        raise InvalidRequestError(
            f"backend kind '{self.kind}' does not support completions", param="model"
        )

    async def embedding(
        self, request: EmbeddingRequest, model: BackendModel
    ) -> EmbeddingResponse:
        """Forward an embedding request. Default: not supported by this kind."""
        raise InvalidRequestError(
            f"backend kind '{self.kind}' does not support embeddings", param="model"
        )

    async def rerank(self, request: RerankRequest, model: BackendModel) -> RerankResponse:
        """Forward a rerank request. Default: not supported by this kind."""
        raise InvalidRequestError(
            f"backend kind '{self.kind}' does not support rerank", param="model"
        )

    @abstractmethod
    async def health(self) -> bool:
        """Cheap reachability probe — used by the background health checker."""
