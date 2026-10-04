#!/usr/bin/env python3
"""
SceneHawk dual-vector recommender.

Every film gets two embeddings:
  plot vector  - the film's "text" blob (title, genres, synopsis): what it is about
  mood vector  - the enrichment "embedding_summary" plus atmosphere/tone/emotion
                 descriptors: what it feels like

A query is scored against both:  score = alpha * mood_sim + (1 - alpha) * plot_sim
Use a high alpha for feeling queries ("something cozy for a rainy Sunday") and a
low alpha for content queries ("a heist movie").

Build the index once (this is the only step that embeds the films):
    python recommend.py build

Then ask as many questions as you like (each costs one tiny query embedding):
    python recommend.py "something cozy for a rainy sunday"
    python recommend.py "a slow sad film about grief" --alpha 0.85 --pool underrated
    python recommend.py "heist" --alpha 0.2 --min-rating 7.5 --pacing brisk

For a standard RAG pipeline (one embedding per film, not the dual mood/plot
vectors above), export flat JSONL instead:
    python recommend.py export-rag
    python recommend.py export-rag --out movies_rag.jsonl --limit 5   # cheap test
Each line is {"id", "text", "embedding", "metadata"} - the combined text is the
film's plot blended with its inferred mood, so one vector captures both.

Embedding endpoint (any OpenAI-compatible /embeddings API):
    EMBED_API_KEY   key (falls back to OPENAI_API_KEY, then REQUESTY_API_KEY)
    EMBED_BASE_URL  default https://api.openai.com/v1
                    (Requesty: https://router.requesty.ai/v1)
    EMBED_MODEL     default text-embedding-3-small
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent  # project root (src/ is one level down)
load_dotenv(ROOT / ".env", override=True)  # .env wins over any stale shell env vars

SOURCES = {  # pool name -> enriched JSON
    "popular": str(ROOT / "data" / "movies_metadata.json"),
    "underrated": str(ROOT / "data" / "movies_underrated.json"),
}
INDEX_FILE = str(ROOT / "data" / "film_index.npz")
META_FILE = str(ROOT / "data" / "film_index_meta.json")

BASE_URL = os.environ.get("EMBED_BASE_URL", "https://api.openai.com/v1").rstrip("/")
MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
BATCH_SIZE = 100
MAX_RETRIES = 4
DEFAULT_ALPHA = 0.6


def api_key() -> str:
    for name in ("EMBED_API_KEY", "OPENAI_API_KEY", "REQUESTY_API_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    sys.exit("No API key found. Set EMBED_API_KEY (or OPENAI_API_KEY / REQUESTY_API_KEY).")


def embed(texts: list[str]) -> np.ndarray:
    """Embed texts in batches; returns an (n, dim) float32 array, L2-normalised."""
    key = api_key()
    out = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    f"{BASE_URL}/embeddings",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": MODEL, "input": batch},
                    timeout=60,
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda d: d["index"])
                out.extend(d["embedding"] for d in data)
                break
            except Exception as e:  # noqa: BLE001 - retry, then surface the error
                if attempt == MAX_RETRIES:
                    raise
                wait = 2**attempt
                print(f"  retry {attempt}/{MAX_RETRIES}: {e} (waiting {wait}s)", file=sys.stderr)
                time.sleep(wait)
        print(f"  embedded {min(start + BATCH_SIZE, len(texts))}/{len(texts)}", file=sys.stderr)
    arr = np.asarray(out, dtype=np.float32)
    return arr / np.linalg.norm(arr, axis=1, keepdims=True)


def mood_text(enrichment: dict) -> str | None:
    """The text embedded for the mood vector; None if the film wasn't enriched."""
    if enrichment.get("status") != "ok":
        return None
    return (
        f"{enrichment['embedding_summary']} "
        f"Atmosphere: {', '.join(enrichment['atmosphere'])}. "
        f"Tone: {', '.join(enrichment['tone'])}. "
        f"Feelings: {', '.join(enrichment['emotional_register'])}."
    )


def combined_text(record: dict) -> str:
    """Plot + mood blended into one string, for a single-vector RAG embedding."""
    parts = [record["text"]]
    mt = mood_text(record.get("enrichment", {}))
    if mt:
        parts.append(f"Mood: {mt}")
        pacing = record["enrichment"].get("pacing")
        if pacing:
            parts.append(f"Pacing: {pacing}.")
    return "\n\n".join(parts)


def load_films() -> list[dict]:
    """All films from every source, de-duplicated by tmdb_id (first pool wins)."""
    films, seen = [], set()
    for pool, path in SOURCES.items():
        if not Path(path).exists():
            print(f"skipping missing file: {path}", file=sys.stderr)
            continue
        for rec in json.load(open(path, encoding="utf-8")):
            tid = rec["metadata"]["tmdb_id"]
            if tid in seen:
                continue
            seen.add(tid)
            rec["pool"] = pool
            films.append(rec)
    return films


def build() -> None:
    films = load_films()
    plot_texts = [f["text"] for f in films]
    mood_texts = [mood_text(f.get("enrichment", {})) for f in films]
    has_mood = np.array([t is not None for t in mood_texts])
    print(f"{len(films)} films, {int(has_mood.sum())} with mood text. Model: {MODEL}", file=sys.stderr)

    print("Embedding plot text...", file=sys.stderr)
    plot_vecs = embed(plot_texts)
    print("Embedding mood text...", file=sys.stderr)
    mood_vecs = np.zeros_like(plot_vecs)
    mood_vecs[has_mood] = embed([t for t in mood_texts if t is not None])
    # Films with no mood text (thin synopsis) fall back to their plot vector.
    mood_vecs[~has_mood] = plot_vecs[~has_mood]

    np.savez_compressed(INDEX_FILE, plot=plot_vecs, mood=mood_vecs, has_mood=has_mood)
    meta = []
    for f in films:
        m, e = f["metadata"], f.get("enrichment", {})
        meta.append(
            {
                "tmdb_id": m["tmdb_id"],
                "title": m["title"],
                "year": m["release_year"],
                "genres": m["genres"],
                "rating": m["vote_average"],
                "votes": m["vote_count"],
                "language": m["original_language"],
                "pool": f["pool"],
                "pacing": e.get("pacing"),
                "confidence": e.get("confidence"),
                "summary": e.get("embedding_summary"),
            }
        )
    json.dump({"model": MODEL, "films": meta}, open(META_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Wrote {INDEX_FILE} and {META_FILE}", file=sys.stderr)


def export_rag(out_path: str, limit: int | None = None) -> None:
    """Write one embedding per film as JSONL: {id, text, embedding, metadata}."""
    films = load_films()
    if limit:
        films = films[:limit]
    texts = [combined_text(f) for f in films]
    print(f"{len(films)} films. Model: {MODEL}", file=sys.stderr)
    vecs = embed(texts)

    with open(out_path, "w", encoding="utf-8") as out:
        for f, text, vec in zip(films, texts, vecs):
            m, e = f["metadata"], f.get("enrichment", {})
            row = {
                "id": m["tmdb_id"],
                "text": text,
                "embedding": vec.tolist(),
                "metadata": {
                    "tmdb_id": m["tmdb_id"],
                    "title": m["title"],
                    "release_year": m["release_year"],
                    "genres": m["genres"],
                    "original_language": m["original_language"],
                    "vote_average": m["vote_average"],
                    "vote_count": m["vote_count"],
                    "pool": f["pool"],
                    "pacing": e.get("pacing"),
                    "atmosphere": e.get("atmosphere"),
                    "tone": e.get("tone"),
                    "emotional_register": e.get("emotional_register"),
                    "visual_style_hint": e.get("visual_style_hint"),
                    "confidence": e.get("confidence"),
                    "embedding_summary": e.get("embedding_summary"),
                },
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(films)} rows to {out_path}", file=sys.stderr)


def recommend(
    query: str,
    alpha: float = DEFAULT_ALPHA,
    k: int = 5,
    pool: str | None = None,
    min_rating: float | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    pacing: str | None = None,
    language: str | None = None,
    exclude_low_confidence: bool = False,
) -> list[dict]:
    """Top-k films for a free-text query. Filters are hard constraints."""
    idx = np.load(INDEX_FILE)
    meta = json.load(open(META_FILE, encoding="utf-8"))
    if meta["model"] != MODEL:
        sys.exit(f"Index was built with {meta['model']} but EMBED_MODEL is {MODEL}. Rebuild or match them.")
    films = meta["films"]

    q = embed([query])[0]
    mood_sim = idx["mood"] @ q
    plot_sim = idx["plot"] @ q
    score = alpha * mood_sim + (1 - alpha) * plot_sim

    def keep(f: dict) -> bool:
        return (
            (pool is None or f["pool"] == pool)
            and (min_rating is None or f["rating"] >= min_rating)
            and (min_year is None or (f["year"] or 0) >= min_year)
            and (max_year is None or (f["year"] or 9999) <= max_year)
            and (pacing is None or f["pacing"] == pacing)
            and (language is None or f["language"] == language)
            and not (exclude_low_confidence and f["confidence"] == "low")
        )

    ranked = sorted(
        (i for i, f in enumerate(films) if keep(f)), key=lambda i: score[i], reverse=True
    )
    return [
        {**films[i], "score": float(score[i]), "mood_sim": float(mood_sim[i]), "plot_sim": float(plot_sim[i])}
        for i in ranked[:k]
    ]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "query",
        help='"build" to (re)build the mood-recommender index, "export-rag" to '
        "write flat JSONL embeddings, otherwise a free-text query",
    )
    p.add_argument("--out", default=str(ROOT / "data" / "movies_rag.jsonl"), help="export-rag: output JSONL path")
    p.add_argument("--limit", type=int, default=None, help="export-rag: only embed the first N films (cheap test)")
    p.add_argument("--alpha", type=float, default=DEFAULT_ALPHA,
                   help="mood weight 0-1 (default %(default)s); 1 = feeling only, 0 = plot only")
    p.add_argument("-k", type=int, default=5, help="number of results")
    p.add_argument("--pool", choices=list(SOURCES), help="restrict to one pool")
    p.add_argument("--min-rating", type=float)
    p.add_argument("--min-year", type=int)
    p.add_argument("--max-year", type=int)
    p.add_argument("--pacing", choices=["slow-burn", "deliberate", "moderate", "brisk", "frenetic"])
    p.add_argument("--language", help="original language code, e.g. en, ja, ko")
    p.add_argument("--skip-low-confidence", action="store_true")
    args = p.parse_args()

    if args.query == "build":
        build()
        return
    if args.query == "export-rag":
        export_rag(args.out, args.limit)
        return
    results = recommend(
        args.query, args.alpha, args.k, args.pool, args.min_rating, args.min_year,
        args.max_year, args.pacing, args.language, args.skip_low_confidence,
    )
    if not results:
        print("No films match those filters.")
    for n, r in enumerate(results, 1):
        print(f"{n}. {r['title']} ({r['year']})  [{r['pool']}, {r['rating']:.1f}★, {r['pacing'] or '-'}]"
              f"  score {r['score']:.3f} (mood {r['mood_sim']:.3f} / plot {r['plot_sim']:.3f})")
        if r["summary"]:
            print(f"     {r['summary']}")


if __name__ == "__main__":
    main()
