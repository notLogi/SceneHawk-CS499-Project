"use client";

import { useEffect, useRef, useState } from "react";

interface RetrievedFilm {
  title?: string;
  year?: number | string;
  rating?: number;
  pacing?: string;
  pool?: string;
  summary?: string;
  similarity?: number;
}

interface Turn {
  role: "user" | "assistant";
  text: string;
  films?: RetrievedFilm[];
}

const STARTERS = [
  "something cozy for a rainy Sunday",
  "a tense slow-burn that builds dread",
  "a melancholic film about loneliness",
  "an underrated sci-fi that's more thoughtful than action",
];

export default function ChatPanel() {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns, loading]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || loading) return;
    setInput("");
    setTurns((prev) => [...prev, { role: "user", text: message }]);
    setLoading(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = (await res.json()) as { reply?: string; films?: RetrievedFilm[] };
      setTurns((prev) => [
        ...prev,
        {
          role: "assistant",
          text: data.reply ?? "Something went wrong — no reply received.",
          films: data.films,
        },
      ]);
    } catch {
      setTurns((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "I couldn't reach the recommendation service. Is the chatbot server running?",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    send(input);
  }

  return (
    <div className="rounded-2xl border border-[#2a2825] bg-[#141315]">
      {/* Conversation */}
      <div
        ref={scrollRef}
        className="max-h-[55vh] min-h-[220px] space-y-5 overflow-y-auto px-5 py-6 sm:px-6"
      >
        {turns.length === 0 && (
          <div className="py-6 text-center">
            <p className="text-sm text-[#8f8b82]">
              Ask for a film by how you want it to feel — mood, pacing, tone.
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {STARTERS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  className="rounded-full border border-[#2a2825] bg-[#0a0a0a] px-4 py-2 text-xs text-[#b7b2a7] transition-colors hover:border-[#e0632f] hover:text-[#e0632f]"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-[#e0632f] px-4 py-2.5 text-sm text-[#0a0a0a]">
                {t.text}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="max-w-[90%] space-y-3">
                <div className="whitespace-pre-wrap rounded-2xl rounded-bl-sm border border-[#2a2825] bg-[#0a0a0a] px-4 py-3 text-sm leading-relaxed text-[#ece7df]">
                  {t.text}
                </div>
                {t.films && t.films.length > 0 && (
                  <div>
                    <p className="mb-2 text-[10px] uppercase tracking-[0.25em] text-[#8f8b82]">
                      Retrieved candidates
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {t.films.map((f, j) => (
                        <span
                          key={j}
                          title={f.summary ?? ""}
                          className="rounded-full border border-[#3a372f] px-3 py-1 text-[11px] text-[#b7b2a7]"
                        >
                          {f.title}
                          {f.year ? (
                            <span className="text-[#6b675f]"> · {f.year}</span>
                          ) : null}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ),
        )}

        {loading && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-sm border border-[#2a2825] bg-[#0a0a0a] px-4 py-3 text-sm text-[#8f8b82]">
              Searching the corpus…
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form
        onSubmit={onSubmit}
        className="flex gap-3 border-t border-[#2a2825] p-4"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Describe the feeling you're after…"
          className="flex-1 rounded-lg border border-[#2a2825] bg-[#0a0a0a] px-4 py-3 text-sm placeholder:text-[#6b675f] focus:border-[#e0632f] focus:outline-none"
          autoFocus
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-lg bg-[#e0632f] px-6 py-3 text-sm font-semibold text-black transition-colors hover:bg-[#ea7443] disabled:opacity-50"
        >
          {loading ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
