# Runbook — model migration

Model file layout and how weights are shared between projects.

## Canonical layout

Models live on a host bind path, default `~/llm-models/` (`LLM_MODELS_DIR`):

```
~/llm-models/
├── T-pro-it-2.1-Q8_0.gguf       # llama.cpp GGUF (chat)
├── T-pro-it-2.1-FP8/            # FP8 variant (GPU)
├── bge-m3/ , bge-reranker-v2-m3/ # checkpoints (pamyat's own use)
└── hf-cache/                    # TEI / HuggingFace download cache
```

The compose stack bind-mounts `~/llm-models` read-only into `tpro-backend`
(the GGUF) and `hf-cache` into the TEI services.

## Initial migration from pamyat-naroda

`scripts/migrate-models-from-pamyat.sh` moves the model directory to
`~/llm-models/` and leaves `~/PAMYAT-NARODA-GRAPH/models` as a **directory
symlink** to it. Directory-level (not per-file) — pamyat bind-mounts the whole
`models/` directory, and Docker resolves a host-side directory symlink when
establishing the bind mount, so pamyat keeps working unchanged.

The script is idempotent. Stop pamyat's containers before running it so nothing
holds the mount during the move.

Reverse it with:

```bash
rm ~/PAMYAT-NARODA-GRAPH/models && mv ~/llm-models ~/PAMYAT-NARODA-GRAPH/models
```

## TEI weights

The TEI services fetch `BAAI/bge-m3` and `BAAI/bge-reranker-v2-m3` into the
shared `hf-cache/` on first run (~4.6 GB total, once). No manual download needed.
