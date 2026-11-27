"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { ArrowUp, ClipboardSignature, ListTree, MessageSquarePlus, ShieldAlert, ShieldCheck } from "lucide-react";

import { api } from "@/lib/api/client";
import { AGENT_ENDPOINT } from "@/lib/api/endpoints";
import { WORKFLOW_LABELS, suggestionsFor, type AgentProposal, type AgentStep } from "@/lib/agent";
import { errorMessage, formatDateTime } from "@/lib/payments";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import Modal from "@/components/ui/Modal";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { useToast } from "@/components/ui/Toast";
import { Answer, CopilotMark, ProposalCard, Thinking } from "@/components/copilot/CopilotParts";
import { useCopilot } from "@/components/copilot/CopilotProvider";

/**
 * Stage 12: Kitchen Copilot, full screen. The conversation is the same one
 * the floating panel shows (CopilotProvider); this screen adds the
 * conversation list, the full proposal history and the step trace.
 */
export default function CopilotPage() {
  const toast = useToast();
  const pathname = usePathname();
  const c = useCopilot();
  const { status, thread, sending } = c;
  const [tab, setTab] = useState<"chat" | "proposals">("chat");
  const [text, setText] = useState("");
  const [trace, setTrace] = useState<AgentStep[] | null>(null);
  const [traceOpen, setTraceOpen] = useState(false);
  const [queue, setQueue] = useState<AgentProposal[] | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (tab !== "proposals" || !status?.enabled) return;
    let active = true;
    api.get<{ items: AgentProposal[] }>(`${AGENT_ENDPOINT}/proposals`)
      .then((r) => active && setQueue(r.items))
      .catch((err: unknown) => { if (active) { setQueue([]); toast.error(errorMessage(err, "Unable to load proposals.")); } });
    return () => { active = false; };
  }, [tab, status?.enabled, toast]);

  // Decisions made here or in the panel update the history list.
  useEffect(() => c.onProposalChange((updated) =>
    setQueue((q) => q ? q.map((x) => x.id === updated.id ? updated : x) : q)), [c]);

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [thread?.messages.length, sending]);

  async function submit(message: string) {
    if (message.trim().length < 2) return;
    setText("");
    setTab("chat");
    if (!(await c.send(message))) setText(message);
  }

  function showTrace() {
    if (!thread?.id) return;
    setTrace(null);
    setTraceOpen(true);
    api.get<{ items: AgentStep[] }>(`${AGENT_ENDPOINT}/conversations/${thread.id}/trace`).then((r) => setTrace(r.items))
      .catch((err: unknown) => { setTrace([]); toast.error(errorMessage(err, "Unable to load the steps.")); });
  }

  if (c.statusError) return <ErrorState message={c.statusError} />;
  if (!status) return <TableSkeleton rows={4} />;
  const suggestions = suggestionsFor(pathname, status.workflows);

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-5 border-b border-slate-200 pb-6 md:flex-row md:items-end md:justify-between">
        <div className="flex min-w-0 items-start gap-4">
          <span className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white ring-4 ring-[#d9f18d]/45 sm:flex"><CopilotMark size={24} /></span>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold tracking-[0.14em] text-slate-500 uppercase">Assistant</p>
            <h1 className="mt-1 text-[1.9rem] leading-tight font-semibold tracking-tight text-slate-900 sm:text-[2.2rem]">Kitchen Copilot</h1>
            <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-slate-600">Ask in plain words. Copilot reads your campus records through permission-checked tools, shows its working, and prepares actions that only take effect when a person approves them. The same conversation is in the Copilot button on every screen.</p>
          </div>
        </div>
        {status.enabled && (
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-slate-700">
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              {status.reader === "gemini" ? `Language model: ${status.external_model}` : "Built-in request reader (no external AI)"}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-slate-700">
              <ShieldCheck size={13} aria-hidden /> Figures always come from the application
            </span>
          </div>
        )}
      </section>

      {!status.enabled ? (
        <Card>
          <EmptyState icon={ShieldAlert} title="Kitchen Copilot is turned off"
            description="An administrator can turn it on with the AGENT_ENABLED setting. Every other screen works normally while it is off." />
        </Card>
      ) : (
        <>
          <SegmentedControl label="View" value={tab} onChange={setTab} options={[{ value: "chat", label: "Conversation" }, { value: "proposals", label: "Proposals to review" }]} />

          {tab === "proposals" ? (
            queue === null ? <TableSkeleton rows={3} /> : queue.length === 0 ? (
              <Card><EmptyState icon={ClipboardSignature} title="No proposals" description="Proposals Copilot prepares for you, or that you may approve, appear here." /></Card>
            ) : (
              <div className="grid gap-4 lg:grid-cols-2" data-queue>
                {queue.map((p) => (
                  <div key={p.id} className="space-y-1">
                    <p className="text-xs text-slate-500">{WORKFLOW_LABELS[p.workflow]} · asked by {p.created_by_name} · {formatDateTime(p.created_at)}</p>
                    <ProposalCard p={p} onDecide={c.requestDecision} />
                  </div>
                ))}
              </div>
            )
          ) : (
            <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
              <Card className="hidden h-fit p-3 lg:block">
                <p className="px-2 pt-1 pb-2 text-[10.5px] font-semibold tracking-[0.14em] text-slate-500 uppercase">Conversations</p>
                <Button variant="secondary" size="sm" className="w-full" icon={<MessageSquarePlus size={15} />} onClick={c.newConversation}>New conversation</Button>
                <ul className="mt-3 space-y-1 text-sm">
                  {c.conversations.map((conv) => (
                    <li key={conv.id}>
                      <button type="button" onClick={() => void c.openConversation(conv.id)}
                        className={`w-full truncate rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-slate-100 ${thread?.id === conv.id ? "bg-slate-900 font-medium text-white hover:bg-slate-900" : "text-slate-700"}`}>
                        {conv.title}
                      </button>
                    </li>
                  ))}
                  {c.conversations.length === 0 && <li className="px-2 text-xs text-slate-500">No conversations yet.</li>}
                </ul>
              </Card>

              <Card className="flex min-h-[64vh] flex-col overflow-hidden">
                <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-3 sm:px-5">
                  <p className="flex min-w-0 items-center gap-2 text-sm font-semibold text-slate-800"><span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-[#b2d64e]" /><span className="truncate">{thread?.title ?? "New conversation"}</span></p>
                  <div className="flex shrink-0 gap-1">
                    {thread?.id ? <Button variant="ghost" size="sm" icon={<ListTree size={15} />} onClick={showTrace}>Steps</Button> : null}
                    <Button variant="ghost" size="sm" className="lg:hidden" icon={<MessageSquarePlus size={15} />} onClick={c.newConversation}>New</Button>
                  </div>
                </div>
                <div className="flex-1 space-y-6 overflow-y-auto p-4 sm:p-6" data-thread>
                  {!thread || thread.messages.length === 0 ? (
                    <div className="mx-auto max-w-2xl space-y-5 py-6 sm:py-10">
                      <div>
                        <p className="text-2xl font-semibold tracking-tight text-slate-900">What can I help with?</p>
                        <p className="mt-1 text-sm text-slate-600">Try one of the jobs Copilot can do for you:</p>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {suggestions.map((s) => (
                          <button key={s.text} type="button" disabled={sending} onClick={() => void submit(s.text)}
                            className="flex flex-col rounded-2xl border border-slate-200 bg-white p-4 text-left text-sm transition-[border-color,transform] duration-200 hover:-translate-y-0.5 hover:border-slate-900 disabled:cursor-not-allowed disabled:opacity-50">
                            <Badge tone="brand">{WORKFLOW_LABELS[s.workflow]}</Badge>
                            <span className="mt-2.5 block leading-relaxed text-slate-800">{s.text}</span>
                          </button>
                        ))}
                      </div>
                      {suggestions.length < 4 && <p className="text-xs text-slate-500">Jobs that need permissions you don&rsquo;t have are not shown.</p>}
                    </div>
                  ) : thread.messages.map((m) => m.role === "user" ? (
                    <div key={m.id} className="flex justify-end">
                      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-slate-900 px-4 py-2.5 text-[14.5px] leading-relaxed text-white">{m.content}</p>
                    </div>
                  ) : (
                    <Answer key={m.id} m={m} proposals={thread.proposals} onChoice={(t) => void submit(t)} onDecide={c.requestDecision} busy={sending} />
                  ))}
                  {sending && <div className="pl-12"><Thinking /></div>}
                  <div ref={end} />
                </div>
                <form className="border-t border-slate-100 bg-white p-3 sm:p-4" onSubmit={(e) => { e.preventDefault(); void submit(text); }}>
                  <div className="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-1.5 pl-3 transition-[border-color,box-shadow] focus-within:border-slate-900 focus-within:ring-4 focus-within:ring-[#d9f18d]/40">
                    <label htmlFor="copilot-input" className="sr-only">Message</label>
                    <textarea id="copilot-input" rows={2} value={text} maxLength={1000} onChange={(e) => setText(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void submit(text); } }}
                      placeholder="Ask Kitchen Copilot…" className="min-h-11 min-w-0 flex-1 resize-none border-0 bg-transparent py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none" />
                    <Button type="submit" loading={sending} disabled={text.trim().length < 2} icon={<ArrowUp size={16} />} className="rounded-xl">Send</Button>
                  </div>
                  <p className="mt-2 px-1 text-[11px] text-slate-500">Enter to send · Shift + Enter for a new line · Nothing changes until a person approves it.</p>
                </form>
              </Card>
            </div>
          )}
        </>
      )}

      <Modal open={traceOpen} onClose={() => setTraceOpen(false)} size="lg" title="Steps and tool calls"
        description="Everything Copilot did for this conversation, in order. Each tool checked your permissions and campus."
        footer={<Button variant="secondary" onClick={() => setTraceOpen(false)}>Close</Button>}>
        {trace === null ? <TableSkeleton rows={4} /> : (
          <ol className="space-y-2 text-sm">
            {trace.map((s) => (
              <li key={s.id} className="rounded-xl border border-slate-200/80 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={s.ok ? "neutral" : "danger"}>{s.kind}</Badge>
                  <span className="font-medium text-slate-800">{s.name}</span>
                  <span className="text-xs text-slate-500">{s.duration_ms} ms</span>
                </div>
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs text-slate-500">Input and result</summary>
                  <pre className="mt-1.5 max-h-60 overflow-auto rounded-lg bg-slate-50 p-2.5 text-xs">{JSON.stringify({ input: s.input, output: s.output }, null, 2)}</pre>
                </details>
              </li>
            ))}
          </ol>
        )}
      </Modal>
    </div>
  );
}
