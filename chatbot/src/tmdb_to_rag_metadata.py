"""
Fetch movies from TMDB and turn them into RAG-ready metadata.


OUTPUT
------
movies_metadata.json — a list of 500 records, each shaped like:

{
  "id": 12345,
  "text": "Title (Year)\nGenres: Action, Sci-Fi\n\nOverview text...",
  "metadata": {
      "tmdb_id": 12345,
      "title": "...",
      "release_year": 2010,
      "genres": ["Action", "Sci-Fi"],
      "original_language": "en",
      "popularity": 123.4,
      "vote_average": 8.1,
      "vote_count": 20000,
      "overview": "..."
  }
}

"text" is what you embed. "metadata" is what you store alongside the vector
for filtering (e.g. "sci-fi movies from the 2010s with rating > 7").
"""

import argparse
import os
import sys
import json
import time
import requests

TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"
TARGET_COUNT = 500
PAGE_SIZE = 20  # fixed by TMDB
SOURCE_ENDPOINT = "discover/movie"  # swap for "movie/top_rated" or "discover/movie" as needed

OUTPUT_FILE = "movies_metadata.json"

# --underrated: well rated, but few people have rated them. The vote_count floor
# keeps out films with a handful of votes, where a 9.0 average means nothing.
UNDERRATED_OUTPUT_FILE = "movies_underrated.json"
UNDERRATED_PARAMS = {
    "sort_by": "vote_average.desc",
    "vote_average.gte": 7.5,
    "vote_count.gte": 200,
    "vote_count.lte": 2000,
    "include_adult": "false",
    "primary_release_date.lte": time.strftime("%Y-%m-%d"),  # released only
}


def fetch_genre_map():
    """TMDB returns genre IDs, not names — fetch the lookup table once."""
    resp = requests.get(
        f"{BASE_URL}/genre/movie/list",
        params={"api_key": TMDB_API_KEY, "language": "en-US"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {g["id"]: g["name"] for g in data.get("genres", [])}


def fetch_page(page_num, extra_params=None):
    resp = requests.get(
        f"{BASE_URL}/{SOURCE_ENDPOINT}",
        params={
            "api_key": TMDB_API_KEY,
            "language": "en-US",
            "page": page_num,
            **(extra_params or {}),
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def build_record(movie, genre_map):
    genre_names = [genre_map.get(gid, "Unknown") for gid in movie.get("genre_ids", [])]
    release_date = movie.get("release_date") or ""
    release_year = int(release_date[:4]) if release_date[:4].isdigit() else None
    overview = (movie.get("overview") or "").strip()
    title = movie.get("title") or movie.get("original_title") or "Untitled"

    text_parts = [f"{title} ({release_year})" if release_year else title]
    if genre_names:
        text_parts.append(f"Genres: {', '.join(genre_names)}")
    if overview:
        text_parts.append(overview)
    text_blob = "\n".join(text_parts)

    return {
        "id": movie.get("id"),
        "text": text_blob,
        "metadata": {
            "tmdb_id": movie.get("id"),
            "title": title,
            "release_year": release_year,
            "genres": genre_names,
            "original_language": movie.get("original_language"),
            "popularity": movie.get("popularity"),
            "vote_average": movie.get("vote_average"),
            "vote_count": movie.get("vote_count"),
            "overview": overview,
        },
    }


def existing_ids(path):
    """tmdb_ids already in a previous export, so --underrated adds new films only."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {r["metadata"]["tmdb_id"] for r in json.load(f)}
    except (OSError, ValueError, KeyError):
        return set()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--underrated",
        action="store_true",
        help=f"fetch highly rated, low-vote films into {UNDERRATED_OUTPUT_FILE} "
        f"instead of the default popular set",
    )
    args = parser.parse_args()
    extra_params = UNDERRATED_PARAMS if args.underrated else None
    output_file = UNDERRATED_OUTPUT_FILE if args.underrated else OUTPUT_FILE
    skip_ids = existing_ids(OUTPUT_FILE) if args.underrated else set()

    if not TMDB_API_KEY:
        print(
            "ERROR: TMDB_API_KEY environment variable is not set.\n"
            "Set it first, e.g.: export TMDB_API_KEY='your_key_here'",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Fetching genre lookup table...")
    genre_map = fetch_genre_map()

    all_records = []
    page = 1
    pages_needed = (TARGET_COUNT + PAGE_SIZE - 1) // PAGE_SIZE

    while len(all_records) < TARGET_COUNT and page <= pages_needed + 5:
        print(f"Fetching page {page} ({len(all_records)}/{TARGET_COUNT} so far)...")
        try:
            results = fetch_page(page, extra_params)
        except requests.HTTPError as e:
            print(f"Request failed on page {page}: {e}", file=sys.stderr)
            break

        if not results:
            print("No more results returned by TMDB — stopping early.")
            break

        for movie in results:
            if movie.get("id") in skip_ids:
                continue
            all_records.append(build_record(movie, genre_map))
            skip_ids.add(movie.get("id"))  # also drops repeats across pages
            if len(all_records) >= TARGET_COUNT:
                break

        page += 1
        time.sleep(0.25)  # be polite to the API / stay well under rate limits

    all_records = all_records[:TARGET_COUNT]

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\nDone. Wrote {len(all_records)} movies to {output_file}")


if __name__ == "__main__":
    main()
