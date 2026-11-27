"use client";

import { useState } from "react";

import { formatDateTime } from "@/lib/payments";
import { ACTION_LABELS, PLATFORM_API, query, type AuditRow } from "@/lib/platform";
import Badge from "@/components/ui/Badge";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import Pagination from "@/components/ui/Pagination";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { PlatformHeader, usePlatformGet } from "@/components/platform/parts";

const OUTCOME_TONE = { SUCCESS: "success", FAILURE: "danger", DENIED: "warning" } as const;

/** The append-only platform audit log: sign-ins and sensitive actions. */
export default function PlatformAuditPage() {
  const [filters, setFilters] = useState({ action: "", outcome: "", campus_id: "", date_from: "", date_to: "" });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const { data, error, reload } = usePlatformGet<{ items: AuditRow[]; total: number }>(
    `${PLATFORM_API}/audit${query({ ...filters, page, page_size: pageSize })}`);
  const { data: campuses } = usePlatformGet<{ items: { id: number; name: string }[] }>(`${PLATFORM_API}/campuses`);
  const names = Object.fromEntries((campuses?.items ?? []).map((c) => [c.id, c.name]));
  const set = (key: keyof typeof filters) => (e: { target: { value: string } }) => { setFilters({ ...filters, [key]: e.target.value }); setPage(1); };

  return (
    <div className="space-y-6">
      <PlatformHeader eyebrow="Organisation" title="Platform audit log"
        description="Every platform sign-in attempt and sensitive action: who, what, when, the target and the outcome. Entries cannot be changed or deleted." />
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Action" className="w-52">{({ id }) => (
          <SelectInput id={id} value={filters.action} onChange={set("action")}>
            <option value="">All actions</option>{Object.entries(ACTION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </SelectInput>)}</Field>
        <Field label="Outcome" className="w-40">{({ id }) => (
          <SelectInput id={id} value={filters.outcome} onChange={set("outcome")}>
            <option value="">Any</option><option value="SUCCESS">Success</option><option value="FAILURE">Failure</option><option value="DENIED">Refused</option>
          </SelectInput>)}</Field>
        <Field label="Campus" className="w-52">{({ id }) => (
          <SelectInput id={id} value={filters.campus_id} onChange={set("campus_id")}>
            <option value="">All</option>{campuses?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </SelectInput>)}</Field>
        <Field label="From" className="w-40">{({ id }) => <TextInput id={id} type="date" value={filters.date_from} onChange={set("date_from")} />}</Field>
        <Field label="To" className="w-40">{({ id }) => <TextInput id={id} type="date" value={filters.date_to} onChange={set("date_to")} />}</Field>
      </div>
      {error ? <ErrorState message={error} onRetry={reload} /> : !data ? <TableSkeleton rows={8} /> : data.items.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white"><EmptyState title="No entries match" /></div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white" data-audit-list>
          <Table minWidth="900px">
            <THead><TR><TH>When</TH><TH>Who</TH><TH>Action</TH><TH>Target</TH><TH>Outcome</TH><TH>Details</TH></TR></THead>
            <TBody>{data.items.map((a) => (
              <TR key={a.id}>
                <TD className="text-sm whitespace-nowrap">{formatDateTime(a.occurred_at)}</TD>
                <TD className="text-sm">{a.actor_email ?? "—"}<span className="block text-xs text-slate-500">{a.ip_address ?? ""}</span></TD>
                <TD className="font-medium">{ACTION_LABELS[a.action] ?? a.action}</TD>
                <TD className="text-sm">{a.target_type.toLowerCase().replaceAll("_", " ")}{a.campus_id ? ` · ${names[a.campus_id] ?? `#${a.campus_id}`}` : ""}</TD>
                <TD><Badge tone={OUTCOME_TONE[a.outcome]}>{a.outcome.toLowerCase()}</Badge></TD>
                <TD className="max-w-[22rem] text-xs break-words text-slate-600">{Object.keys(a.details).length ? JSON.stringify(a.details) : "—"}</TD>
              </TR>))}</TBody>
          </Table>
          <Pagination page={page} pageCount={Math.max(1, Math.ceil(data.total / pageSize))} total={data.total} pageSize={pageSize}
            onPageChange={setPage} noun="entries" pageSizeOptions={[25, 50, 100]} onPageSizeChange={(s) => { setPageSize(s); setPage(1); }} />
        </div>
      )}
    </div>
  );
}
