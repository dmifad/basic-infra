"""vLLM backend adapter.

vLLM speaks the OpenAI API plus a ``guided_json`` extension for structured
output. Until a vLLM backend is actually deployed, this adapter reuses the
OpenAI-compatible behaviour unchanged; the ``guided_json`` translation is a
later refinement (ADR-0005).
"""
from __future__ import annotations

from .openai_compat import OpenAICompatAdapter


class VllmAdapter(OpenAICompatAdapter):
    """vLLM adapter — currently identical to OpenAI-compatible behaviour."""

    kind = "vllm"
    # TODO(week4-review): translate response_format -> guided_json once a vLLM
    # backend is available to validate against.
