#!/usr/bin/env python3
"""
SceneHawk chat: ask for a recommendation in plain English, get a written
answer grounded in retrieved films - not just a ranked list.

This is the "generation" half of RAG. Retrieval (load_chroma.py) already
finds candidate films by semantic similarity; this script hands those
candidates to an LLM (via Requesty) and asks it to write an actual
recommendation, explaining why each pick fits the request.

Usage:
    python chat.py "something cozy for a rainy sunday"
    python chat.py "a heist movie" -k 8
    python chat.py                       # interactive loop, blank line to quit

Needs two separate keys (they can be the same key if you route both
through Requesty):
    EMBED_API_KEY (or OPENAI_API_KEY / REQUESTY_API_KEY) - to embed the query
    REQUESTY_API_KEY                                      - to generate the reply
"""

import argparse
import os
import sys
from pathlib import Path

import chromadb
import requests

from recommend import embed  # same embedding config used to build chroma_db (also loads .env)

ROOT = Path(__file__).resolve().parent.parent  # project root (src/ is one level down)
ROUTER_URL = "https://router.requesty.ai/v1/chat/completions"
CHAT_MODEL = os.environ.get("REQUESTY_CHAT_MODEL", "novita/ling-3.1-flash")
DB_DIR = str(ROOT / "chroma_db")
COLLECTION = "films"

SYSTEM_PROMPT = """You are a film recommendation assistant. You are given a user's \
request and a CONTEXT list of candidate films retrieved by semantic search \
(each with title, year, rating, and a short synopsis).

Recommend only films that appear in CONTEXT - never invent a film that isn't listed. \
Pick the best 2-4 matches, ranked best first.

Output plain text only - NO Markdown, no asterisks, no bold. This is read in a \
terminal, so formatting characters show up as literal symbols. Format each pick \
as a numbered entry laid out exactly like this:

1. Title (Year)  -  rating stars
   Why it fits: one or two sentences referencing its plot and themes.

Leave a blank line between entries. Start with a single short intro line (e.g. \
"Here are the best matches for a tense heist:"). If nothing in CONTEXT fits well, \
say so honestly in one line instead of forcing a recommendation."""


def retrieve(query: str, k: int) -> list[dict]:
    client = chromadb.PersistentClient(path=DB_DIR)
    coll = client.get_collection(COLLECTION)
    q = embed([query])[0].tolist()
    res = coll.query(query_embeddings=[q], n_results=k)
    return [
        {"text": doc, "metadata": meta, "similarity": 1 - dist}
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]


def build_context(films: list[dict]) -> str:
    blocks = []
    for f in films:
        m = f["metadata"]
        blocks.append(
            f"- {m['title']} ({m['release_year']}) [{m['pool']}, {m['vote_average']}★]\n"
            f"  Synopsis: {f['text'][:300]}"
        )
    return "\n\n".join(blocks)


def ask_llm(query: str, context: str) -> str:
    api_key = os.environ.get("REQUESTY_API_KEY")
    if not api_key:
        sys.exit("REQUESTY_API_KEY is not set.")
    resp = requests.post(
        ROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": CHAT_MODEL,
            "max_tokens": 3000,  # gemma-4-31b-it is a reasoning model; budget must cover hidden reasoning tokens + the answer
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"User request: {query}\n\nCONTEXT (candidate films):\n{context}"},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    choice = resp.json()["choices"][0]
    content = choice["message"].get("content")
    if not content:
        sys.exit(f"empty reply from model (finish_reason={choice.get('finish_reason')})")
    return content.strip()


def answer(query: str, k: int) -> None:
    films = retrieve(query, k)
    if not films:
        print("No films found in the index. Did you run load_chroma.py?")
        return
    reply = ask_llm(query, build_context(films))
    print(reply)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("query", nargs="?", help="your request; omit for an interactive loop")
    p.add_argument("-k", type=int, default=6, help="how many candidate films to retrieve as context")
    args = p.parse_args()

    if args.query:
        answer(args.query, args.k)
        return

    print("SceneHawk chat - ask for a recommendation (blank line to quit)")
    while True:
        try:
            query = input("\n> ").strip()
        except EOFError:
            break
        if not query:
            break
        answer(query, args.k)


if __name__ == "__main__":
    main()
