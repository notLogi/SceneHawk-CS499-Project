#!/usr/bin/env python3
"""
SceneHawk enrichment pipeline.

Turns a raw TMDB-style film export (title, genres, overview, ratings) into
an enriched knowledge base with inferred atmosphere/tone/pacing/emotional
fields, suitable for embedding and semantic retrieval.

Calls go through the Requesty router (OpenAI-compatible chat completions).

Usage:
    export REQUESTY_API_KEY=rqsty-sk-...
    python enrich_films.py films.json enriched_films.jsonl

    # try a handful first:
    python enrich_films.py films.json enriched_films.jsonl --limit 5

    # test the data-cleaning steps without spending API calls:
    python enrich_films.py films.json enriched_films.jsonl --dry-run

Input format: a JSON list of records shaped like:
    {
      "id": 969681,
      "text": "...",
      "metadata": {
        "tmdb_id": 969681, "title": "...", "release_year": 2026,
        "genres": [...], "original_language": "en",
        "popularity": 704.4, "vote_average": 7.8, "vote_count": 2809,
        "overview": "..."
      }
    }

Output format: JSON Lines, one enriched record per line, so partial runs
resume cleanly and large datasets don't need to be held fully in memory.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # read keys from project-root .env

MIN_OVERVIEW_WORDS = 8
ROUTER_URL = "https://router.requesty.ai/v1/chat/completions"
MODEL = os.environ.get("REQUESTY_MODEL", "google/gemma-4-31b-it")
MAX_RETRIES = 3

SYSTEM_PROMPT = """You are a film analyst producing structured metadata for a recommendation system. For each film, infer its likely atmosphere, tone, pacing, and emotional register from its title, genre tags, and plot synopsis.

You have not seen the film. Base your answer only on what a synopsis and genre tags can reasonably imply. Do not invent plot details, character names, or visual specifics that are not stated or strongly implied.

If the synopsis is too short or generic to support a confident inference (fewer than ~15 words, or purely a premise with no emotional or stylistic cues), still produce your best-guess fields but set "confidence" to "low" and keep descriptors generic rather than fabricating specificity.

Respond with ONLY a JSON object matching this schema, no other text:

{
  "pacing": "slow-burn" | "deliberate" | "moderate" | "brisk" | "frenetic",
  "atmosphere": [2 to 4 short lowercase descriptors],
  "tone": [1 to 3 short lowercase descriptors],
  "emotional_register": [1 to 3 short lowercase nouns],
  "visual_style_hint": a short phrase (<=8 words) or null,
  "confidence": "low" | "medium",
  "embedding_summary": one sentence (<=25 words), written as "a film that feels like..."
}"""


def load_films(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dedupe(records: list[dict]) -> list[dict]:
    """Keep the highest-vote_count record per tmdb_id."""
    best: dict[int, dict] = {}
    for r in records:
        md = r["metadata"]
        tid = md["tmdb_id"]
        if tid not in best or md.get("vote_count", 0) > best[tid]["metadata"].get(
            "vote_count", 0
        ):
            best[tid] = r
    deduped = list(best.values())
    print(
        f"Deduped {len(records)} -> {len(deduped)} records "
        f"({len(records) - len(deduped)} duplicates removed)",
        file=sys.stderr,
    )
    return deduped


def classify(record: dict) -> str:
    """Return 'ready', 'thin_overview', or 'zero_signal'."""
    md = record["metadata"]
    overview = (md.get("overview") or "").strip()
    if len(overview.split()) < MIN_OVERVIEW_WORDS:
        return "thin_overview"
    if md.get("vote_count", 0) == 0 and md.get("vote_average", 0) == 0:
        return "zero_signal"
    return "ready"


def build_user_prompt(record: dict) -> str:
    md = record["metadata"]
    genres = ", ".join(md.get("genres") or []) or "unspecified"
    return (
        f"Title: {md['title']} ({md.get('release_year', 'n/a')})\n"
        f"Genres: {genres}\n"
        f"Synopsis: {md.get('overview', '')}"
    )


def call_model(api_key: str, user_prompt: str) -> dict:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                ROUTER_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": MODEL,
                    # Gemma reasons before answering, and reasoning tokens count
                    # against this cap; 400 left no room for the actual JSON.
                    "max_tokens": 3000,
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=60,
            )
            resp.raise_for_status()
            choice = resp.json()["choices"][0]
            content = choice["message"].get("content")
            if not content:
                raise ValueError(
                    f"empty content (finish_reason={choice.get('finish_reason')})"
                )
            text = content.strip()
            text = text.removeprefix("```json").removeprefix("```").removesuffix(
                "```"
            ).strip()
            return json.loads(text)
        except Exception as e:  # noqa: BLE001 - broad by design, we retry/report
            if attempt == MAX_RETRIES:
                raise
            wait = 2**attempt
            print(f"  retry {attempt}/{MAX_RETRIES} after error: {e} "
                  f"(waiting {wait}s)", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def enrich(records: list[dict], dry_run: bool) -> list[dict]:
    api_key = None
    if not dry_run:
        api_key = os.environ.get("REQUESTY_API_KEY")
        if not api_key:
            print("REQUESTY_API_KEY is not set.", file=sys.stderr)
            sys.exit(1)

    out = []
    counts = {"ready": 0, "thin_overview": 0, "zero_signal": 0}
    for i, record in enumerate(records, 1):
        status = classify(record)
        counts[status] += 1
        title = record["metadata"]["title"]

        if status == "thin_overview":
            record["enrichment"] = {"status": "skipped_thin_overview"}
        elif dry_run:
            record["enrichment"] = {"status": "dry_run_skipped"}
        else:
            print(f"[{i}/{len(records)}] enriching: {title}", file=sys.stderr)
            try:
                fields = call_model(api_key, build_user_prompt(record))
                fields["status"] = "ok"
                if status == "zero_signal":
                    fields["note"] = "zero vote_count/vote_average: unreleased or unrated"
                record["enrichment"] = fields
            except Exception as e:  # noqa: BLE001
                print(f"  FAILED after retries: {e}", file=sys.stderr)
                record["enrichment"] = {"status": "error", "error": str(e)}
        out.append(record)
    print(f"Classification counts: {counts}", file=sys.stderr)
    return out


def write_jsonl(records: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(records)} records to {path}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", help="Path to raw film export (JSON list)")
    parser.add_argument("output_jsonl", help="Path to write enriched JSONL")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run dedupe/classification only; skip model calls",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N records (for cheap test runs)",
    )
    args = parser.parse_args()

    if not Path(args.input_json).exists():
        print(f"Input file not found: {args.input_json}", file=sys.stderr)
        sys.exit(1)

    records = load_films(args.input_json)
    records = dedupe(records)
    if args.limit:
        records = records[: args.limit]
    enriched = enrich(records, dry_run=args.dry_run)
    write_jsonl(enriched, args.output_jsonl)


if __name__ == "__main__":
    main()
