# SceneHawk — a mood-aware movie recommender

SceneHawk recommends films by *feeling*, not just genre. Instead of matching
on keywords like "action" or "comedy", it understands requests like
*"something cozy for a rainy Sunday"* or *"a tense slow-burn that builds dread"*
and returns films whose **atmosphere, tone, and pacing** actually match.

It's a RAG (retrieval-augmented generation) system built on ~995 films pulled
from TMDB, each enriched with LLM-inferred mood metadata and embedded into a
vector database for semantic search.

## How it works

1. **Fetch** — pull movie data (title, genres, synopsis, ratings) from TMDB.
2. **Enrich** — an LLM infers each film's `pacing`, `atmosphere`, `tone`,
   `emotional_register`, and a one-line "feels like…" summary from its synopsis.
3. **Embed** — each film's plot + mood text is turned into a vector so films
   can be compared by meaning.
4. **Retrieve** — a user's request is embedded the same way, and the closest
   films are pulled from the vector store.
5. **Generate** *(optional)* — an LLM writes a natural recommendation from the
   retrieved films, explaining why each fits.

## Project layout

```
src/
  recommend.py              Embeds the films; exports the RAG data (data/movies_rag.jsonl)
  load_chroma.py            Builds the Chroma index from the exported JSONL (no API key needed)
  chat.py                   Full RAG chat: retrieval + an LLM-written answer (needs keys)
  server.py                 HTTP API wrapper around the chat retrieval + generation
  enrich_films.py           Adds the mood metadata to the source films (already done)
  tmdb_to_rag_metadata.py   Fetches raw film data from TMDB
data/
  movies_metadata.json      500 popular films (enriched)
  movies_underrated.json    500 underrated films (enriched)
  movies_rag.jsonl          The built dataset the recommender queries
chroma_db/                  Local vector index (gitignored — build it with load_chroma.py)
.env                        Your API keys (gitignored — never committed)
.env.example                Template: copy to .env and add your keys
```

## Setup

Requires Python 3.10+.

```bash
pip install chromadb python-dotenv numpy requests
```

## How to run it:

1. In PowerShell:
   - git clone https://github.com/notLogi/SceneHawk-CS499.git
   - cd SceneHawk-CS499
3. Install the following dependencies:
   - pip install chromadb python-dotenv numpy requests
4. Copy the template to `.env` and add your own keys:
   - cp .env.example .env
   - EMBED_API_KEY=sk-proj-your-openai-key
     REQUESTY_API_KEY=rqsty-sk-your-requesty-key
5. Build the vector index (reads data/movies_rag.jsonl; no API key needed):
   - python src/load_chroma.py
6. Run the chat:
   - python src/chat.py "something cozy for a rainy sunday"
   - python src/chat.py                      # interactive loop; blank line to quit



