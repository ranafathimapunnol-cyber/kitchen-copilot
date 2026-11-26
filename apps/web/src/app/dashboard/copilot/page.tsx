"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bot, CheckCircle2, ExternalLink, ListTree, MessageSquarePlus, Send, ShieldAlert, XCircle } from "lucide-react";

import { api } from "@/lib/api/client";
import { AGENT_ENDPOINT } from "@/lib/api/endpoints";
import {
  ACTION_LABELS, EXAMPLES, WORKFLOW_LABELS, proposalLines,
  type AgentMessage, type AgentProposal, type AgentStatus, type AgentStep,
} from "@/lib/agent";
import { errorMessage, formatDateTime } from "@/lib/payments";
import Badge, { StatusBadge } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextArea } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, Spinner, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

type Conversation = { id: number; title: string; updated_at: string };
type Thread = { id: number; title: string; messages: AgentMessage[]; proposals: AgentProposal[] };

function ProposalCard({ p, onDecide }: { p: AgentProposal; onDecide: (p: AgentProposal, approve: boolean) => void }) {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4" data-proposal={p.status}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-semibold tracking-wide text-amber-800 uppercase">{ACTION_LABELS[p.action_type] ?? p.action_type} · needs a person&rsquo;s approval</p>
          <p className="mt-1 font-semibold text-slate-900">{p.title}</p>
        </div>
        <StatusBadge status={p.status} />
      </div>
      <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-slate-700">
        {proposalLines(p).map((l, i) => <li key={i}>{l}</li>)}
      </ul>
      <p className="mt-2 text-sm text-slate-600">{p.rationale}</p>
      {p.status === "PENDING" && (
        p.can_decide ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" icon={<CheckCircle2 size={15} />} onClick={() => onDecide(p, true)} data-approve>Approve and create</Button>
            <Button size="sm" variant="secondary" icon={<XCircle size={15} />} onClick={() => onDecide(p, false)}>Reject</Button>
          </div>
        ) : <p className="mt-3 text-xs text-slate-500">You can&rsquo;t approve this one; someone holding {p.required_permission} can.</p>
      )}
      {p.status === "EXECUTED" && p.result.href && (
        <p className="mt-3 text-sm text-emerald-700">
          Created {p.result.number} by {p.decided_by_name}.{" "}
          <Link className="font-medium underline" href={p.result.href}>Open</Link>
        </p>
      )}
      {p.status === "FAILED" && <p className="mt-3 text-sm text-red-700">Not created: {p.error}</p>}
      {p.status === "REJECTED" && <p className="mt-3 text-sm text-slate-600">Rejected by {p.decided_by_name}: {p.decision_note}</p>}
    </div>
  );
}

function Answer({ m, proposals, onChoice, onDecide, busy }: {
  m: AgentMessage; proposals: AgentProposal[]; onChoice: (t: string) => void;
  onDecide: (p: AgentProposal, approve: boolean) => void; busy: boolean;
}) {
  const p = m.payload;
  const mine = proposals.filter((x) => p.proposal_ids?.includes(x.id));
  return (
    <div className="flex gap-3" data-answer={p.status}>
      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-600 text-white"><Bot size={16} aria-hidden /></div>
      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          {p.workflow && <Badge tone="brand">{WORKFLOW_LABELS[p.workflow] ?? p.workflow}</Badge>}
          {p.status === "not_allowed" && <Badge tone="danger">Not allowed</Badge>}
          {p.status === "needs_info" && <Badge tone="warning">Needs a detail</Badge>}
          <span>{formatDateTime(m.created_at)}</span>
        </div>
        {p.plan && p.plan.length > 0 && p.status !== "needs_info" && (
          <details className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
            <summary className="cursor-pointer font-medium text-slate-700">How I worked on this ({p.plan.length} steps)</summary>
            <ol className="mt-2 list-decimal space-y-0.5 pl-5 text-slate-600">{p.plan.map((s, i) => <li key={i}>{s}</li>)}</ol>
          </details>
        )}
        <div className="space-y-2 text-sm leading-relaxed whitespace-pre-line text-slate-800">
          {m.content.split("\n\n").map((para, i) => <p key={i}>{para}</p>)}
        </div>
        {p.notes?.map((n, i) => <p key={i} className="text-xs text-slate-500">{n}</p>)}
        {p.blocks?.map((b, i) => b.type === "table" ? (
          <Card key={i} className="overflow-hidden">
            <p className="border-b border-slate-100 px-4 py-2 text-sm font-semibold text-slate-800">{b.title}</p>
            <Table minWidth="560px">
              <THead><TR>{b.columns.map((c) => <TH key={c}>{c}</TH>)}</TR></THead>
              <TBody>{b.rows.map((r, j) => <TR key={j}>{r.map((v, k) => <TD key={k} className="text-sm">{v}</TD>)}</TR>)}</TBody>
            </Table>
            {b.note && <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">{b.note}</p>}
          </Card>
        ) : (
          <div key={i} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
            <p className="font-semibold text-slate-800">{b.title}</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-slate-700">{b.items.map((t, j) => <li key={j}>{t}</li>)}</ul>
          </div>
        ))}
        {p.sources && p.sources.length > 0 && (
          <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
            <p className="font-semibold text-slate-800">Approved procedures</p>
            {p.sources.map((s) => <p key={s.source} className="mt-1 text-slate-600"><span className="font-medium">{s.title}</span> ({s.source}): {s.excerpt}</p>)}
          </div>
        )}
        {mine.map((x) => <ProposalCard key={x.id} p={x} onDecide={onDecide} />)}
        {p.links && p.links.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {p.links.map((l) => (
              <Link key={l.href + l.label} href={l.href} className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-brand-700 hover:bg-brand-50">
                {l.label} <ExternalLink size={12} aria-hidden />
              </Link>
            ))}
          </div>
        )}
        {p.choices && p.choices.length > 0 && (
          <div className="flex flex-wrap gap-2" data-choices>
            {p.choices.map((c) => (
              <button key={c.label} type="button" disabled={busy} onClick={() => onChoice(c.text)}
                className="rounded-full border border-brand-200 bg-brand-50 px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-100 disabled:opacity-50">
                {c.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Stage 12: Kitchen Copilot. Chat, reasoning steps, proposals and human approval. */
export default function CopilotPage() {
  const toast = useToast();
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [statusError, setStatusError] = useState("");
  const [tab, setTab] = useState<"chat" | "proposals">("chat");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [thread, setThread] = useState<Thread | null>(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [decision, setDecision] = useState<{ p: AgentProposal; approve: boolean } | null>(null);
  const [note, setNote] = useState("");
  const [deciding, setDeciding] = useState(false);
  const [trace, setTrace] = useState<AgentStep[] | null>(null);
  const [traceOpen, setTraceOpen] = useState(false);
  const [queue, setQueue] = useState<AgentProposal[] | null>(null);
  const [queueKey, setQueueKey] = useState(0);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<AgentStatus>(`${AGENT_ENDPOINT}/status`)
      .then((s) => {
        setStatus(s);
        if (s.enabled) api.get<{ items: Conversation[] }>(`${AGENT_ENDPOINT}/conversations`).then((r) => setConversations(r.items)).catch(() => undefined);
      })
      .catch((err: unknown) => setStatusError(errorMessage(err, "Unable to reach Kitchen Copilot.")));
  }, []);

  useEffect(() => {
    if (tab !== "proposals" || !status?.enabled) return;
    let active = true;
    api.get<{ items: AgentProposal[] }>(`${AGENT_ENDPOINT}/proposals`)
      .then((r) => active && setQueue(r.items))
      .catch((err: unknown) => { if (active) { setQueue([]); toast.error(errorMessage(err, "Unable to load proposals.")); } });
    return () => { active = false; };
  }, [tab, status?.enabled, queueKey, toast]);

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [thread?.messages.length]);

  function openConversation(id: number) {
    api.get<Thread>(`${AGENT_ENDPOINT}/conversations/${id}`).then(setThread)
      .catch((err: unknown) => toast.error(errorMessage(err, "Unable to open the conversation.")));
    setTab("chat");
  }

  async function send(message: string) {
    const body = message.trim();
    if (body.length < 2 || sending) return;
    setSending(true);
    const pending: AgentMessage = { id: -1, role: "user", content: body, payload: {}, created_at: new Date().toISOString() };
    setThread((t) => t ? { ...t, messages: [...t.messages, pending] } : { id: 0, title: body, messages: [pending], proposals: [] });
    setText("");
    try {
      const r = await api.post<{ conversation_id: number; title: string; question: AgentMessage; answer: AgentMessage; proposals: AgentProposal[] }>(
        `${AGENT_ENDPOINT}/messages`, { text: body, conversation_id: thread?.id || null });
      setThread((t) => ({
        id: r.conversation_id, title: r.title,
        messages: [...(t?.messages ?? []).filter((m) => m.id !== -1), r.question, r.answer],
        proposals: [...(t?.proposals ?? []), ...r.proposals],
      }));
      setConversations((list) => [{ id: r.conversation_id, title: r.title, updated_at: r.answer.created_at },
        ...list.filter((c) => c.id !== r.conversation_id)]);
    } catch (err) {
      setThread((t) => t ? { ...t, messages: t.messages.filter((m) => m.id !== -1) } : null);
      setText(body);
      toast.error(errorMessage(err, "Kitchen Copilot could not answer."));
    } finally {
      setSending(false);
    }
  }

  async function decide() {
    if (!decision) return;
    setDeciding(true);
    try {
      const updated = await api.post<AgentProposal>(
        `${AGENT_ENDPOINT}/proposals/${decision.p.id}/${decision.approve ? "approve" : "reject"}`,
        decision.approve ? { note: note.trim() || null } : { reason: note.trim() });
      setThread((t) => t ? { ...t, proposals: t.proposals.map((x) => x.id === updated.id ? updated : x) } : t);
      setQueue((q) => q ? q.map((x) => x.id === updated.id ? updated : x) : q);
      if (updated.status === "EXECUTED") toast.success(`Created ${updated.result.number ?? ""}. It stays a draft until you finish it on its screen.`);
      else if (updated.status === "FAILED") toast.error(`Not created: ${updated.error}`);
      else toast.success("Proposal rejected.");
      setDecision(null);
    } catch (err) {
      toast.error(errorMessage(err, "The decision could not be saved."));
      setQueueKey((n) => n + 1);
    } finally {
      setDeciding(false);
    }
  }

  function showTrace() {
    if (!thread?.id) return;
    setTrace(null);
    setTraceOpen(true);
    api.get<{ items: AgentStep[] }>(`${AGENT_ENDPOINT}/conversations/${thread.id}/trace`).then((r) => setTrace(r.items))
      .catch((err: unknown) => { setTrace([]); toast.error(errorMessage(err, "Unable to load the steps.")); });
  }

  const onDecide = (p: AgentProposal, approve: boolean) => { setNote(""); setDecision({ p, approve }); };

  if (statusError) return <ErrorState message={statusError} />;
  if (!status) return <TableSkeleton rows={4} />;

  return (
    <div className="space-y-6">
      <PageHeader icon={Bot} eyebrow="Assistant" title="Kitchen Copilot"
        description="Ask in plain words. Copilot reads your campus records through permission-checked tools, shows its working, and prepares actions that only take effect when a person approves them."
        meta={status.enabled ? (
          <span className="text-xs text-slate-500">
            {status.reader === "gemini" ? `Language model: ${status.external_model}` : "Built-in request reader (no external AI)"} · Figures always come from the application
          </span>) : undefined}
      />

      {!status.enabled ? (
        <EmptyState icon={ShieldAlert} title="Kitchen Copilot is turned off"
          description="An administrator can turn it on with the AGENT_ENABLED setting. Every other screen works normally while it is off." />
      ) : (
        <>
          <SegmentedControl label="View" value={tab} onChange={setTab} options={[{ value: "chat", label: "Conversation" }, { value: "proposals", label: "Proposals to review" }]} />

          {tab === "proposals" ? (
            queue === null ? <TableSkeleton rows={3} /> : queue.length === 0 ? (
              <EmptyState title="No proposals" description="Proposals Copilot prepares for you, or that you may approve, appear here." />
            ) : (
              <div className="grid gap-3 lg:grid-cols-2" data-queue>
                {queue.map((p) => (
                  <div key={p.id} className="space-y-1">
                    <p className="text-xs text-slate-500">{WORKFLOW_LABELS[p.workflow]} · asked by {p.created_by_name} · {formatDateTime(p.created_at)}</p>
                    <ProposalCard p={p} onDecide={onDecide} />
                  </div>
                ))}
              </div>
            )
          ) : (
            <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
              <Card className="hidden h-fit p-3 lg:block">
                <Button variant="secondary" size="sm" className="w-full" icon={<MessageSquarePlus size={15} />} onClick={() => setThread(null)}>New conversation</Button>
                <ul className="mt-3 space-y-1 text-sm">
                  {conversations.map((c) => (
                    <li key={c.id}>
                      <button type="button" onClick={() => openConversation(c.id)}
                        className={`w-full truncate rounded-lg px-2 py-1.5 text-left hover:bg-slate-100 ${thread?.id === c.id ? "bg-brand-50 font-medium text-brand-800" : "text-slate-700"}`}>
                        {c.title}
                      </button>
                    </li>
                  ))}
                  {conversations.length === 0 && <li className="px-2 text-xs text-slate-500">No conversations yet.</li>}
                </ul>
              </Card>

              <Card className="flex min-h-[60vh] flex-col">
                <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-2.5">
                  <p className="truncate text-sm font-semibold text-slate-800">{thread?.title ?? "New conversation"}</p>
                  <div className="flex shrink-0 gap-1">
                    {thread?.id ? <Button variant="ghost" size="sm" icon={<ListTree size={15} />} onClick={showTrace}>Steps</Button> : null}
                    <Button variant="ghost" size="sm" className="lg:hidden" icon={<MessageSquarePlus size={15} />} onClick={() => setThread(null)}>New</Button>
                  </div>
                </div>
                <div className="flex-1 space-y-6 overflow-y-auto p-4" data-thread>
                  {!thread || thread.messages.length === 0 ? (
                    <div className="mx-auto max-w-xl space-y-3 py-6 text-center">
                      <p className="text-sm text-slate-600">Try one of the three jobs Copilot can do:</p>
                      <div className="grid gap-2">
                        {EXAMPLES.map((e) => (
                          <button key={e.label} type="button" disabled={sending || !status.workflows[e.label === "Plan and procure" ? "plan_procure" : e.label === "Explain spending" ? "explain_spending" : "stock_difference"]}
                            onClick={() => send(e.text)}
                            className="rounded-xl border border-slate-200 bg-white p-3 text-left text-sm hover:border-brand-300 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-50">
                            <span className="font-semibold text-slate-800">{e.label}</span>
                            <span className="mt-0.5 block text-slate-600">{e.text}</span>
                          </button>
                        ))}
                      </div>
                      <p className="text-xs text-slate-500">Greyed-out jobs need permissions you don&rsquo;t have.</p>
                    </div>
                  ) : thread.messages.map((m) => m.role === "user" ? (
                    <div key={m.id} className="flex justify-end">
                      <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-brand-600 px-4 py-2 text-sm text-white">{m.content}</p>
                    </div>
                  ) : (
                    <Answer key={m.id} m={m} proposals={thread.proposals} onChoice={send} onDecide={onDecide} busy={sending} />
                  ))}
                  {sending && <Spinner label="Working through your records…" className="justify-start" />}
                  <div ref={end} />
                </div>
                <form className="flex items-end gap-2 border-t border-slate-100 p-3" onSubmit={(e) => { e.preventDefault(); send(text); }}>
                  <label htmlFor="copilot-input" className="sr-only">Message</label>
                  <textarea id="copilot-input" rows={2} value={text} maxLength={1000} onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
                    placeholder="Ask Kitchen Copilot…" className="min-h-11 flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-100 focus:outline-none" />
                  <Button type="submit" loading={sending} disabled={text.trim().length < 2} icon={<Send size={16} />}>Send</Button>
                </form>
              </Card>
            </div>
          )}
        </>
      )}

      <Modal open={decision !== null} onClose={() => !deciding && setDecision(null)} size="sm"
        title={decision?.approve ? "Approve this action?" : "Reject this proposal?"}
        description={decision?.p.title}
        footer={<>
          <Button variant="secondary" onClick={() => setDecision(null)} disabled={deciding}>Cancel</Button>
          <Button variant={decision?.approve ? "primary" : "danger"} loading={deciding}
            disabled={!decision?.approve && note.trim().length < 3} onClick={decide}>
            {decision?.approve ? "Approve and create" : "Reject"}
          </Button>
        </>}>
        <div className="space-y-3 text-sm">
          {decision?.approve && (
            <p className="text-slate-600">Your permission is checked again now. The record is created through the normal application rules and recorded in the audit log under your name. It is saved as a draft or request; nothing is posted to stock or sent to a supplier.</p>
          )}
          <Field label={decision?.approve ? "Note (optional)" : "Reason"} required={!decision?.approve}>
            {({ id }) => <TextArea id={id} rows={3} value={note} onChange={(e) => setNote(e.target.value)} data-autofocus />}
          </Field>
        </div>
      </Modal>

      <Modal open={traceOpen} onClose={() => setTraceOpen(false)} size="lg" title="Steps and tool calls"
        description="Everything Copilot did for this conversation, in order. Each tool checked your permissions and campus."
        footer={<Button variant="secondary" onClick={() => setTraceOpen(false)}>Close</Button>}>
        {trace === null ? <TableSkeleton rows={4} /> : (
          <ol className="space-y-2 text-sm">
            {trace.map((s) => (
              <li key={s.id} className="rounded-lg border border-slate-200 p-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={s.ok ? "neutral" : "danger"}>{s.kind}</Badge>
                  <span className="font-medium text-slate-800">{s.name}</span>
                  <span className="text-xs text-slate-500">{s.duration_ms} ms</span>
                </div>
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs text-slate-500">Input and result</summary>
                  <pre className="mt-1 max-h-60 overflow-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify({ input: s.input, output: s.output }, null, 2)}</pre>
                </details>
              </li>
            ))}
          </ol>
        )}
      </Modal>
    </div>
  );
}
