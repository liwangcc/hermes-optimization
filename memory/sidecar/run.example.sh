#!/usr/bin/env bash
# Example launcher. Edit SEMANTIC_DB to your holographic fact store.
export SEMANTIC_DB="${SEMANTIC_DB:-$HOME/.hermes/memory_store.db}"
export SEMANTIC_MODEL="${SEMANTIC_MODEL:-$(dirname "$0")/models/bge-m3}"
export SEMANTIC_PORT="${SEMANTIC_PORT:-8791}"
exec python "$(dirname "$0")/server.py"