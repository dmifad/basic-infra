"""Общие фикстуры для тестов хранилища."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from storage.adapters.filesystem import FilesystemAdapter


@pytest.fixture
def filesystem_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def filesystem_adapter(filesystem_root: Path) -> FilesystemAdapter:
    return FilesystemAdapter(filesystem_root=filesystem_root)


@pytest_asyncio.fixture
async def sample_tenant() -> str:
    return "telcoss"
