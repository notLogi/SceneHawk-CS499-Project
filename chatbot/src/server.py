#!/usr/bin/env python3
"""
SceneHawk chatbot HTTP service.

Exposes the existing RAG chat pipeline (retrieve from the Chroma vector
store, then have an LLM write a grounded recommendation) as a small
FastAPI endpoint so the Next.js website can call it.

    pip install "fastapi>=0.110" "uvicorn[standard]>=0.27"
    python server.py                 # serves on http://127.0.0.1:8000
    # or: uvicorn server:app --port 8000

Endpoints:
    GET  /health         -> {"status": "ok", "films": <count>}
    POST /chat  {message} -> {"reply": "...", "films": [ {title, ...}, ... ]}

The heavy objects (Chroma client + collection) are opened once at startup
and reused across requests, unlike the CLI which reopens them each run.
"""

import os
import sys

import chromadb
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from recommend import embed  # same embedding config used to build chroma_db (also loads .env)
from chat import DB_DIR, COLLECTION, ROUTER_URL, CHAT_MODEL, SYSTEM_PROMPT, build_context

# Which website origins may call this service directly from the browser.
# The Next.js app proxies through its own /api/chat route (server-to-server,
# no CORS needed), but allowing localhost keeps direct calls working too.
ALLOWED_ORIGINS = os.environ.get(
    "CHATBOT_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app = FastAPI(title="SceneHawk chatbot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Open the persistent collection once. If it's missing, fail loudly at
# startup rather than on the first request.
_client = chromadb.PersistentClient(path=DB_DIR)
try:
    _collection = _client.get_collection(COLLECTION)
except Exception as e:  # noqa: BLE001 - surface a clear setup hint
    sys.exit(
        f"Could not open Chroma collection '{COLLECTION}' in {DB_DIR}: {e}\n"
        "Did you run `python load_chroma.py` to build the index?"
    )


class ChatRequest(BaseModel):
    message: str
    k: int = 6


def retrieve(query: str, k: int) -> list[dict]:
    q = embed([query])[0].tolist()
    res = _collection.query(query_embeddings=[q], n_results=k)
    return [
        {"text": doc, "metadata": meta, "similarity": 1 - dist}
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        )
    ]


def generate(query: str, context: str) -> str:
    """Ask the LLM for a written recommendation grounded in the context.

    Reimplemented here (rather than importing chat.ask_llm) so a missing
    key or an upstream error returns an HTTP-friendly message instead of
    calling sys.exit() and taking down the worker.
    """
    api_key = os.environ.get("REQUESTY_API_KEY")
    if not api_key:
        return "The recommendation service isn't configured (REQUESTY_API_KEY is not set)."
    resp = requests.post(
        ROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": CHAT_MODEL,
            # Budget for the written recommendation (2-4 films). Larger values
            # allow longer replies at some cost to latency.
            "max_tokens": 2000,
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"User request: {query}\n\nCONTEXT (candidate films):\n{context}",
                },
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    choice = resp.json()["choices"][0]
    content = choice["message"].get("content")
    if not content:
        return f"The model returned an empty reply (finish_reason={choice.get('finish_reason')})."
    return content.strip()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "films": _collection.count()}


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    message = (req.message or "").strip()
    if not message:
        return {"reply": "Ask me what you're in the mood for.", "films": []}

    films = retrieve(message, req.k)
    if not films:
        return {
            "reply": "I couldn't find anything in the index for that. Try describing a mood, pacing, or feeling.",
            "films": [],
        }

    reply = generate(message, build_context(films))
    return {
        "reply": reply,
        # Return the retrieved candidates so the UI can show what grounded the answer.
        "films": [
            {
                "title": f["metadata"].get("title"),
                "year": f["metadata"].get("release_year"),
                "rating": f["metadata"].get("vote_average"),
                "pacing": f["metadata"].get("pacing"),
                "pool": f["metadata"].get("pool"),
                "summary": f["metadata"].get("embedding_summary"),
                "similarity": round(f["similarity"], 3),
            }
            for f in films
        ],
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("CHATBOT_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
