#!/usr/bin/env python3
"""
Load movies_rag.jsonl (produced by recommend.py export-rag) into a local,
persistent Chroma collection.

    python load_chroma.py                    # build/refresh the collection
    python load_chroma.py --query "a heist"   # quick similarity search test

Chroma needs its own query embedding for a text search, so --query only works
if EMBED_API_KEY (or OPENAI_API_KEY / REQUESTY_API_KEY) is set, same as
recommend.py. Loading the JSONL itself needs no API key - the embeddings are
already computed.
"""

import argparse
import json
import sys
from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parent.parent  # project root (src/ is one level down)
JSONL_FILE = str(ROOT / "data" / "movies_rag.jsonl")
DB_DIR = str(ROOT / "chroma_db")
COLLECTION = "films"
BATCH_SIZE = 500  # chroma's add() has an internal max batch size; stay well under it


def load_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def flatten_metadata(md: dict) -> dict:
    """Chroma metadata values must be str/int/float/bool/None - no lists/dicts."""
    out = {}
    for k, v in md.items():
        if isinstance(v, list):
            out[k] = ", ".join(str(x) for x in v) if v else ""
        elif v is None:
            out[k] = ""
        else:
            out[k] = v
    return out


def build() -> None:
    if not Path(JSONL_FILE).exists():
        sys.exit(f"{JSONL_FILE} not found. Run: python recommend.py export-rag")

    rows = load_rows(JSONL_FILE)
    print(f"Loaded {len(rows)} rows from {JSONL_FILE}", file=sys.stderr)

    client = chromadb.PersistentClient(path=DB_DIR)
    # Fresh load each run keeps this idempotent - safe to re-run after re-exporting.
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    coll = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        coll.add(
            ids=[str(r["id"]) for r in batch],
            embeddings=[r["embedding"] for r in batch],
            documents=[r["text"] for r in batch],
            metadatas=[flatten_metadata(r["metadata"]) for r in batch],
        )
        print(f"  added {min(start + BATCH_SIZE, len(rows))}/{len(rows)}", file=sys.stderr)

    print(f"Collection '{COLLECTION}' now has {coll.count()} documents in {DB_DIR}/", file=sys.stderr)


def query(text: str, k: int = 5) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    from recommend import embed  # reuses the same embedding config as export-rag

    client = chromadb.PersistentClient(path=DB_DIR)
    coll = client.get_collection(COLLECTION)
    q = embed([text])[0].tolist()
    res = coll.query(query_embeddings=[q], n_results=k)

    for i, (doc_id, meta, dist) in enumerate(
        zip(res["ids"][0], res["metadatas"][0], res["distances"][0]), 1
    ):
        sim = 1 - dist  # cosine distance -> similarity
        print(f"{i}. {meta['title']} ({meta['release_year']})  [{meta['pool']}, "
              f"{meta['vote_average']}★, {meta['pacing'] or '-'}]  sim {sim:.3f}")
        if meta.get("embedding_summary"):
            print(f"     {meta['embedding_summary']}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--query", help="run a similarity search instead of (re)building the collection")
    p.add_argument("-k", type=int, default=5, help="number of results for --query")
    args = p.parse_args()

    if args.query:
        query(args.query, args.k)
    else:
        build()


if __name__ == "__main__":
    main()
