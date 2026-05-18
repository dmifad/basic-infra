#!/usr/bin/env bash
# Migrate LLM models from pamyat-naroda-graph to shared host path.
# Idempotent — safe to re-run.
#
# Before: ~/PAMYAT-NARODA-GRAPH/models/T-pro-it-2.1-Q8_0.gguf
# After:  ~/llm-models/T-pro-it-2.1-Q8_0.gguf  (real file)
#         ~/PAMYAT-NARODA-GRAPH/models/T-pro-it-2.1-Q8_0.gguf  (symlink → real)
#
# Pamyat continues to work via symlink. basic-infra mounts ~/llm-models directly.
# When pamyat-naroda migrates to basic-infra in Phase 6, symlinks can be removed.

set -euo pipefail

SRC="${HOME}/PAMYAT-NARODA-GRAPH/models"
DST="${HOME}/llm-models"

if [[ ! -d "$SRC" ]]; then
    echo "ERROR: source $SRC does not exist"
    exit 1
fi

mkdir -p "$DST"

migrate_file() {
    local name="$1"
    local src_path="$SRC/$name"
    local dst_path="$DST/$name"

    if [[ -L "$src_path" ]]; then
        echo "  [-] $name: already a symlink, skipping"
        return
    fi

    if [[ ! -e "$src_path" ]]; then
        echo "  [-] $name: not present in source, skipping"
        return
    fi

    if [[ -e "$dst_path" ]]; then
        echo "  [-] $name: already at destination, removing source and symlinking"
        rm "$src_path"
    else
        echo "  [+] $name: moving to $DST"
        mv "$src_path" "$dst_path"
    fi

    ln -s "$dst_path" "$src_path"
    echo "  [✓] $name: symlinked $src_path → $dst_path"
}

migrate_dir() {
    local name="$1"
    local src_path="$SRC/$name"
    local dst_path="$DST/$name"

    if [[ -L "$src_path" ]]; then
        echo "  [-] $name/: already a symlink, skipping"
        return
    fi

    if [[ ! -d "$src_path" ]]; then
        echo "  [-] $name/: not present in source, skipping"
        return
    fi

    if [[ -e "$dst_path" ]]; then
        echo "  [-] $name/: already at destination, removing source and symlinking"
        rm -rf "$src_path"
    else
        echo "  [+] $name/: moving to $DST"
        mv "$src_path" "$dst_path"
    fi

    ln -s "$dst_path" "$src_path"
    echo "  [✓] $name/: symlinked $src_path → $dst_path"
}

echo "=== Migrating models from $SRC to $DST ==="
echo

echo "T-pro GGUF:"
migrate_file "T-pro-it-2.1-Q8_0.gguf"
echo

echo "BGE-M3 (if present):"
migrate_dir "bge-m3"
echo

echo "BGE Reranker v2 m3 (if present):"
migrate_dir "bge-reranker-v2-m3"
echo

echo "HF cache:"
mkdir -p "$DST/hf-cache"
if [[ -d "$SRC/hf-cache" ]] && [[ ! -L "$SRC/hf-cache" ]]; then
    echo "  [+] hf-cache: merging contents"
    cp -an "$SRC/hf-cache/." "$DST/hf-cache/" || true
    rm -rf "$SRC/hf-cache"
    ln -s "$DST/hf-cache" "$SRC/hf-cache"
    echo "  [✓] hf-cache: symlinked"
else
    ln -sfn "$DST/hf-cache" "$SRC/hf-cache" 2>/dev/null || true
    echo "  [-] hf-cache: already linked or absent"
fi
echo

echo "=== Migration complete. ==="
echo
echo "Verify pamyat-naroda still starts:"
echo "  cd ~/PAMYAT-NARODA-GRAPH"
echo "  docker compose restart reranker llm-gateway retrieval"
echo "  docker compose ps"
