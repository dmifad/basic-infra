"""TEI rerank adapter.

Translates the Cohere-style rerank request (ADR-0002) to TEI's ``/rerank``
endpoint: TEI takes ``{"query", "texts", "return_text"}`` and returns
``[{"index", "score", "text"?}, ...]``.
"""
from __future__ import annotations

import secrets

import httpx

from ..exceptions import GatewayError
from ..schemas.rerank import RerankedDocument, RerankRequest, RerankResponse, RerankResult
from .base import BackendAdapter, BackendModel

_HEALTH_TIMEOUT = 5.0


def _clamp_unit(score: float) -> float:
    """Clamp a relevance score into [0, 1] — the contract's bound."""
    return max(0.0, min(1.0, score))


class TeiRerankAdapter(BackendAdapter):
    """Adapter for a TEI server serving a cross-encoder rerank model."""

    kind = "tei_rerank"
    capabilities = frozenset({"rerank"})

    async def rerank(self, request: RerankRequest, model: BackendModel) -> RerankResponse:
        payload = {
            "query": request.query,
            "texts": list(request.documents),
            "return_text": request.return_documents,
        }
        data = await self._request_json("POST", "/rerank", json=payload)
        if not isinstance(data, list):
            raise GatewayError(f"{self.name} returned an unexpected /rerank payload")

        results: list[RerankResult] = []
        for item in data:
            if not isinstance(item, dict):
                raise GatewayError(f"{self.name} returned a malformed rerank result")
            document = None
            if request.return_documents and item.get("text") is not None:
                document = RerankedDocument(text=str(item["text"]))
            results.append(
                RerankResult(
                    index=int(item["index"]),
                    relevance_score=_clamp_unit(float(item["score"])),
                    document=document,
                )
            )
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        if request.top_n is not None:
            results = results[: request.top_n]
        return RerankResponse(
            id=f"rerank_{secrets.token_hex(8)}", model=request.model, results=results
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
