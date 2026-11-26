"use client";

import { Fragment, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, ScrollText } from "lucide-react";

import { api } from "@/lib/api/client";
import { AUDIT_ENDPOINT, AUDIT_OPTIONS_ENDPOINT } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime } from "@/lib/payments";
import Badge, { humanize } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type Entry = {
  id: number; created_at: string; action: string; entity_type: string; entity_id: number | null;
  user_id: number | null; user_name: string | null; details: Record<string, unknown>;
};
type Page = { items: Entry[]; total: number; page: number; page_size: number; financial_values: boolean };
type Options = { actions: string[]; entity_types: string[]; users: { id: number; name: string }[] };

const EMPTY = { date_from: "", date_to: "", action: "", entity_type: "", user_id: "", entity_id: "" };

function Details({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <span className="text-slate-400">—</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-slate-400">none</span>;
    return (
      <ol className="list-decimal space-y-1 pl-5">
        {value.map((v, i) => <li key={i}><Details value={v} /></li>)}
      </ol>
    );
  }
  if (typeof value === "object") {
    return (
      <dl className="grid grid-cols-[minmax(110px,auto)_1fr] gap-x-3 gap-y-1">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <Fragment key={k}>
            <dt className="text-slate-500">{humanize(k)}</dt>
            <dd className="min-w-0 break-words text-slate-800">
              {v === "hidden" ? <Badge tone="neutral">Hidden</Badge> : <Details value={v} />}
            </dd>
          </Fragment>
        ))}
      </dl>
    );
  }
  return <>{String(value)}</>;
}

/** Stage 10: the audit viewer (audit.read). Read-only; money is hidden without supplier-bill access. */
export default function AuditPage() {
  const [filters, setFilters] = useState(EMPTY);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [error, setError] = useState("");
  const [loadedUrl, setLoadedUrl] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    api.get<Options>(AUDIT_OPTIONS_ENDPOINT).then(setOptions).catch(() => undefined);
  }, []);

  const params = new URLSearchParams({ page: String(page), page_size: "50" });
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
  const invalid = filters.date_from && filters.date_to && filters.date_from > filters.date_to;
  const url = invalid ? "" : `${AUDIT_ENDPOINT}?${params}#${retry}`;
  const loading = Boolean(url) && loadedUrl !== url;

  useEffect(() => {
    if (!url) return;
    let active = true;
    api.get<Page>(url.split("#")[0])
      .then((r) => { if (active) { setData(r); setError(""); } })
      .catch((err: unknown) => { if (active) setError(errorMessage(err, "Unable to load the audit log.")); })
      .finally(() => active && setLoadedUrl(url));
    return () => { active = false; };
  }, [url]);

  const set = (key: keyof typeof EMPTY, value: string) => { setFilters((f) => ({ ...f, [key]: value })); setPage(1); };

  return (
    <div className="space-y-6">
      <PageHeader icon={ScrollText} eyebrow="Administration" title="Audit Log"
        description="Every recorded change on your campus: who did what, when, and the details kept with it. Entries cannot be edited or deleted." />

      <Card className="p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <Field label="From">{({ id }) => <TextInput id={id} type="date" value={filters.date_from} onChange={(e) => set("date_from", e.target.value)} />}</Field>
          <Field label="To" error={invalid ? "The start must be on or before the end." : undefined}>
            {({ id }) => <TextInput id={id} type="date" value={filters.date_to} onChange={(e) => set("date_to", e.target.value)} />}
          </Field>
          <Field label="Record type">{({ id }) => (
            <SelectInput id={id} value={filters.entity_type} onChange={(e) => set("entity_type", e.target.value)}>
              <option value="">All</option>
              {options?.entity_types.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
            </SelectInput>)}
          </Field>
          <Field label="Action">{({ id }) => (
            <SelectInput id={id} value={filters.action} onChange={(e) => set("action", e.target.value)}>
              <option value="">All</option>
              {options?.actions.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
            </SelectInput>)}
          </Field>
          <Field label="Person">{({ id }) => (
            <SelectInput id={id} value={filters.user_id} onChange={(e) => set("user_id", e.target.value)}>
              <option value="">Anyone</option>
              {options?.users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </SelectInput>)}
          </Field>
          <Field label="Record number">{({ id }) => (
            <TextInput id={id} inputMode="numeric" value={filters.entity_id} placeholder="e.g. 42"
              onChange={(e) => set("entity_id", e.target.value.replace(/\D/g, ""))} />)}
          </Field>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
          <span>{data ? `${data.total} entr${data.total === 1 ? "y" : "ies"}` : " "}
            {data && !data.financial_values && " · amounts are hidden (needs supplier-bill access)"}</span>
          <Button variant="ghost" size="sm" onClick={() => { setFilters(EMPTY); setPage(1); }}>Clear filters</Button>
        </div>
      </Card>

      {error ? <ErrorState message={error} onRetry={() => setRetry((n) => n + 1)} /> :
        data === null ? <TableSkeleton rows={6} /> :
        data.items.length === 0 ? <EmptyState title="No entries" description="Nothing matches these filters." /> : (
          <Card className={loading ? "opacity-60" : undefined} data-audit>
            <Table minWidth="720px">
              <THead><TR><TH className="w-8"><span className="sr-only">Expand</span></TH><TH>When</TH><TH>Person</TH><TH>Action</TH><TH>Record</TH></TR></THead>
              <TBody>
                {data.items.map((e) => (
                  <Fragment key={e.id}>
                    <TR>
                      <TD>
                        <button type="button" aria-expanded={open === e.id} aria-label="Show details"
                          className="rounded p-1 text-slate-500 hover:bg-slate-100" onClick={() => setOpen(open === e.id ? null : e.id)}>
                          {open === e.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        </button>
                      </TD>
                      <TD className="whitespace-nowrap text-sm">{formatDateTime(e.created_at)}</TD>
                      <TD className="text-sm">{e.user_name ?? "System"}</TD>
                      <TD><Badge tone={e.action.includes("DELETE") || e.action.includes("REJECT") || e.action.includes("FAIL") ? "danger" : e.action.includes("APPROVE") || e.action === "EXECUTED" ? "success" : "neutral"}>{humanize(e.action)}</Badge></TD>
                      <TD className="text-sm">{humanize(e.entity_type)}{e.entity_id ? ` #${e.entity_id}` : ""}</TD>
                    </TR>
                    {open === e.id && (
                      <TR><TD colSpan={5} className="bg-slate-50 text-sm"><Details value={e.details} /></TD></TR>
                    )}
                  </Fragment>
                ))}
              </TBody>
            </Table>
            <div className="border-t border-slate-100 px-4 py-3">
              <Pagination page={data.page} pageCount={Math.max(1, Math.ceil(data.total / data.page_size))} pageSize={data.page_size} total={data.total} onPageChange={setPage} noun="entries" />
            </div>
          </Card>
        )}
    </div>
  );
}
