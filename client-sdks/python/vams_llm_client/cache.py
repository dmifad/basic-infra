"""Opt-in SQLite embedding cache (ADR-0004).

Keyed by ``(provider, model, sha256(text))``. Off by default; enabled when
``LLM_CACHE_DIR`` is set and ``client.embeddings.cache_enabled = True``.
Embeddings are the cache-friendly endpoint — the same text always embeds the
same way for a given model.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


class EmbeddingCache:
    """SQLite-backed cache of embedding vectors."""

    def __init__(self, cache_dir: str) -> None:
        directory = Path(cache_dir).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(directory / "embeddings.sqlite"), check_same_thread=False
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector TEXT NOT NULL)"
        )
        self._conn.commit()

    @staticmethod
    def _key(provider: str, model: str, text: str) -> str:
        digest = hashlib.sha256(f"{provider}\x00{model}\x00{text}".encode())
        return digest.hexdigest()

    def get(self, provider: str, model: str, text: str) -> list[float] | None:
        """Return the cached vector for ``text``, or ``None`` on a miss."""
        row = self._conn.execute(
            "SELECT vector FROM embeddings WHERE key = ?",
            (self._key(provider, model, text),),
        ).fetchone()
        if row is None:
            return None
        vector: list[float] = json.loads(row[0])
        return vector

    def put(self, provider: str, model: str, text: str, vector: list[float]) -> None:
        """Store ``vector`` as the embedding of ``text``."""
        self._conn.execute(
            "INSERT OR REPLACE INTO embeddings (key, vector) VALUES (?, ?)",
            (self._key(provider, model, text), json.dumps(vector)),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the cache database."""
        self._conn.close()
