"""TEI (Text Embeddings Inference) embedding adapter.

Translates the OpenAI embeddings shape to TEI's ``/embed`` endpoint: TEI takes
``{"inputs": [...]}`` and returns a list of float vectors. TEI does not report
token usage, so it is estimated.
"""
from __future__ import annotations

import httpx

from ..exceptions import GatewayError
from ..schemas.embeddings import (
    EmbeddingData,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingUsage,
)
from .base import BackendAdapter, BackendModel

_HEALTH_TIMEOUT = 5.0
_CHARS_PER_TOKEN = 4  # rough estimate — TEI /embed returns no usage counts


class TeiEmbeddingAdapter(BackendAdapter):
    """Adapter for a TEI server serving an embedding model."""

    kind = "tei"
    capabilities = frozenset({"embeddings"})

    async def embedding(
        self, request: EmbeddingRequest, model: BackendModel
    ) -> EmbeddingResponse:
        inputs = [request.input] if isinstance(request.input, str) else list(request.input)
        data = await self._request_json("POST", "/embed", json={"inputs": inputs})
        if not isinstance(data, list):
            raise GatewayError(f"{self.name} returned an unexpected /embed payload")
        vectors: list[EmbeddingData] = []
        for index, vector in enumerate(data):
            if not isinstance(vector, list):
                raise GatewayError(f"{self.name} returned a non-vector embedding")
            vectors.append(
                EmbeddingData(index=index, embedding=[float(x) for x in vector])
            )
        tokens = sum(len(text) for text in inputs) // _CHARS_PER_TOKEN
        return EmbeddingResponse(
            data=vectors,
            model=request.model,
            usage=EmbeddingUsage(prompt_tokens=tokens, total_tokens=tokens),
        )

    async def health(self) -> bool:
        """Probe TEI's ``/health`` endpoint."""
        try:
            resp = await self._client.get(
                f"{self.base_url}/health", timeout=_HEALTH_TIMEOUT
            )
        except httpx.HTTPError:
            return False
        return resp.status_code == 200
