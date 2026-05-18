#!/usr/bin/env bash
# Migrate the LLM model directory from pamyat-naroda-graph to a shared host path.
# Idempotent — safe to re-run.
#
# Strategy: DIRECTORY-LEVEL symlink.
#
#   Before: ~/PAMYAT-NARODA-GRAPH/models/        (real directory)
#   After:  ~/llm-models/                        (real directory — canonical shared path)
#           ~/PAMYAT-NARODA-GRAPH/models  ->  ~/llm-models   (symlink)
#
# Why directory-level, not per-file:
#   pamyat-naroda bind-mounts the WHOLE ./models directory into its containers
#   (reranker, retrieval, tpro-backend). A per-file symlink inside that mount
#   would point at a host path that does not exist inside the container —
#   a dangling symlink. A host-side DIRECTORY symlink, by contrast, is resolved
#   by Docker when the bind mount is established, so pamyat keeps working with
#   zero compose changes.
#
# Reversible:
#   rm ~/PAMYAT-NARODA-GRAPH/models && mv ~/llm-models ~/PAMYAT-NARODA-GRAPH/models
#
# Safety: stop pamyat's containers before running so nothing holds the mount.
#   cd ~/PAMYAT-NARODA-GRAPH && docker compose stop

set -euo pipefail

SRC="${PAMYAT_MODELS_DIR:-${HOME}/PAMYAT-NARODA-GRAPH/models}"
DST="${LLM_MODELS_DIR:-${HOME}/llm-models}"

echo "=== Model migration: $SRC -> $DST ==="

# ─── Case 1: already migrated (SRC is a symlink) ────────────────────────────
if [[ -L "$SRC" ]]; then
    target="$(readlink -f "$SRC")"
    if [[ "$target" == "$(readlink -f "$DST" 2>/dev/null || echo "$DST")" ]]; then
        echo "  [-] already migrated: $SRC -> $target"
        exit 0
    fi
    echo "  ERROR: $SRC is a symlink to $target, not $DST — resolve manually."
    exit 1
fi

# ─── Case 2: SRC absent ─────────────────────────────────────────────────────
if [[ ! -e "$SRC" ]]; then
    if [[ -d "$DST" ]]; then
        echo "  [-] $SRC absent and $DST exists — nothing to do."
        exit 0
    fi
    echo "  ERROR: neither $SRC nor $DST exists."
    exit 1
fi

# ─── Case 3: SRC is a real directory — migrate ──────────────────────────────
if [[ ! -d "$SRC" ]]; then
    echo "  ERROR: $SRC exists but is not a directory."
    exit 1
fi
if [[ -e "$DST" ]]; then
    echo "  ERROR: $DST already exists — refusing to overwrite. Resolve manually."
    exit 1
fi

echo "  [+] moving directory (rename on same filesystem — fast, no copy)..."
mv "$SRC" "$DST"
ln -s "$DST" "$SRC"
echo "  [✓] migrated: $SRC -> $(readlink "$SRC")"
echo
echo "Contents now at $DST:"
ls -la "$DST"
echo
echo "Verify pamyat-naroda still starts:"
echo "  cd ~/PAMYAT-NARODA-GRAPH && docker compose up -d"
echo "  docker compose logs --tail 20 reranker llm-gateway retrieval"
