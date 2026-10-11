# SceneHawk

**Find films by how they feel, not just what they are about.**

CSCI 49900, Hunter College (CUNY) · Group 3: Mate Novak, Roger Su, Apurba Acharya

## What SceneHawk does

Most film search works on genre, cast and ratings. People often want
something else: *"something cozy for a rainy Sunday"*, *"a tense slow-burn
that builds dread"*, *"sad, but it ends hopeful"*.

SceneHawk takes a request like that in plain English and returns a short list
of films, each with the reason it matches. It handles three kinds of request:

- **Feeling** — "I want something unsettling and lonely"
- **Story** — "a heist that goes wrong"
- **Both, with or without a genre** — "a hopeful sci-fi about first contact"

- Personalized discovery:** Helps users find films based on mood, atmosphere, and emotional experience rather than relying only on genres or plot summaries.
- Transparent recommendations:** Provides matching scores and review evidence so users can understand why each film was recommended.
- Research-driven design:** Combines a fine-tuned feelings model with story matching and systematic evaluation against general-purpose chatbots.
- 

## Why not just ask a chatbot?

A general LLM knows a little about every film and answers from memory. It has
no fixed measure of how a film feels, so its picks vary from one ask to the
next and cannot be checked.

SceneHawk is narrow on purpose:

- **Our own model.** We fine-tune an open-source model for one job: reading a
  movie review and scoring the feelings the viewer had.
- **A fixed feelings table.** Every film gets a 0–1 score for each feeling on
  one shared list, built from many reviews. The same film always has the same
  scores.
- **Evidence with every pick.** Results show the matching feeling scores and a
  short review snippet, so a recommendation can be checked.
- **A measured comparison.** We test our model against a general LLM and
  report the numbers, including where we lose.

## How the pipeline works

There are two halves. The **build** half runs ahead of time and fills the
database. The **query** half runs each time someone asks for a film.

### Build: filling the database (offline)
 
```
Reviews ──▶ Feelings model (ours) ──▶ scores per review ──▶ average per film ──▶ FEELINGS TABLE

Descriptions + genres ──▶ embeddings + common keywords ─────────────────────▶ DESCRIPTION TABLE
```

1. **Collect.** For each film: reviews, description, genres and basic facts.
2. **Score feelings.** Our fine-tuned model reads every review and outputs a
   0–1 score for each feeling on the list.
3. **Average per film.** Review scores are averaged into one row per film. The
   review count is stored too, so films with few reviews can be labeled
   "low confidence".
4. **Index the story.** Each film's description is embedded, and the most
   common description keywords are stored for matching.

### Query: answering a request (live)

```
                         user prompt
                              │
                        Prompt reader
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
         genre          feeling words       story words
            │                 │                 │
       Genre filter     Feeling match     Description match
      (hard filter)   (feelings table)   (description table)
            │                 └────────┬────────┘
            │                          ▼
            └──────────────▶    Combine scores
                                       ▼
                         Top films + why each fits
```

1. **Read the prompt.** Pull out any genre, the feeling words and the story
   words.
2. **Map feeling words.** Words outside our list are mapped onto it, so
   "gloomy" lands on the right column.
3. **Filter by genre.** Only when the user names one. Films with several
   genres are kept, "not horror" is respected, and the filter loosens if too
   few films are left.
4. **Match feelings.** Score each remaining film against the requested
   feelings using the feelings table.
5. **Match the story.** Score each film on how close its description is to the
   story words.
6. **Combine.** Blend the two scores. The weights follow the prompt: a request
   that is mostly feeling leans on the feelings table, and one that is mostly
   plot leans on the description.
7. **Explain.** Return the top films with their matching scores and a short
   review snippet.

## The feelings model

This is the part of SceneHawk we train ourselves.

| Step | What we do |
| --- | --- |
| **Feelings list** | Fix 20–30 feelings, each with a one-line definition and an example. These are the model's outputs and the table's columns. |
| **Labeling guide** | One main rule: label what the viewer *felt while watching*, not whether they liked the film. |
| **Training labels** | A large LLM labels 3,000–5,000 reviews using the guide. We spot-check 100 by hand. |
| **Answer key** | The team hand-labels 200–300 reviews. The model never trains on these. |
| **Fine-tune** | Start from a small open-source model on Hugging Face and fine-tune it in Google Colab so it outputs a 0–1 score per feeling. |
| **Improve** | Find the feelings the model confuses, fix bad labels, add examples, retrain. |
| **Freeze** | Save the final weights where the whole team and the app can load them. |

The large LLM is used only to create training examples. In the running system,
feelings are scored by our model.

## Evaluation

Two tests, both reported in full:

1. **Model test.** Our model and a general LLM both label the hand-made answer
   key. We compare accuracy feeling by feeling.
2. **Blind test.** 30 prompts (feeling-only, story-only, mixed, with a genre,
   with a "not") are run through SceneHawk and one or two general chatbots.
   At least five people outside the team rate the results without knowing
   which system produced which.

## Project status

| Piece | Status |
| --- | --- |
| Website (search, chat, film pages) | Built, deployed on Vercel |
| Chat service with retrieval over 1,000 TMDB films | Built, deployed on Render |
| Story matching on descriptions | Built |
| Review collection and labeling | In progress |
| Feelings model and feelings table | Planned |
| Genre filter, feeling match, combined scoring | Planned |
| Results screen with scores and evidence | Planned |

### Timeline (Oct 12 – Dec 18)

| Weeks | Phase | Outcome |
| --- | --- | --- |
| 1–3 | Data and labels | Feelings list, collected reviews, training labels, answer key |
| 4–5 | Train the model | Fine-tuned model, model-vs-LLM numbers, filled feelings table |
| 6–8 | Build the pipeline | Prompt reader, genre filter, matching, combined scoring, results screen |
| 9–10 | Test and present | Blind test, report, final demo |

Every week each of us reads one research paper and adds a summary to the
shared notes, so design choices are grounded in prior work.

### Still to decide

- The final feelings list
- Where the reviews come from (each source's terms need checking)
- The exact base model for fine-tuning
- Where the feelings and description tables are stored

### If time allows

- Scene search from subtitles: find a film by a moment in it
- An ending-feeling score, so "sad but ends hopeful" can be matched
- A "did it feel how you wanted?" button that saves feedback

## Tech stack

| Layer | Tools |
| --- | --- |
| Website | Next.js, React, TypeScript, Tailwind CSS — hosted on Vercel |
| Chat service | Python, FastAPI, Chroma vector store — hosted on Render |
| Story embeddings | OpenAI `text-embedding-3-small` |
| Feelings model | Hugging Face Transformers, trained in Google Colab |
| Film data | TMDB (titles, genres, descriptions, ratings) |

## Repo layout

```
src/app/            Website pages and API routes
src/components/     UI components
src/lib/            Search pipelines, retrieval, data access
data/films/         Small hand-analyzed film set used by the search page
chatbot/src/        Chat service: TMDB fetch, embedding, index, API server
chatbot/data/       The 1,000-film dataset the chat service queries
eval/, scripts/     Test queries and the evaluation runner
DEPLOY.md           Deployment guide (Vercel + Render)
```

## Running it locally

### Website

```bash
npm install
npm run dev        # http://localhost:3000
```

The website runs without any API keys.

### Chat service (needed for the `/chat` page)

Requires Python 3.10+. Run it in a second terminal:

```bash
cd chatbot
pip install -r requirements.txt
cp .env.example .env               # then add EMBED_API_KEY and REQUESTY_API_KEY
python src/load_chroma.py          # build the search index once
python -m uvicorn server:app --app-dir src --port 8000
```

`EMBED_API_KEY` turns the user's request into a search. `REQUESTY_API_KEY`
writes the recommendation. Never commit `.env` files.

### Deployment

The website deploys to Vercel and the chat service to Render. The website
finds the chat service through one setting, `CHATBOT_URL`. Full steps are in
[DEPLOY.md](DEPLOY.md).
