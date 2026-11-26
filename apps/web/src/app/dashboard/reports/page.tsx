"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, BarChart3, FileDown, FileSpreadsheet, Printer } from "lucide-react";

import { api, apiDownload } from "@/lib/api/client";
import { REPORT_CATALOG_ENDPOINT, REPORT_LOOKUPS_ENDPOINT, reportEndpoint, reportExportEndpoint } from "@/lib/api/endpoints";
import type { CatalogEntry, CompareMode, ReportColumn, ReportData } from "@/lib/analytics";
import { periodError, presetPeriod, type Preset } from "@/lib/outsourcedMath";
import { errorMessage, formatDay, formatRupees } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import SearchSelect from "@/components/ui/SearchSelect";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, Spinner, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

type Lists = { categories: { id: number; name: string }[]; items: { id: number; name: string; category_id?: number }[];
  suppliers: { id: number; name: string }[]; sessions: { id: number; name: string }[] };

function cell(column: ReportColumn, row: Record<string, string | number | null>) {
  const value = row[column.key];
  if (value === null || value === undefined || value === "") return <span className="text-slate-400">—</span>;
  if (column.kind === "money") return formatRupees(value);
  if (column.kind === "percent") return `${value}%`;
  if (column.kind === "date") return formatDay(String(value));
  if (column.kind === "qty") return `${plainQuantity(String(value))} ${column.unit_key ? row[column.unit_key] ?? "" : ""}`.trim();
  return String(value);
}

function totalText(t: ReportData["totals"][number]) {
  if (t.value === null) return t.kind === "percent" ? "Not comparable" : "—";
  if (t.kind === "money") return formatRupees(t.value);
  if (t.kind === "percent") return `${t.value}%`;
  if (t.kind === "qty") return `${plainQuantity(t.value)} ${t.unit ?? ""}`.trim();
  return t.value;
}

/** Stage 9 reports (PROPOSAL.md §5.8): one screen for every tabular report, with Excel, PDF and print. */
export default function ReportsPage() {
  const toast = useToast();
  const [catalog, setCatalog] = useState<CatalogEntry[] | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [selected, setSelected] = useState("");
  const [preset, setPreset] = useState<Preset>("month");
  const [period, setPeriod] = useState(() => presetPeriod("month", new Date()));
  const [filters, setFilters] = useState({ supplier: "", category: "", item: "", session: "" });
  const [compare, setCompare] = useState<CompareMode>("elapsed");
  const [lists, setLists] = useState<Lists>({ categories: [], items: [], suppliers: [], sessions: [] });
  const [report, setReport] = useState<ReportData | null>(null);
  const [error, setError] = useState("");
  const [loadedUrl, setLoadedUrl] = useState("");
  const [exporting, setExporting] = useState<"xlsx" | "pdf" | null>(null);

  useEffect(() => {
    api.get<{ items: CatalogEntry[] }>(REPORT_CATALOG_ENDPOINT)
      .then((r) => { setCatalog(r.items); const first = r.items.find((i) => !i.href); if (first) setSelected(first.key); })
      .catch((err: unknown) => setCatalogError(errorMessage(err, "Unable to load the reports.")));
    api.get<Omit<Lists, "sessions"> & { meal_sessions: Lists["sessions"] }>(REPORT_LOOKUPS_ENDPOINT)
      .then((o) => setLists({ categories: o.categories, items: o.items, suppliers: o.suppliers, sessions: o.meal_sessions }))
      .catch(() => undefined);
  }, []);

  const entry = catalog?.find((c) => c.key === selected) ?? null;
  const wants = (f: string) => Boolean(entry?.filters.includes(f as never));
  const invalid = wants("period") ? periodError(period.from, period.to) : undefined;
  const query = new URLSearchParams();
  if (entry && !entry.href) {
    if (entry.filters.includes("period")) { query.set("date_from", period.from); query.set("date_to", period.to); }
    if (entry.filters.includes("supplier") && filters.supplier) query.set("supplier_id", filters.supplier);
    if (entry.filters.includes("category") && filters.category) query.set("category_id", filters.category);
    if (entry.filters.includes("item") && filters.item) query.set("item_id", filters.item);
    if (entry.filters.includes("meal_session") && filters.session) query.set("meal_session_id", filters.session);
    if (entry.filters.includes("compare")) query.set("compare", compare);
  }
  const requestUrl = entry && !entry.href && !invalid ? `${reportEndpoint(entry.key)}?${query}` : "";
  const loading = Boolean(requestUrl) && loadedUrl !== requestUrl;

  useEffect(() => {
    if (!requestUrl) return;
    let active = true;
    api.get<ReportData>(requestUrl)
      .then((r) => { if (active) { setReport(r); setError(""); } })
      .catch((err: unknown) => { if (active) { setReport(null); setError(errorMessage(err, "Unable to load the report.")); } })
      .finally(() => active && setLoadedUrl(requestUrl));
    return () => { active = false; };
  }, [requestUrl]);

  function exportReport(format: "xlsx" | "pdf") {
    if (!entry || !report) return;
    setExporting(format);
    const body: Record<string, unknown> = { format, compare };
    query.forEach((value, key) => { body[key] = key.endsWith("_id") ? Number(value) : value; });
    apiDownload(reportExportEndpoint(entry.key), body)
      .then(({ blob, filename }) => {
        const name = filename ?? `${entry.key}.${format}`;
        const href = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = href; link.download = name; document.body.appendChild(link); link.click(); link.remove();
        setTimeout(() => URL.revokeObjectURL(href), 1000);
        toast.success(`${format === "xlsx" ? "Excel" : "PDF"} file downloaded: ${name}`);
      })
      .catch((err: unknown) => toast.error(errorMessage(err, "The export could not be created.")))
      .finally(() => setExporting(null));
  }

  const groups: Record<string, CatalogEntry[]> = {};
  for (const c of catalog ?? []) (groups[c.group] ??= []).push(c);
  const items = lists.items.filter((i) => !filters.category || String(i.category_id) === filters.category);
  const canExport = Boolean(report && !loading && !error && report.key === selected);

  return (
    <div className="space-y-6 pb-6">
      <style>{"@media print { @page { size: A4 landscape; margin: 12mm; } }"}</style>
      <PageHeader eyebrow="Reports" icon={BarChart3} title="Reports"
        description="Daily, weekly, monthly and custom-period reports with their filters, quantities and units, ready for Excel, PDF or printing."
        actions={entry && !entry.href ? (
          <div className="flex flex-wrap gap-2 print:hidden">
            <Button variant="secondary" icon={<FileSpreadsheet size={15} aria-hidden />} loading={exporting === "xlsx"} disabled={!canExport || exporting !== null} onClick={() => exportReport("xlsx")}>Excel</Button>
            <Button variant="secondary" icon={<FileDown size={15} aria-hidden />} loading={exporting === "pdf"} disabled={!canExport || exporting !== null} onClick={() => exportReport("pdf")}>PDF</Button>
            <Button variant="secondary" icon={<Printer size={15} aria-hidden />} disabled={!canExport} onClick={() => window.print()}>Print</Button>
          </div>
        ) : undefined} />

      {catalogError ? <Card><ErrorState title="Couldn't load the reports" message={catalogError} /></Card>
        : !catalog ? <Card><CardBody><Spinner label="Loading reports" /></CardBody></Card>
        : catalog.length === 0 ? <Card><EmptyState icon={BarChart3} title="No reports available" description="Reports appear for the modules your account can read." /></Card> : (
          <>
            <Card className="print:hidden">
              <CardBody className="space-y-4">
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
                  <Field label="Report">
                    {({ id }) => (
                      <SelectInput id={id} value={selected} onChange={(e) => { if (e.target.value !== selected) { setSelected(e.target.value); setReport(null); } }} data-report-select>
                        {Object.entries(groups).map(([group, entries]) => (
                          <optgroup key={group} label={group}>
                            {entries.map((c) => <option key={c.key} value={c.key}>{c.title}{c.href ? " (own screen)" : ""}</option>)}
                          </optgroup>
                        ))}
                      </SelectInput>
                    )}
                  </Field>
                  <p className="self-end text-sm text-slate-600">{entry?.description}</p>
                </div>
                {entry?.href ? (
                  <Link href={entry.href} className="inline-flex items-center gap-2 text-sm font-medium text-brand-700 hover:underline" data-report-link>
                    Open {entry.title} <ArrowRight size={14} aria-hidden />
                  </Link>
                ) : entry && (
                  <>
                    {wants("period") && (
                      <div className="overflow-x-auto">
                        <SegmentedControl<Preset> label="Period" value={preset}
                          onChange={(v) => { setPreset(v); if (v !== "custom") setPeriod(presetPeriod(v, new Date())); }}
                          options={[{ value: "today", label: "Today" }, { value: "week", label: "This week" }, { value: "month", label: "This month" }, { value: "custom", label: "Custom" }]} />
                      </div>
                    )}
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 xl:items-end">
                      {wants("period") && (
                        <>
                          <Field label="From">
                            {({ id }) => <TextInput id={id} type="date" value={period.from} max={period.to || undefined}
                              onChange={(e) => { setPreset("custom"); setPeriod((p) => ({ ...p, from: e.target.value })); }} />}
                          </Field>
                          <Field label="To" error={invalid && period.from && period.to ? invalid : undefined}>
                            {({ id }) => <TextInput id={id} type="date" value={period.to} min={period.from || undefined}
                              onChange={(e) => { setPreset("custom"); setPeriod((p) => ({ ...p, to: e.target.value })); }} />}
                          </Field>
                        </>
                      )}
                      {wants("compare") && (
                        <Field label="Compare with">
                          {({ id }) => (
                            <SelectInput id={id} value={compare} onChange={(e) => setCompare(e.target.value as CompareMode)}>
                              <option value="elapsed">Same days, previous month</option><option value="full">Full months</option><option value="previous">Previous equal period</option>
                            </SelectInput>
                          )}
                        </Field>
                      )}
                      {wants("supplier") && (
                        <Field label="Supplier">
                          {({ id }) => <SearchSelect id={id} value={filters.supplier} noun="suppliers" emptyLabel="All suppliers"
                            options={lists.suppliers.map((s) => ({ value: String(s.id), label: s.name }))} onChange={(v) => setFilters((f) => ({ ...f, supplier: v }))} />}
                        </Field>
                      )}
                      {wants("category") && (
                        <Field label="Category">
                          {({ id }) => <SearchSelect id={id} value={filters.category} noun="categories" emptyLabel="All categories"
                            options={lists.categories.map((c) => ({ value: String(c.id), label: c.name }))} onChange={(v) => setFilters((f) => ({ ...f, category: v, item: "" }))} />}
                        </Field>
                      )}
                      {wants("item") && (
                        <Field label="Item">
                          {({ id }) => <SearchSelect id={id} value={filters.item} noun="items" emptyLabel="All items"
                            options={items.map((i) => ({ value: String(i.id), label: i.name }))} onChange={(v) => setFilters((f) => ({ ...f, item: v }))} />}
                        </Field>
                      )}
                      {wants("meal_session") && (
                        <Field label="Meal session">
                          {({ id }) => (
                            <SelectInput id={id} value={filters.session} onChange={(e) => setFilters((f) => ({ ...f, session: e.target.value }))}>
                              <option value="">All meal sessions</option>
                              {lists.sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                            </SelectInput>
                          )}
                        </Field>
                      )}
                    </div>
                  </>
                )}
              </CardBody>
            </Card>

            {entry && !entry.href && (invalid ? <Card><EmptyState icon={BarChart3} title="Check the period" description={invalid} /></Card>
              : error ? <Card><ErrorState title="Couldn't load the report" message={error} /></Card>
              : !report ? <Card><TableSkeleton rows={5} columns={6} /></Card> : (
                <Card className={loading ? "opacity-60" : undefined} data-report={report.key}>
                  <CardHeader title={report.title}
                    subtitle={[
                      report.period ? `${formatDay(report.period.date_from)} – ${formatDay(report.period.date_to)}` : `As of ${formatDay(report.as_of)}`,
                      report.comparison ? `compared with ${formatDay(report.comparison.previous.date_from)} – ${formatDay(report.comparison.previous.date_to)}` : null,
                      ...report.filters.map((f) => `${f.label}: ${f.value}`),
                      report.campus.name,
                    ].filter(Boolean).join(" · ")} icon={BarChart3} />
                  {report.rows.length === 0 ? <p className="px-5 pb-4 text-sm text-slate-600">No records for these filters.</p> : (
                    <Table minWidth={`${Math.max(640, report.columns.length * 120)}px`}>
                      <THead><tr>{report.columns.map((c) => <TH key={c.key} align={["money", "qty", "number", "percent"].includes(c.kind) ? "right" : undefined}>{c.label}</TH>)}</tr></THead>
                      <TBody>
                        {report.rows.slice(0, 1000).map((row, index) => (
                          <TR key={index}>
                            {report.columns.map((c) => (
                              <TD key={c.key} align={["money", "qty", "number", "percent"].includes(c.kind) ? "right" : undefined}
                                className={["money", "qty", "number"].includes(c.kind) ? "whitespace-nowrap tabular-nums" : undefined}>{cell(c, row)}</TD>
                            ))}
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                  )}
                  {report.rows.length > 1000 && <p className="px-5 pt-2 text-xs text-slate-500">Showing the first 1,000 of {report.row_count} rows; the exports contain every row.</p>}
                  {report.totals.length > 0 && (
                    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 border-t border-slate-100 px-5 py-4 text-sm sm:grid-cols-2 lg:grid-cols-3" data-report-totals>
                      {report.totals.map((t) => (
                        <div key={t.label} className="flex justify-between gap-3"><dt className="text-slate-600">{t.label}</dt><dd className="font-semibold tabular-nums">{totalText(t)}</dd></div>
                      ))}
                    </dl>
                  )}
                  {report.notes.length > 0 && <ul className="list-disc space-y-1 px-5 pb-5 pl-10 text-xs text-slate-500">{report.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
                </Card>
              ))}
          </>
        )}
    </div>
  );
}
