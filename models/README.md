# models/

This directory is a **placeholder**. Model weights do **not** live in the repo.

Models live on a host bind path, default `~/llm-models/` (configurable via
`LLM_MODELS_DIR` in `.env`). Both `basic-infra` and `pamyat-naroda` bind-mount
that path into their backend containers.

Expected host layout:

```
~/llm-models/
├── T-pro-it-2.1-Q8_0.gguf       # ~7 GB — llama.cpp GGUF
├── bge-m3/                       # TEI embedding checkpoint
├── bge-reranker-v2-m3/           # TEI rerank checkpoint
└── hf-cache/                     # HuggingFace / TEI download cache
```

Populate it with `scripts/migrate-models-from-pamyat.sh` (Phase 2) or by
downloading directly. See `docs/runbooks/model-migration.md`.

Everything in this directory except this README is gitignored.
