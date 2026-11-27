"use client";

import Link from "next/link";
import { CheckCircle2, ClipboardSignature, Database, ExternalLink, ListTree, XCircle } from "lucide-react";

import {
  ACTION_LABELS, TOOL_LABELS, WORKFLOW_LABELS, proposalLines,
  type AgentMessage, type AgentProposal,
} from "@/lib/agent";
import { formatDateTime } from "@/lib/payments";
import Badge, { StatusBadge } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { cn } from "@/components/ui/cn";

export type Decide = (p: AgentProposal, approve: boolean) => void;

/** The Copilot mark: a speech bubble holding a lime spark. */
export function CopilotMark({ size = 22, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      <path d="M4.5 5.5A2.5 2.5 0 0 1 7 3h10a2.5 2.5 0 0 1 2.5 2.5v8A2.5 2.5 0 0 1 17 16h-5.2l-4.1 3.6c-.5.4-1.2.1-1.2-.6V16H7a2.5 2.5 0 0 1-2.5-2.5z"
        stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M12 5.8l.95 2.55 2.55.95-2.55.95L12 12.8l-.95-2.55-2.55-.95 2.55-.95z" fill="#d9f18d" stroke="currentColor"
        strokeWidth="0.7" strokeLinejoin="round" />
    </svg>
  );
}

const STATUS_RAIL: Record<string, string> = {
  PENDING: "bg-amber-500", EXECUTING: "bg-amber-500", EXECUTED: "bg-emerald-600", REJECTED: "bg-slate-400",
};

export function ProposalCard({ p, onDecide, compact = false }: { p: AgentProposal; onDecide: Decide; compact?: boolean }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs" data-proposal={p.status}>
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", STATUS_RAIL[p.status] ?? "bg-red-600")} />
      <div className={cn("flex flex-wrap items-start justify-between gap-2 border-b border-dashed border-slate-200 bg-slate-50/70 py-3 pr-4", compact ? "pl-4" : "pl-5")}>
        <div className="flex min-w-0 items-start gap-3">
          {!compact && (
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-brand-700 ring-1 ring-slate-200">
              <ClipboardSignature size={16} aria-hidden />
            </span>
          )}
          <div className="min-w-0">
            <p className="text-[10.5px] font-semibold tracking-[0.12em] text-slate-500 uppercase">
              {ACTION_LABELS[p.action_type] ?? p.action_type} · needs a person&rsquo;s approval
            </p>
            <p className="mt-0.5 font-semibold text-slate-900">{p.title}</p>
          </div>
        </div>
        <StatusBadge status={p.status} />
      </div>
      <div className={cn("py-3.5 pr-4", compact ? "pl-4" : "pl-5")}>
        <ul className="list-disc space-y-0.5 pl-5 text-sm text-slate-700 marker:text-slate-400">
          {proposalLines(p).map((l, i) => <li key={i}>{l}</li>)}
        </ul>
        <p className="mt-2.5 text-sm leading-relaxed text-slate-600">{p.rationale}</p>
        {p.status === "PENDING" && (
          p.can_decide ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" icon={<CheckCircle2 size={15} />} onClick={() => onDecide(p, true)} data-approve>Approve and create</Button>
              <Button size="sm" variant="secondary" icon={<XCircle size={15} />} onClick={() => onDecide(p, false)}>Reject</Button>
            </div>
          ) : <p className="mt-3 text-xs text-slate-500">Waiting for someone holding {p.required_permission} to approve it. Copilot never approves its own proposals.</p>
        )}
        {p.status === "EXECUTING" && <p className="mt-3 text-sm text-amber-700">Being created…</p>}
        {p.status === "EXECUTED" && p.result.href && (
          <p className="mt-3 text-sm text-emerald-700">
            Created {p.result.number} by {p.decided_by_name}.{" "}
            <Link className="font-medium underline" href={p.result.href}>Open</Link>
          </p>
        )}
        {p.status === "FAILED" && <p className="mt-3 text-sm text-red-700">Not created: {p.error}</p>}
        {p.status === "REJECTED" && <p className="mt-3 text-sm text-slate-600">Rejected by {p.decided_by_name}: {p.decision_note}</p>}
        {p.status === "EXPIRED" && <p className="mt-3 text-sm text-slate-600">Expired without a decision. Ask again to prepare a fresh one.</p>}
      </div>
    </div>
  );
}

/** "Checked: Operations overview ✓ · …": the permission-checked reads of a turn. */
export function ToolLine({ tools }: { tools: { name: string; ok: boolean }[] }) {
  if (tools.length === 0) return null;
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500" data-tools>
      <Database size={13} aria-hidden className="shrink-0" />
      <span>Checked</span>
      {tools.map((t, i) => (
        <span key={`${t.name}-${i}`} className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 ring-1 ring-inset",
          t.ok ? "bg-white text-slate-700 ring-slate-200" : "bg-red-50 text-red-700 ring-red-200")}>
          {TOOL_LABELS[t.name] ?? t.name}
          {t.ok ? <CheckCircle2 size={11} aria-label="done" className="text-emerald-600" /> : <XCircle size={11} aria-label="refused" />}
        </span>
      ))}
    </p>
  );
}

export function Answer({ m, proposals, onChoice, onDecide, busy, compact = false }: {
  m: AgentMessage; proposals: AgentProposal[]; onChoice: (t: string) => void;
  onDecide: Decide; busy: boolean; compact?: boolean;
}) {
  const p = m.payload;
  const mine = proposals.filter((x) => p.proposal_ids?.includes(x.id));
  return (
    <div className="flex gap-3" data-answer={p.status}>
      {!compact && (
        <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white">
          <CopilotMark size={18} />
        </div>
      )}
      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          {p.workflow && <Badge tone="brand">{WORKFLOW_LABELS[p.workflow] ?? p.workflow}</Badge>}
          {p.status === "not_allowed" && <Badge tone="danger">Not allowed</Badge>}
          {p.status === "needs_info" && <Badge tone="warning">Needs a detail</Badge>}
          {p.status === "error" && <Badge tone="danger">Stopped</Badge>}
          <span>{formatDateTime(m.created_at)}</span>
        </div>
        {p.tools && p.tools.length > 0 && <ToolLine tools={p.tools} />}
        {p.plan && p.plan.length > 0 && p.status !== "needs_info" && (
          <details className="group rounded-xl border border-slate-200 bg-slate-50/70 px-3.5 py-2.5 text-sm">
            <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-slate-700">
              <ListTree size={15} aria-hidden className="text-slate-500" /> How I worked on this ({p.plan.length} steps)
            </summary>
            <ol className="mt-2.5 space-y-1.5 text-slate-600">
              {p.plan.map((s, i) => (
                <li key={i} className="flex gap-2.5">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200">{i + 1}</span>
                  <span>{s}</span>
                </li>
              ))}
            </ol>
          </details>
        )}
        <div className={cn("space-y-2 rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3.5 leading-relaxed whitespace-pre-line text-slate-800",
          compact ? "text-sm" : "text-[14.5px]")}>
          {m.content.split("\n\n").map((para, i) => <p key={i}>{para}</p>)}
        </div>
        {p.notes?.map((n, i) => <p key={i} className="text-xs text-slate-500">{n}</p>)}
        {p.blocks?.map((b, i) => b.type === "table" ? (
          <Card key={i} className="overflow-hidden">
            <p className="border-b border-slate-100 px-4 py-2.5 text-sm font-semibold text-slate-800">{b.title}</p>
            <Table minWidth={compact ? "480px" : "560px"}>
              <THead><TR>{b.columns.map((c) => <TH key={c}>{c}</TH>)}</TR></THead>
              <TBody>{b.rows.map((r, j) => <TR key={j}>{r.map((v, k) => <TD key={k} className="text-sm">{v}</TD>)}</TR>)}</TBody>
            </Table>
            {b.note && <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">{b.note}</p>}
          </Card>
        ) : (
          <div key={i} className="rounded-xl border border-slate-200 bg-white p-4 text-sm" data-block={b.title}>
            <p className="font-semibold text-slate-800">{b.title}</p>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-700 marker:text-slate-400">{b.items.map((t, j) => <li key={j}>{t}</li>)}</ul>
          </div>
        ))}
        {p.sources && p.sources.length > 0 && (
          <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
            <p className="font-semibold text-slate-800">Approved procedures</p>
            {p.sources.map((s) => <p key={s.source} className="mt-1 text-slate-600"><span className="font-medium">{s.title}</span> ({s.source}): {s.excerpt}</p>)}
          </div>
        )}
        {mine.map((x) => <ProposalCard key={x.id} p={x} onDecide={onDecide} compact={compact} />)}
        {p.links && p.links.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {p.links.map((l) => (
              <Link key={l.href + l.label} href={l.href} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-800 transition-colors hover:border-slate-400">
                {l.label} <ExternalLink size={12} aria-hidden />
              </Link>
            ))}
          </div>
        )}
        {p.choices && p.choices.length > 0 && (
          <div className="flex flex-wrap gap-2" data-choices>
            {p.choices.map((c) => (
              <button key={c.label} type="button" disabled={busy} onClick={() => onChoice(c.text)}
                className="rounded-full border border-slate-300 bg-white px-3.5 py-1.5 text-sm font-medium text-slate-800 transition-colors hover:border-slate-900 disabled:opacity-50">
                {c.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Three pulsing dots with what Copilot is doing. */
export function Thinking({ label = "Checking your records…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2.5 text-sm text-slate-500" data-thinking>
      <span className="flex gap-1" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: `${i * 140}ms` }} />
        ))}
      </span>
      {label}
    </div>
  );
}
