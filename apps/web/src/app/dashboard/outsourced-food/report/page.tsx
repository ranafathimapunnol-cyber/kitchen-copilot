"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, CalendarDays, ChartColumn, FileDown, FileSpreadsheet, Printer, Receipt, Soup, Truck, Utensils } from "lucide-react";

import { api, apiDownload } from "@/lib/api/client";
import { OUTSOURCED_OPTIONS_ENDPOINT, OUTSOURCED_REPORT_ENDPOINT, OUTSOURCED_REPORT_EXPORT_ENDPOINT } from "@/lib/api/endpoints";
import type { OutsourcedOptions, OutsourcedReport } from "@/lib/outsourced";
import { outsourcedExportName, periodError, presetPeriod, type Preset } from "@/lib/outsourcedMath";
import { errorMessage, formatDay, formatRupees } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import { ReportStatusBadge } from "@/components/outsourced/OutsourcedBadges";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import SearchSelect from "@/components/ui/SearchSelect";
import SegmentedControl from "@/components/ui/SegmentedControl";
import StatCard from "@/components/ui/StatCard";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

type Format = "xlsx" | "pdf";

const QTY_COLUMNS: [keyof OutsourcedReport["by_item"][number], string][] = [
  ["ordered_quantity", "Ordered"],
  ["received_quantity", "Received"],
  ["rejected_quantity", "Rejected"],
  ["accepted_quantity", "Accepted"],
  ["distributed_quantity", "Distributed"],
  ["remaining_quantity", "Remaining"],
  ["retained_quantity", "Retained"],
  ["returned_to_supplier_quantity", "Returned"],
  ["wasted_quantity", "Wasted"],
  ["disposed_quantity", "Disposed"],
];

/** Outsourced food report (OUT02, AT04): by meal date, supplier, item and meal session. */
export default function OutsourcedReportPage() {
  const toast = useToast();
  const [preset, setPreset] = useState<Preset>("month");
  const [period, setPeriod] = useState(() => presetPeriod("month", new Date()));
  const [supplierId, setSupplierId] = useState("");
  const [itemId, setItemId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [options, setOptions] = useState<OutsourcedOptions | null>(null);
  const [report, setReport] = useState<OutsourcedReport | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [exporting, setExporting] = useState<Format | null>(null);

  const invalid = periodError(period.from, period.to);
  const params = new URLSearchParams({ date_from: period.from, date_to: period.to });
  if (supplierId) params.set("supplier_id", supplierId);
  if (itemId) params.set("item_id", itemId);
  if (sessionId) params.set("meal_session_id", sessionId);
  const url = `${OUTSOURCED_REPORT_ENDPOINT}?${params}`;
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    if (invalid) return;
    let active = true;
    api
      .get<OutsourcedReport>(url)
      .then((response) => {
        if (!active) return;
        setReport(response);
        setError("");
      })
      .catch((err: unknown) => active && setError(errorMessage(err, "Unable to load the report.")))
      .finally(() => active && setLoadedKey(requestKey));
    return () => {
      active = false;
    };
  }, [url, requestKey, invalid]);

  useEffect(() => {
    api.get<OutsourcedOptions>(OUTSOURCED_OPTIONS_ENDPOINT).then(setOptions).catch(() => setOptions(null));
  }, []);

  function choosePreset(value: Preset) {
    setPreset(value);
    if (value !== "custom") setPeriod(presetPeriod(value, new Date()));
  }

  const shown = invalid ? null : report;
  const canExport = Boolean(shown && !loading && !error);
  const costs = Boolean(shown?.costs_visible);

  function exportReport(format: Format) {
    if (!shown || !canExport) return;
    setExporting(format);
    apiDownload(OUTSOURCED_REPORT_EXPORT_ENDPOINT, {
      format,
      date_from: shown.period.date_from,
      date_to: shown.period.date_to,
      supplier_id: shown.filters.supplier_id,
      item_id: shown.filters.item_id,
      meal_session_id: shown.filters.meal_session_id,
    })
      .then(({ blob, filename }) => {
        const name = filename ?? outsourcedExportName(shown.period, shown.filters, format);
        const href = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = href;
        link.download = name;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(href), 1000);
        toast.success(`${format === "xlsx" ? "Excel" : "PDF"} file downloaded: ${name}`);
      })
      .catch((err: unknown) => toast.error(errorMessage(err, "The export could not be created.")))
      .finally(() => setExporting(null));
  }

  const totals = shown?.totals_by_unit ?? [];

  return (
    <div className="space-y-6 pb-6">
      <style>{"@media print { @page { size: A4 landscape; margin: 12mm; } }"}</style>
      {shown && (
        <div className="hidden print:block" data-print-header>
          <p className="text-xs text-slate-600">{shown.campus.name ?? `Campus #${shown.campus.id}`} · Kitchen Copilot</p>
          <p className="mt-1 text-xs text-slate-500">
            {formatDay(shown.period.date_from)} – {formatDay(shown.period.date_to)} ·{" "}
            {[shown.filters.supplier_name ?? "All suppliers", shown.filters.item_name ?? "All items",
              shown.filters.meal_session_name ?? "All meal sessions"].join(" · ")} · generated {new Date(shown.generated_at).toLocaleString("en-IN")}
          </p>
        </div>
      )}

      <PageHeader
        eyebrow="Operations"
        icon={ChartColumn}
        title="Outsourced food report"
        description="Ordered outsourced food by meal date: received, rejected and accepted quantities, what reached the meal records, distributed, remaining and leftovers."
        actions={
          <div className="flex flex-wrap gap-2 print:hidden">
            <Link href="/dashboard/outsourced-food"
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50">
              <ArrowLeft size={15} aria-hidden />
              Orders
            </Link>
            <Button variant="secondary" icon={<FileSpreadsheet size={15} aria-hidden />} loading={exporting === "xlsx"}
              disabled={!canExport || exporting !== null} onClick={() => exportReport("xlsx")}>Export Excel</Button>
            <Button variant="secondary" icon={<FileDown size={15} aria-hidden />} loading={exporting === "pdf"}
              disabled={!canExport || exporting !== null} onClick={() => exportReport("pdf")}>Export PDF</Button>
            <Button variant="secondary" icon={<Printer size={15} aria-hidden />} disabled={!canExport} onClick={() => window.print()}>Print</Button>
          </div>
        }
      />

      <Card className="print:hidden">
        <CardBody className="space-y-4">
          <div className="overflow-x-auto">
            <SegmentedControl<Preset>
              label="Reporting period"
              value={preset}
              onChange={choosePreset}
              options={[
                { value: "today", label: "Today" },
                { value: "week", label: "This week" },
                { value: "month", label: "This month" },
                { value: "custom", label: "Custom" },
              ]}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5 lg:items-end">
            <Field label="Meal date from">
              {({ id }) => (
                <TextInput id={id} type="date" value={period.from} max={period.to || undefined}
                  onChange={(event) => { setPreset("custom"); setPeriod((p) => ({ ...p, from: event.target.value })); }} />
              )}
            </Field>
            <Field label="Meal date to" error={invalid && period.from && period.to ? invalid : undefined}>
              {({ id, describedBy }) => (
                <TextInput id={id} type="date" aria-describedby={describedBy} value={period.to} min={period.from || undefined}
                  onChange={(event) => { setPreset("custom"); setPeriod((p) => ({ ...p, to: event.target.value })); }} />
              )}
            </Field>
            <Field label="Supplier">
              {({ id }) => (
                <SearchSelect id={id} value={supplierId} noun="suppliers" emptyLabel="All suppliers"
                  options={(options?.suppliers ?? []).map((s) => ({ value: String(s.id), label: s.name }))} onChange={setSupplierId} />
              )}
            </Field>
            <Field label="Item">
              {({ id }) => (
                <SearchSelect id={id} value={itemId} noun="items" emptyLabel="All items"
                  options={(options?.items ?? []).map((i) => ({ value: String(i.id), label: i.name }))} onChange={setItemId} />
              )}
            </Field>
            <Field label="Meal session">
              {({ id }) => (
                <SelectInput id={id} value={sessionId} onChange={(event) => setSessionId(event.target.value)}>
                  <option value="">All meal sessions</option>
                  {options?.meal_sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </SelectInput>
              )}
            </Field>
          </div>
        </CardBody>
      </Card>

      {invalid ? (
        <Card><EmptyState icon={CalendarDays} title="Check the period" description={invalid} /></Card>
      ) : error && !loading ? (
        <Card><ErrorState title="Couldn't load the report" message={error} onRetry={() => setReloadKey((key) => key + 1)} /></Card>
      ) : !shown ? (
        <Card><TableSkeleton rows={5} columns={8} /></Card>
      ) : (
        <div className={loading ? "space-y-6 opacity-60 transition-opacity" : "space-y-6"} aria-busy={loading} data-outsourced-report>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Order lines" value={String(shown.line_count)} icon={Soup}
              description={`${shown.unreconciled_count} not yet reconciled`} />
            {costs && shown.cost_totals ? (
              <>
                <StatCard label="Purchase expenditure" value={formatRupees(shown.cost_totals.billed_cost)} icon={Receipt}
                  description="From linked supplier bill lines" />
                <StatCard label="Planned cost" value={formatRupees(shown.cost_totals.planned_cost)} icon={ChartColumn}
                  description={`Order rates; not expenditure · ${shown.cost_totals.lines_without_bill} line(s) without a bill`} />
              </>
            ) : (
              <StatCard label="Costs" value="Not shown" icon={Receipt} description="Needs supplier-bill access" />
            )}
            <StatCard label="Units" value={totals.map((t) => t.unit_symbol).filter(Boolean).join(", ") || "—"} icon={Utensils}
              description="Quantities are added up per unit only" />
          </div>

          {shown.rejected_note && <Alert tone="warning" title="Rejected food">{shown.rejected_note}</Alert>}

          <Card>
            <CardHeader title="Totals by unit" subtitle="No conversion between units is assumed (client question Q7)." icon={Truck} />
            {totals.length === 0 ? (
              <EmptyState icon={Soup} title="No outsourced food in this period" description="Only ordered outsourced orders with a meal date in the period are included." />
            ) : (
              <Table minWidth="980px">
                <THead>
                  <tr>
                    <TH>Unit</TH>
                    <TH align="right">Lines</TH>
                    {QTY_COLUMNS.map(([, label]) => <TH key={label} align="right">{label}</TH>)}
                  </tr>
                </THead>
                <TBody>
                  {totals.map((group) => (
                    <TR key={group.unit_id}>
                      <TD className="font-medium">{group.unit_symbol}</TD>
                      <TD align="right" className="tabular-nums">{group.lines}</TD>
                      {QTY_COLUMNS.map(([key, label]) => (
                        <TD key={label} align="right" className="tabular-nums">{plainQuantity(group[key] as string)}</TD>
                      ))}
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </Card>

          {shown.by_item.length > 0 && (
            <Card>
              <CardHeader title="By item" icon={Soup} />
              <Table minWidth={costs ? "1240px" : "1040px"}>
                <THead>
                  <tr>
                    <TH>Item</TH>
                    {QTY_COLUMNS.map(([, label]) => <TH key={label} align="right">{label}</TH>)}
                    {costs && <TH align="right">Planned</TH>}
                    {costs && <TH align="right">Billed</TH>}
                  </tr>
                </THead>
                <TBody>
                  {shown.by_item.map((group) => (
                    <TR key={`${group.item_id}-${group.unit_id}`}>
                      <TD className="min-w-40 font-medium text-slate-900">
                        {group.item_name}
                        <div className="text-xs font-normal text-slate-500">{group.unit_symbol}</div>
                      </TD>
                      {QTY_COLUMNS.map(([key, label]) => (
                        <TD key={label} align="right" className="tabular-nums">{plainQuantity(group[key] as string)}</TD>
                      ))}
                      {costs && <TD align="right" className="whitespace-nowrap tabular-nums">{formatRupees(group.planned_cost ?? "0")}</TD>}
                      {costs && <TD align="right" className="whitespace-nowrap tabular-nums">{formatRupees(group.billed_cost ?? "0")}</TD>}
                    </TR>
                  ))}
                </TBody>
              </Table>
            </Card>
          )}

          {shown.lines.length > 0 && (
            <Card>
              <CardHeader title="Lines" subtitle="One row per ordered item, with its meal record status." icon={Truck} />
              <Table minWidth={costs ? "1320px" : "1160px"}>
                <THead>
                  <tr>
                    <TH>Meal</TH>
                    <TH>Order · supplier</TH>
                    <TH>Item</TH>
                    <TH align="right">Ordered</TH>
                    <TH align="right">Received</TH>
                    <TH align="right">Rejected</TH>
                    <TH align="right">Accepted</TH>
                    <TH align="right">Distributed</TH>
                    <TH align="right">Remaining</TH>
                    <TH>Status</TH>
                    {costs && <TH align="right">Billed</TH>}
                  </tr>
                </THead>
                <TBody>
                  {shown.lines.map((line) => (
                    <TR key={line.order_line_id}>
                      <TD className="whitespace-nowrap">
                        <span className="font-medium text-slate-900">{line.meal_session_name}</span>
                        <div className="text-xs text-slate-500">{formatDay(line.meal_date)}</div>
                      </TD>
                      <TD className="whitespace-nowrap">
                        <Link href={`/dashboard/outsourced-food/${line.order_id}`} className="font-medium text-brand-700 hover:underline">{line.order_number}</Link>
                        <div className="text-xs text-slate-500">{line.supplier_name}</div>
                      </TD>
                      <TD>{line.item_name}</TD>
                      {(["ordered_quantity", "received_quantity", "rejected_quantity", "accepted_quantity", "distributed_quantity", "remaining_quantity"] as const).map((key) => (
                        <TD key={key} align="right" className="whitespace-nowrap tabular-nums">{plainQuantity(line[key])} {line.unit_symbol}</TD>
                      ))}
                      <TD className="whitespace-nowrap"><ReportStatusBadge status={line.status} /></TD>
                      {costs && (
                        <TD align="right" className="whitespace-nowrap tabular-nums">
                          {line.billed_cost ? formatRupees(line.billed_cost) : <span className="text-slate-400">Not billed</span>}
                          {line.bill_invoice_number && <div className="text-xs text-slate-500">{line.bill_invoice_number}</div>}
                        </TD>
                      )}
                    </TR>
                  ))}
                </TBody>
              </Table>
            </Card>
          )}

          <ul className="space-y-1 text-xs text-slate-500">
            <li>{shown.basis.orders}</li>
            <li>{shown.basis.quantities}</li>
            {costs && <li>{shown.basis.costs}</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
