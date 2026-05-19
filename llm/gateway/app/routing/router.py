"""Request router — dispatches a model request to its backend adapter.

Per ADR-0005, the router is the single choke point between the HTTP layer and
the backends. For every request it: resolves the model, checks the tenant is
permitted, checks the model supports the capability, checks the backend is
healthy — then forwards to the adapter.
"""
from __future__ import annotations

from ..backends.base import BackendAdapter, BackendModel
from ..exceptions import BackendUnavailableError, ForbiddenError, InvalidRequestError
from ..schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from ..schemas.completions import CompletionRequest, CompletionResponse
from ..schemas.embeddings import EmbeddingRequest, EmbeddingResponse
from ..schemas.rerank import RerankRequest, RerankResponse
from ..tenancy.store import TenantRecord
from .registry import Registry


class Router:
    """Dispatches platform requests to backend adapters via the registry."""

    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    async def chat_completion(
        self, request: ChatCompletionRequest, tenant: TenantRecord
    ) -> ChatCompletionResponse:
        adapter, model = self._resolve(request.model, tenant, "chat")
        return await adapter.chat_completion(request, model)

    async def completion(
        self, request: CompletionRequest, tenant: TenantRecord
    ) -> CompletionResponse:
        adapter, model = self._resolve(request.model, tenant, "completions")
        return await adapter.completion(request, model)

    async def embedding(
        self, request: EmbeddingRequest, tenant: TenantRecord
    ) -> EmbeddingResponse:
        adapter, model = self._resolve(request.model, tenant, "embeddings")
        return await adapter.embedding(request, model)

    async def rerank(self, request: RerankRequest, tenant: TenantRecord) -> RerankResponse:
        adapter, model = self._resolve(request.model, tenant, "rerank")
        return await adapter.rerank(request, model)

    def _resolve(
        self, model_id: str, tenant: TenantRecord, capability: str
    ) -> tuple[BackendAdapter, BackendModel]:
        """Resolve and authorize a model request.

        Raises:
            ModelNotFoundError: model id is not registered (404).
            ForbiddenError: tenant is not permitted to use the model (403).
            InvalidRequestError: model does not support the capability (400).
            BackendUnavailableError: the model's backend is unhealthy (503).
        """
        adapter, model = self._registry.get_backend_for(model_id)
        if "*" not in tenant.allowed_models and model_id not in tenant.allowed_models:
            raise ForbiddenError(
                f"tenant '{tenant.id}' is not permitted to use model '{model_id}'",
                param="model",
            )
        if capability not in model.capabilities:
            raise InvalidRequestError(
                f"model '{model_id}' does not support {capability}", param="model"
            )
        if not adapter.is_healthy:
            raise BackendUnavailableError(f"backend '{adapter.name}' is unhealthy")
        return adapter, model
