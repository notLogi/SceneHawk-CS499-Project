import ChatPanel from "@/components/ChatPanel";

export const metadata = { title: "Chat" };

// Conversational recommendation, backed by the Python chatbot sidecar
// (retrieval over the ~995-film Chroma corpus + an LLM-written answer).
// Distinct from /search, which runs the four in-app comparison pipelines
// over the curated 29-film corpus.
export default function ChatPage() {
  return (
    <div className="pt-12">
      <div className="mx-auto max-w-2xl">
        <div className="mb-8 text-center">
          <p className="mb-4 text-[11px] uppercase tracking-[0.35em] text-[#e0632f]">
            Chat
          </p>
          <h1 className="font-display text-3xl md:text-4xl mb-3">
            Talk to <em className="text-[#e0632f]">SceneHawk</em>
          </h1>
          <p className="text-sm leading-relaxed text-[#8f8b82]">
            Describe what you want to feel and get a written recommendation,
            grounded in films retrieved by mood and plot.
          </p>
        </div>

        <ChatPanel />

        <p className="mt-4 text-center text-[11px] text-[#6b675f]">
          Recommendations are drawn only from the retrieved candidates — the
          assistant won&apos;t invent films that aren&apos;t in the corpus.
        </p>
      </div>
    </div>
  );
}
