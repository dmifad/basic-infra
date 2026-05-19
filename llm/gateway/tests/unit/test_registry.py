"""Unit tests — backend registry loading, validation and tenant filtering."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.exceptions import ModelNotFoundError
from app.routing.registry import Registry, RegistryError
from app.tenancy.store import TenantRecord

_VALID_YAML = """
backends:
  - name: llama-cpp-tpro
    kind: openai_compat
    base_url: http://tpro:8080/v1
    models:
      - id: t-pro-it-2.1-q8
        backend_model_name: T-pro.gguf
        capabilities: [chat, completions, structured]
  - name: tei-embed
    kind: tei
    base_url: http://tei:80
    models:
      - id: bge-m3
        backend_model_name: BAAI/bge-m3
        capabilities: [embeddings]
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "backends.yaml"
    path.write_text(text)
    return path


def test_load_valid_config(tmp_path: Path) -> None:
    registry = Registry.load(_write(tmp_path, _VALID_YAML))
    assert len(registry.adapters) == 2
    adapter, model = registry.get_backend_for("t-pro-it-2.1-q8")
    assert adapter.kind == "openai_compat"
    assert model.backend_model_name == "T-pro.gguf"
    assert "chat" in model.capabilities


def test_missing_file_yields_empty_registry(tmp_path: Path) -> None:
    registry = Registry.load(tmp_path / "absent.yaml")
    assert registry.adapters == []


def test_unknown_model_raises(tmp_path: Path) -> None:
    registry = Registry.load(_write(tmp_path, _VALID_YAML))
    with pytest.raises(ModelNotFoundError):
        registry.get_backend_for("ghost-model")


def test_unknown_kind_rejected(tmp_path: Path) -> None:
    bad = _VALID_YAML.replace("kind: tei", "kind: nonsense")
    with pytest.raises(RegistryError):
        Registry.load(_write(tmp_path, bad))


def test_duplicate_model_id_rejected(tmp_path: Path) -> None:
    dupe = _VALID_YAML + """
  - name: dupe-backend
    kind: openai_compat
    base_url: http://x:8080/v1
    models:
      - id: t-pro-it-2.1-q8
        backend_model_name: other.gguf
        capabilities: [chat]
"""
    with pytest.raises(RegistryError):
        Registry.load(_write(tmp_path, dupe))


def test_models_for_filters_by_allowed_models(tmp_path: Path) -> None:
    registry = Registry.load(_write(tmp_path, _VALID_YAML))
    wildcard = TenantRecord(id="t", display_name="T", allowed_models=("*",))
    assert {m.id for m in registry.models_for(wildcard)} == {"t-pro-it-2.1-q8", "bge-m3"}
    limited = TenantRecord(id="t2", display_name="T2", allowed_models=("bge-m3",))
    assert {m.id for m in registry.models_for(limited)} == {"bge-m3"}
