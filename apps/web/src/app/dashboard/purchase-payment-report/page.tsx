"use client";

import { useEffect, useState } from "react";
import {
  Banknote,
  CalendarDays,
  ChartColumn,
  FileDown,
  FileSpreadsheet,
  Printer,
  Receipt,
  Scale,
  Wallet,
} from "lucide-react";

import { api, apiDownload } from "@/lib/api/client";
import { ENDPOINTS } from "@/lib/api/endpoints";
import { exportFileName, type ExportFormat } from "@/lib/reportExport";
import { useToast } from "@/components/ui/Toast";
import {
  errorMessage,
  fetchAllPages,
  formatDay,
  formatRupees,
  methodLabel,
  toAmount,
  type PurchasesVsPaymentsReport,
  type SupplierBalance,
} from "@/lib/payments";
import {
  financialYearToDate,
  isValidPeriod,
  monthToDate,
  previousMonth,
  type Period,
} from "@/lib/periods";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import SearchSelect from "@/components/ui/SearchSelect";
import PageHeader from "@/components/ui/PageHeader";
import StatCard from "@/components/ui/StatCard";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

function reportUrl(period: Period, supplierId: string): string {
  const params = new URLSearchParams({ date_from: period.from, date_to: period.to });
  if (supplierId) params.set("supplier_id", supplierId);
  return `${ENDPOINTS.purchasesVsPaymentsReport}?${params}`;
}

/** A signed balance: negative means the supplier has been overpaid. */
function Balance({ value }: { value: string }) {
  const amount = toAmount(value);
  return amount < 0 ? (
    <span title="Overpaid: a credit with this supplier">
      {formatRupees(-amount)} <span className="text-xs text-slate-500">credit</span>
    </span>
  ) : (
    <>{formatRupees(amount)}</>
  );
}

export default function PurchasesVsPaymentsPage() {
  const [period, setPeriod] = useState<Period>(() => monthToDate(new Date()));
  const [supplierId, setSupplierId] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const [report, setReport] = useState<PurchasesVsPaymentsReport | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");
  const [suppliers, setSuppliers] = useState<SupplierBalance[]>([]);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const toast = useToast();

  const valid = isValidPeriod(period);
  const url = reportUrl(period, supplierId);
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    if (!valid) return;
    let active = true;

    api
      .get<PurchasesVsPaymentsReport>(url)
      .then((response) => {
        if (!active) return;
        setReport(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load the report."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });

    return () => {
      active = false;
    };
  }, [url, requestKey, valid]);

  useEffect(() => {
    let active = true;
    fetchAllPages<SupplierBalance>(ENDPOINTS.supplierBalances)
      .then(({ items }) => {
        if (active) {
          setSuppliers(
            [...items].sort((a, b) =>
              (a.supplier_name ?? "").localeCompare(b.supplier_name ?? "")
            )
          );
        }
      })
      .catch(() => {
        // The report still works for all suppliers.
      });
    return () => {
      active = false;
    };
  }, []);

  const presets: { label: string; period: () => Period }[] = [
    { label: "This month", period: () => monthToDate(new Date()) },
    { label: "Last month", period: () => previousMonth(new Date()) },
    { label: "Financial year", period: () => financialYearToDate(new Date()) },
  ];

  // An invalid period is never sent, so no figures are shown for it.
  const shown = valid ? report : null;
  const totals = shown?.totals;
  const netChange = totals ? toAmount(totals.billed) - toAmount(totals.paid) : 0;
  const signed = (value: string) =>
    toAmount(value) < 0 ? `${formatRupees(-toAmount(value))} credit` : formatRupees(value);

  // Files and prints always carry the report on screen: its own period and
  // supplier, never filters still being edited. Off while that report is
  // missing, outdated or loading.
  const canExport = Boolean(shown && totals && !loading && !error);

  function exportReport(format: ExportFormat) {
    if (!shown || !canExport) return;
    setExporting(format);

    apiDownload(ENDPOINTS.purchasesVsPaymentsExport, {
      format,
      date_from: shown.period.date_from,
      date_to: shown.period.date_to,
      supplier_id: shown.filters.supplier_id,
    })
      .then(({ blob, filename }) => {
        const name =
          filename ??
          exportFileName(
            shown.period,
            { id: shown.filters.supplier_id, name: shown.filters.supplier_name },
            format
          );
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = name;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        toast.success(`${format === "xlsx" ? "Excel" : "PDF"} file downloaded: ${name}`);
      })
      .catch((err: unknown) => {
        toast.error(errorMessage(err, "The export could not be created."));
      })
      .finally(() => setExporting(null));
  }

  return (
    <div className="space-y-6 pb-6">
      {/* A4 landscape, so the supplier table prints at full width. */}
      <style>{"@media print { @page { size: A4 landscape; margin: 12mm; } }"}</style>

      {shown && (
        <div className="hidden print:block" data-print-header>
          <p className="text-xs text-slate-600">
            {shown.campus.name ?? `Campus #${shown.campus.id}`} · Kitchen Copilot
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Generated {new Date(shown.generated_at).toLocaleString("en-IN")}
          </p>
        </div>
      )}

      <PageHeader
        eyebrow="Purchasing"
        icon={ChartColumn}
        title="Purchases vs payments"
        description="Purchase expenditure and supplier payments for a period, reported separately. Bills count on their bill date and payments on their payment date."
        actions={
          <div className="flex flex-wrap gap-2 print:hidden">
            <Button
              variant="secondary"
              icon={<FileSpreadsheet size={15} aria-hidden />}
              loading={exporting === "xlsx"}
              disabled={!canExport || exporting !== null}
              onClick={() => exportReport("xlsx")}
            >
              Export Excel
            </Button>
            <Button
              variant="secondary"
              icon={<FileDown size={15} aria-hidden />}
              loading={exporting === "pdf"}
              disabled={!canExport || exporting !== null}
              onClick={() => exportReport("pdf")}
            >
              Export PDF
            </Button>
            <Button
              variant="secondary"
              icon={<Printer size={15} aria-hidden />}
              disabled={!canExport}
              onClick={() => window.print()}
            >
              Print
            </Button>
          </div>
        }
      />

      <Card className="print:hidden">
        <CardBody className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,2fr)] lg:items-end">
            <Field label="From">
              {({ id }) => (
                <TextInput
                  id={id}
                  type="date"
                  value={period.from}
                  max={period.to || undefined}
                  onChange={(event) =>
                    setPeriod((current) => ({ ...current, from: event.target.value }))
                  }
                />
              )}
            </Field>
            <Field
              label="To"
              error={
                period.from && period.to && period.from > period.to
                  ? "Must be on or after the From date."
                  : undefined
              }
            >
              {({ id, describedBy }) => (
                <TextInput
                  id={id}
                  type="date"
                  aria-describedby={describedBy}
                  aria-invalid={Boolean(period.from && period.to && period.from > period.to)}
                  value={period.to}
                  min={period.from || undefined}
                  onChange={(event) =>
                    setPeriod((current) => ({ ...current, to: event.target.value }))
                  }
                />
              )}
            </Field>
            <Field label="Supplier">
              {({ id }) => (
                <SearchSelect
                  id={id}
                  value={supplierId}
                  noun="suppliers"
                  emptyLabel="All suppliers"
                  options={suppliers.map((row) => ({
                    value: String(row.supplier_id),
                    label: row.supplier_name ?? `Supplier #${row.supplier_id}`,
                  }))}
                  onChange={(value) => setSupplierId(value)}
                />
              )}
            </Field>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {presets.map((preset) => (
              <Button
                key={preset.label}
                size="sm"
                variant="secondary"
                onClick={() => setPeriod(preset.period())}
              >
                {preset.label}
              </Button>
            ))}
          </div>
        </CardBody>
      </Card>

      {!valid ? (
        <Card>
          <EmptyState
            icon={CalendarDays}
            title="Choose a valid period"
            description="Enter both dates, with the From date on or before the To date."
          />
        </Card>
      ) : error && !loading ? (
        <Card>
          <ErrorState
            title="Couldn't load the report"
            message={error}
            onRetry={() => setReloadKey((key) => key + 1)}
          />
        </Card>
      ) : !shown || !totals ? (
        <Card>
          <TableSkeleton rows={4} columns={6} />
        </Card>
      ) : (
        <div
          className={`space-y-6 ${loading ? "opacity-60 transition-opacity" : ""}`}
          aria-busy={loading}
        >
          <p className="text-sm text-slate-600" data-report-scope>
            <span className="font-semibold text-slate-900">
              {formatDay(shown.period.date_from)} – {formatDay(shown.period.date_to)}
            </span>{" "}
            · Supplier: {shown.filters.supplier_name ?? "All suppliers"} · Amounts in ₹
            ({shown.currency})
          </p>

          <section
            aria-label="Report totals"
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
          >
            <StatCard
              label="Purchase expenditure"
              value={formatRupees(totals.billed)}
              description={`${totals.bill_count} bill${totals.bill_count === 1 ? "" : "s"} dated in the period`}
              icon={Receipt}
            />
            <StatCard
              label="Supplier payments"
              value={formatRupees(totals.paid)}
              description={`${totals.payment_count} payment${totals.payment_count === 1 ? "" : "s"} · ${formatRupees(totals.paid_cash)} in cash`}
              icon={Banknote}
            />
            <StatCard
              label="Billed minus paid"
              value={`${netChange < 0 ? "−" : ""}${formatRupees(Math.abs(netChange))}`}
              description="Change in what is owed over the period"
              icon={Scale}
            />
            <StatCard
              label="Owed at period end"
              value={signed(totals.closing_balance)}
              description={`${signed(totals.opening_balance)} owed at the start`}
              icon={Wallet}
            />
          </section>

          {/* Side by side only on very wide screens, where the supplier
              table still fits; otherwise the table gets the full width. */}
          <div className="grid grid-cols-1 gap-6 2xl:grid-cols-3">
            <Card className="2xl:col-span-1">
              <CardHeader title="Payments by method" subtitle="Payments dated in the period" />
              <CardBody>
                <dl className="divide-y divide-slate-100 text-sm" data-method-breakdown>
                  {totals.paid_by_method.map((row) => (
                    <div
                      key={row.payment_method}
                      className="flex items-center justify-between gap-3 py-2.5 first:pt-0"
                    >
                      <dt className="text-slate-600">
                        {methodLabel(row.payment_method)}
                        <span className="ml-1 text-xs text-slate-400">({row.payment_count})</span>
                      </dt>
                      <dd className="font-semibold text-slate-900 tabular-nums">
                        {formatRupees(row.amount)}
                      </dd>
                    </div>
                  ))}
                  <div className="flex items-center justify-between gap-3 pt-2.5">
                    <dt className="font-semibold text-slate-900">Total paid</dt>
                    <dd className="font-semibold text-slate-900 tabular-nums">
                      {formatRupees(totals.paid)}
                    </dd>
                  </div>
                </dl>
              </CardBody>
            </Card>

            <Card className="2xl:col-span-2">
              <CardHeader
                title="By supplier"
                subtitle="Owed at end = owed at start + billed − paid"
              />
              {shown.suppliers.length === 0 ? (
                <EmptyState
                  compact
                  icon={Receipt}
                  title="No bills or payments in this period"
                  description="And nothing owed to any supplier either side of it."
                />
              ) : (
                <Table minWidth="760px">
                  <THead>
                    <tr>
                      <TH>Supplier</TH>
                      <TH align="right">Owed at start</TH>
                      <TH align="right">Billed</TH>
                      <TH align="right">Paid</TH>
                      <TH align="right">of which cash</TH>
                      <TH align="right">Owed at end</TH>
                    </tr>
                  </THead>
                  <TBody>
                    {shown.suppliers.map((row) => (
                      <TR key={row.supplier_id}>
                        <TD className="font-medium text-slate-900">
                          {row.supplier_name ?? `Supplier #${row.supplier_id}`}
                        </TD>
                        <TD align="right">
                          <Balance value={row.opening_balance} />
                        </TD>
                        <TD align="right">
                          {formatRupees(row.billed)}
                          <span className="block text-xs text-slate-500">
                            {row.bill_count} bill{row.bill_count === 1 ? "" : "s"}
                          </span>
                        </TD>
                        <TD align="right">
                          {formatRupees(row.paid)}
                          <span className="block text-xs text-slate-500">
                            {row.payment_count} payment{row.payment_count === 1 ? "" : "s"}
                          </span>
                        </TD>
                        <TD align="right">{formatRupees(row.paid_cash)}</TD>
                        <TD align="right" className="font-semibold text-slate-900">
                          <Balance value={row.closing_balance} />
                        </TD>
                      </TR>
                    ))}
                    <tr className="border-t-2 border-slate-200 bg-slate-50/70 font-semibold text-slate-900">
                      <TD className="font-semibold text-slate-900">Total</TD>
                      <TD align="right"><Balance value={totals.opening_balance} /></TD>
                      <TD align="right">{formatRupees(totals.billed)}</TD>
                      <TD align="right">{formatRupees(totals.paid)}</TD>
                      <TD align="right">{formatRupees(totals.paid_cash)}</TD>
                      <TD align="right"><Balance value={totals.closing_balance} /></TD>
                    </tr>
                  </TBody>
                </Table>
              )}
            </Card>
          </div>

          <p className="text-xs text-slate-500">
            Supplier-return credits are not included yet. Exports and prints
            carry exactly the figures, period and supplier shown here.
          </p>
        </div>
      )}
    </div>
  );
}
