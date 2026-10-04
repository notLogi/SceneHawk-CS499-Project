#!/usr/bin/env sh
# Container entrypoint for the SceneHawk chatbot service.
#
# The Chroma index (chroma_db/) is derived data, rebuilt from the committed
# data/movies_rag.jsonl — which already holds the embeddings, so this step
# needs NO API key. Building on boot keeps the container stateless: no
# persistent volume required, and the index can never drift from the corpus.
set -e

if [ ! -d chroma_db ] || [ -z "$(ls -A chroma_db 2>/dev/null)" ]; then
  echo "[start] Building Chroma index from data/movies_rag.jsonl ..."
  python src/load_chroma.py
else
  echo "[start] Reusing existing chroma_db/"
fi

# Bind to all interfaces and the host-provided $PORT (Render/Railway/Fly set
# this). --app-dir puts src/ on the import path so server.py can `import chat`.
echo "[start] Launching uvicorn on 0.0.0.0:${PORT:-8000}"
exec uvicorn server:app --app-dir src --host 0.0.0.0 --port "${PORT:-8000}"
