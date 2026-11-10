"use client";

import { FormEvent, useState } from "react";

const STREAM_URL = "http://localhost:8010/stream";

type ToolStep = {
  tool: string;
  status: string;
  message: string;
};

export default function StreamingPage() {
  const [prompt, setPrompt] = useState("Check rice stock");
  const [answer, setAnswer] = useState("");
  const [toolStep, setToolStep] = useState<ToolStep | null>(null);
  const [status, setStatus] = useState("Idle");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!prompt.trim() || loading) return;

    setAnswer("");
    setToolStep(null);
    setError("");
    setStatus("Connecting...");
    setLoading(true);

    try {
      const response = await fetch(
        `${STREAM_URL}?prompt=${encodeURIComponent(prompt.trim())}`,
        { headers: { Accept: "text/event-stream" } }
      );

      if (!response.ok || !response.body) {
        throw new Error(`Streaming request failed (${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let completed = false;

      while (!completed) {
        const { value, done } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const rawEvent of events) {
          const lines = rawEvent.split("\n");
          const eventName =
            lines.find((line) => line.startsWith("event:"))
              ?.slice(6)
              .trim() ?? "message";

          const data = lines
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim())
            .join("\n");

          if (!data) continue;

          if (data === "[DONE]") {
            setStatus("Completed");
            completed = true;
            break;
          }

          if (eventName === "tool_step") {
            setToolStep(JSON.parse(data) as ToolStep);
            setStatus("Tool executed");
            continue;
          }

          const parsed = JSON.parse(data) as { token?: string };

          if (parsed.token) {
            setAnswer((previous) => previous + parsed.token);
            setStatus("Streaming response...");
          }
        }
      }

      if (!completed) {
        setStatus("Connection closed");
      }

      await reader.cancel();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to stream response"
      );
      setStatus("Failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-5 py-10 text-slate-900">
      <div className="mx-auto max-w-3xl">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-blue-700">
            Week 1 · AI Spike
          </p>

          <h1 className="mt-2 text-3xl font-bold">
            Kitchen Copilot Streaming
          </h1>

          <p className="mt-2 text-slate-600">
            Test incremental responses and tool execution events using
            Server-Sent Events.
          </p>
        </div>

        <section className="mt-8 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <form onSubmit={handleSubmit}>
            <label
              htmlFor="prompt"
              className="block text-sm font-medium text-slate-700"
            >
              Enter a prompt
            </label>

            <input
              id="prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              disabled={loading}
              className="mt-2 w-full rounded-lg border border-slate-300 px-4 py-3 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
              placeholder="Ask Kitchen Copilot..."
            />

            <button
              type="submit"
              disabled={loading || !prompt.trim()}
              className="mt-4 rounded-lg bg-blue-700 px-5 py-2.5 font-medium text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Streaming..." : "Start streaming"}
            </button>
          </form>

          <div className="mt-6 border-t border-slate-100 pt-5">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">Execution status</h2>
              <span className="text-sm text-blue-700">{status}</span>
            </div>

            {toolStep && (
              <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
                  Tool step · {toolStep.status}
                </p>
                <p className="mt-1 font-medium">{toolStep.tool}</p>
                <p className="mt-1 text-sm text-slate-600">
                  {toolStep.message}
                </p>
              </div>
            )}

            <h3 className="mt-6 text-sm font-semibold text-slate-700">
              Streamed response
            </h3>

            <div className="mt-2 min-h-32 whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-sm leading-7 text-slate-800">
              {answer || (
                <span className="text-slate-400">
                  The streamed response will appear here...
                </span>
              )}
            </div>

            {error && (
              <p className="mt-3 text-sm text-red-600">{error}</p>
            )}
          </div>
        </section>

        <p className="mt-5 text-xs text-slate-500">
          Offline FakeLLM demonstration. No production inventory is accessed
          or modified.
        </p>
      </div>
    </main>
  );
}
