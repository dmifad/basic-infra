# Runbook — model migration

> **Status:** stub. The migration mechanism is delivered in Phase 2.

How LLM model files are laid out and moved between projects.

Reference: `docs/specs/llm-platform-spec.md` § "Models — file system layout".

## Canonical layout

Models live under a host bind path, default `~/llm-models/`:

```
~/llm-models/
├── T-pro-it-2.1-Q8_0.gguf
├── bge-m3/
├── bge-reranker-v2-m3/
└── hf-cache/
```

Both `basic-infra` and (after Phase 6) `pamyat-naroda` bind-mount this path.

## Initial migration from pamyat-naroda

Run `scripts/migrate-models-from-pamyat.sh`. It moves model files to
`~/llm-models/` and leaves symlinks in the old `~/PAMYAT-NARODA-GRAPH/models/`
location so pamyat keeps working until it migrates in Phase 6.

The script is idempotent — safe to re-run.

_TODO(week4-phase-8): rollback procedure, disk-space checks, GPU/CPU model variants._
