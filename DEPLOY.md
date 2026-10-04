# Deploying SceneHawk

SceneHawk lives in **one repo** (`notLogi/CSCI499-SceneHawk-Project`) but runs
as **two services** that talk over HTTP. One repo, two hosts:

| Piece | Folder | Host | Why |
| --- | --- | --- | --- |
| Website (Next.js) | repo root | **Vercel** | Static/SSR frontend + API routes — Vercel's sweet spot. |
| Chatbot (FastAPI + Chroma) | [`chatbot/`](chatbot/) | **Render** (or Railway / Fly.io) | Long-running process that holds the vector index in memory. Not a fit for Vercel serverless. |

Separate *hosts* do not mean separate *repos*: Vercel builds the repo root and
ignores `chatbot/` (see [.vercelignore](.vercelignore)); Render builds only the
`chatbot/` subfolder (see [render.yaml](render.yaml)). The only wire between the
two is one env var — the website's `CHATBOT_URL` points at the chatbot's public
URL.

```
Browser ──/chat──▶ Next.js (Vercel) ──/api/chat proxy──▶ FastAPI (Render) ──▶ Chroma + LLM
```

See [src/app/api/chat/route.ts](src/app/api/chat/route.ts) for the proxy and
[chatbot/src/server.py](chatbot/src/server.py) for the service.

---

## Step 1 — Deploy the chatbot (do this first; you need its URL for step 2)

The [`chatbot/`](chatbot/) folder ships a `Dockerfile`, `start.sh`,
`requirements.txt`, and a `.dockerignore`; [render.yaml](render.yaml) at the
repo root wires it up for Render.

**Key fact:** the Chroma index is *derived data*. [chatbot/start.sh](chatbot/start.sh)
rebuilds it from the committed `chatbot/data/movies_rag.jsonl` (embeddings
already baked in) on every boot — **no API key, no persistent volume**. The
container is stateless.

### On Render (Blueprint)

1. Push this repo to GitHub.
2. Render dashboard → **New → Blueprint** → pick the repo. It reads
   [render.yaml](render.yaml) and creates a Docker web service that builds only
   `chatbot/` (`dockerContext: ./chatbot`).
3. Set the secret env vars (marked `sync: false`, so Render prompts for them):
   - `EMBED_API_KEY` — embeds the user's query at request time.
   - `REQUESTY_API_KEY` — generates the written recommendation.
   - `CHATBOT_ALLOWED_ORIGINS` — set to your Vercel domain once you have it
     (step 2), e.g. `https://your-app.vercel.app`.
4. Deploy. Confirm it's up:
   ```bash
   curl https://<your-service>.onrender.com/health
   # {"status":"ok","films":995}
   ```

> The embedding model/key here **must match** how `movies_rag.jsonl` was built
> (default `text-embedding-3-small`). A different model → wrong-dimension query
> vectors → bad or failing retrieval.

### Any Docker host instead

```bash
cd chatbot
docker build -t scenehawk-chatbot .
docker run -p 8000:8000 \
  -e EMBED_API_KEY=... -e REQUESTY_API_KEY=... \
  -e CHATBOT_ALLOWED_ORIGINS=https://your-app.vercel.app \
  scenehawk-chatbot
```

---

## Step 2 — Deploy the website to Vercel

1. Import this repo in Vercel (it auto-detects Next.js at the root; `chatbot/`
   is excluded by [.vercelignore](.vercelignore)). Leave the Root Directory as
   the repo root.
2. **Settings → Environment Variables**, add:
   - `CHATBOT_URL` = the chatbot URL from step 1 (e.g.
     `https://scenehawk-chatbot.onrender.com`). This is the one required var;
     without it the proxy falls back to `127.0.0.1:8000`, which is nothing in
     production. See [.env.example](.env.example) for the rest (all optional).
3. Deploy, then open `/chat` and send a message.

---

## Local development

Two processes, two terminals, from the repo root:

```bash
# Terminal 1 — chatbot (needs chatbot/.env with your keys; see chatbot/.env.example)
cd chatbot
pip install -r requirements.txt
python src/load_chroma.py          # build the index once (reads data/movies_rag.jsonl, no key needed)
uvicorn server:app --app-dir src --port 8000

# Terminal 2 — website
npm run dev                        # CHATBOT_URL defaults to http://127.0.0.1:8000
```

> `chatbot/.env` is gitignored and was **not** copied during the repo merge —
> recreate it from [chatbot/.env.example](chatbot/.env.example) with your own
> `EMBED_API_KEY` / `REQUESTY_API_KEY`.

---

## Gotchas

- **Function timeout.** The proxy allows 90s for a slow LLM call
  ([route.ts](src/app/api/chat/route.ts) `AbortSignal.timeout(90_000)`), but
  Vercel caps serverless duration (Hobby ≈ 60s max). A slow reply can be killed
  by Vercel before the proxy's own timeout. If you hit this, add
  `export const maxDuration = 60;` to the route (Hobby ceiling) or upgrade the
  plan.
- **Render free tier sleeps.** Free services cold-start after idle, so the first
  `/chat` after a quiet spell is slow (and may hit the timeout above). The
  `starter` plan in [render.yaml](render.yaml) avoids this; the free tier also
  tends to be tight on RAM for `chromadb` + `onnxruntime`.
- **CORS.** Only matters if something calls the FastAPI service *directly* from
  a browser. The normal path (browser → Vercel proxy → FastAPI) is
  server-to-server and unaffected. Still, set `CHATBOT_ALLOWED_ORIGINS` to your
  real domain rather than leaving the localhost default.
- **Secrets.** `.env` files are gitignored. Set keys in the Vercel and Render
  dashboards, never commit them.
