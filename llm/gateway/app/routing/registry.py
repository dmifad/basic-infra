"""Backend registry — loads ``backends.yaml`` and indexes models to adapters.

Per ADR-0005: ``backends.yaml`` is configuration, not code. The registry parses
and validates it (Pydantic), instantiates one adapter per backend, and builds a
``model_id -> (adapter, BackendModel)`` index for the router.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from ..backends.anthropic import AnthropicAdapter
from ..backends.base import BackendAdapter, BackendModel
from ..backends.openai_compat import OpenAICompatAdapter
from ..backends.tei import TeiEmbeddingAdapter
from ..backends.tei_rerank import TeiRerankAdapter
from ..backends.vllm import VllmAdapter
from ..exceptions import ModelNotFoundError
from ..observability.logging import get_logger
from ..schemas.models import Capability, Model
from ..tenancy.store import TenantRecord

_log = get_logger("registry")

_ADAPTER_KINDS: dict[str, type[BackendAdapter]] = {
    "openai_compat": OpenAICompatAdapter,
    "vllm": VllmAdapter,
    "tei": TeiEmbeddingAdapter,
    "tei_rerank": TeiRerankAdapter,
    "anthropic": AnthropicAdapter,
}


# ─── backends.yaml schema ────────────────────────────────────────────────────


class ModelConfig(BaseModel):
    """One model entry under a backend in ``backends.yaml``."""

    id: str
    backend_model_name: str
    capabilities: list[Capability]
    notes: str | None = None


class BackendConfig(BaseModel):
    """One backend entry in ``backends.yaml``."""

    name: str
    kind: str
    base_url: str
    # Per-backend upstream read budget (seconds). When omitted, the backend
    # inherits the global default (config.backend_request_timeout_seconds).
    timeout_seconds: int | None = None
    api_key_env: str | None = None
    models: list[ModelConfig] = Field(min_length=1)


class BackendsConfig(BaseModel):
    """Top-level shape of ``backends.yaml``."""

    backends: list[BackendConfig]


class RegistryError(Exception):
    """``backends.yaml`` is invalid or references an unknown adapter kind."""


class Registry:
    """In-memory index from model id to the adapter that serves it."""

    def __init__(self) -> None:
        self._adapters: list[BackendAdapter] = []
        self._by_model: dict[str, tuple[BackendAdapter, BackendModel]] = {}
        self._model_meta: dict[str, ModelConfig] = {}

    @classmethod
    def load(cls, path: Path, *, request_timeout_seconds: float = 900.0) -> Registry:
        """Load a registry from a ``backends.yaml`` file.

        A missing file yields an empty registry (the gateway still boots, with
        no models). A present-but-invalid file raises :class:`RegistryError`.

        ``request_timeout_seconds`` is the **default** upstream HTTP read budget
        (``config.backend_request_timeout_seconds``); a backend overrides it with
        its own ``timeout_seconds`` in backends.yaml. connect/pool/write budgets
        are short and fixed in the adapter.
        """
        registry = cls()
        if not path.exists():
            _log.warning("backends_config_missing", path=str(path))
            return registry
        try:
            raw = yaml.safe_load(path.read_text()) or {}
            config = BackendsConfig.model_validate(raw)
        except (yaml.YAMLError, ValidationError) as exc:
            raise RegistryError(f"invalid backends config {path}: {exc}") from exc
        registry._build(config, request_timeout_seconds=request_timeout_seconds)
        return registry

    @classmethod
    def from_config(
        cls, config: BackendsConfig, *, request_timeout_seconds: float = 900.0
    ) -> Registry:
        """Build a registry directly from a validated config (used in tests)."""
        registry = cls()
        registry._build(config, request_timeout_seconds=request_timeout_seconds)
        return registry

    def _build(
        self, config: BackendsConfig, *, request_timeout_seconds: float = 900.0
    ) -> None:
        for backend in config.backends:
            adapter_cls = _ADAPTER_KINDS.get(backend.kind)
            if adapter_cls is None:
                raise RegistryError(
                    f"backend '{backend.name}': unknown kind '{backend.kind}'"
                )
            api_key = os.getenv(backend.api_key_env) if backend.api_key_env else None
            adapter = adapter_cls(
                name=backend.name,
                base_url=backend.base_url,
                # Per-backend read budget if set in backends.yaml, else the
                # global default (config.backend_request_timeout_seconds).
                read_timeout_seconds=(
                    float(backend.timeout_seconds)
                    if backend.timeout_seconds is not None
                    else request_timeout_seconds
                ),
                api_key=api_key,
            )
            self._adapters.append(adapter)
            for model_cfg in backend.models:
                if model_cfg.id in self._by_model:
                    raise RegistryError(f"duplicate model id: {model_cfg.id}")
                self._by_model[model_cfg.id] = (
                    adapter,
                    BackendModel(
                        id=model_cfg.id,
                        backend_model_name=model_cfg.backend_model_name,
                        capabilities=frozenset(model_cfg.capabilities),
                    ),
                )
                self._model_meta[model_cfg.id] = model_cfg
        _log.info(
            "registry_loaded", backends=len(self._adapters), models=len(self._by_model)
        )

    @property
    def adapters(self) -> list[BackendAdapter]:
        """All registered adapters (one per backend)."""
        return list(self._adapters)

    def get_backend_for(self, model_id: str) -> tuple[BackendAdapter, BackendModel]:
        """Resolve a model id to its adapter and backend model.

        Raises:
            ModelNotFoundError: the model id is not registered.
        """
        entry = self._by_model.get(model_id)
        if entry is None:
            raise ModelNotFoundError(f"Model not found: {model_id}")
        return entry

    def models_for(self, tenant: TenantRecord) -> list[Model]:
        """Return the models visible to ``tenant``, filtered by ``allowed_models``."""
        wildcard = "*" in tenant.allowed_models
        models: list[Model] = []
        for model_id, (adapter, _backend_model) in self._by_model.items():
            if not wildcard and model_id not in tenant.allowed_models:
                continue
            meta = self._model_meta[model_id]
            models.append(
                Model(id=model_id, owned_by=adapter.name, capabilities=meta.capabilities)
            )
        return models

    async def aclose(self) -> None:
        """Close every adapter's HTTP client."""
        for adapter in self._adapters:
            await adapter.aclose()
