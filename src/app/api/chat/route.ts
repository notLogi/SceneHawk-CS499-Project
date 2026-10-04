import { NextRequest, NextResponse } from "next/server";

// POST /api/chat { message }
// Proxies to the Python chatbot sidecar (FastAPI, from scenehawk-cs499).
// Kept server-side so the Python service URL isn't exposed to the browser
// and no CORS round-trip is needed. If the sidecar isn't running, the UI
// gets a friendly message instead of a hard fetch error.
export const dynamic = "force-dynamic";
// Vercel caps serverless function duration (Hobby max ~60s). Set it explicitly
// so a slow reply (or a cold-starting free-tier chatbot) fails cleanly at the
// platform limit instead of being killed abruptly.
export const maxDuration = 60;

const CHATBOT_URL = process.env.CHATBOT_URL ?? "http://127.0.0.1:8000";

export async function POST(req: NextRequest) {
  let message = "";
  let k: number | undefined;
  try {
    const body = (await req.json()) as { message?: string; k?: number };
    message = (body.message ?? "").trim();
    k = body.k;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  if (!message) {
    return NextResponse.json({ error: "missing message" }, { status: 400 });
  }

  try {
    const res = await fetch(`${CHATBOT_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, ...(k ? { k } : {}) }),
      // The LLM generation step can take a while; give it room — but stay
      // under maxDuration (60s) so our own catch returns a friendly message
      // before Vercel kills the function.
      signal: AbortSignal.timeout(55_000),
    });

    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      return NextResponse.json(
        {
          reply: `The recommendation service returned an error (${res.status}). ${detail}`.trim(),
          films: [],
        },
        { status: 502 },
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      {
        reply:
          "I can't reach the recommendation service right now. Make sure the SceneHawk chatbot server is running (`python server.py` in the scenehawk-cs499 folder).",
        films: [],
      },
      { status: 503 },
    );
  }
}
