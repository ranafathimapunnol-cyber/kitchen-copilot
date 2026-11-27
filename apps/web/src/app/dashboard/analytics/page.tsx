"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChartColumn, FileSearch, Paperclip, TrendingUp, Wallet, X } from "lucide-react";

import { api } from "@/lib/api/client";
import { ANALYTICS_OPTIONS_ENDPOINT, ANALYTICS_SPENDING_ENDPOINT, ANALYTICS_TRANSACTIONS_ENDPOINT } from "@/lib/api/endpoints";
import { STATUS_LABELS, type AnalyticsOptions, type CompareMode, type SpendingAnalysis, type TransactionLine } from "@/lib/analytics";
import { percentText } from "@/lib/dashboard";
import { periodError, presetPeriod } from "@/lib/outsourcedMath";
import { errorMessage, formatDay, formatRupees } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import AreaChart from "@/components/charts/AreaChart";
import BarList from "@/components/charts/BarList";
import { SERIES } from "@/components/charts/tokens";
import BillDetailModal from "@/components/payments/BillDetailModal";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import SearchSelect from "@/components/ui/SearchSelect";
import SegmentedControl from "@/components/ui/SegmentedControl";
import StatCard from "@/components/ui/StatCard";
import { EmptyState, ErrorState, Spinner, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type Preset = "month" | "last_month" | "custom";
type Drill = { title: string; category_id?: number; item_id?: number; date_from: string; date_to: string };

function lastMonth(today: Date) {
  const from = new Date(today.getFullYear(), today.getMonth() - 1, 1);
  const to = new Date(today.getFullYear(), today.getMonth(), 0);
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return { from: iso(from), to: iso(to) };
}

function Change({ value }: { value: string | null }) {
  if (value === null) return <span className="text-slate-500">Not comparable</span>;
  const n = Number(value);
  return <span className={n > 0 ? "text-red-700" : n < 0 ? "text-emerald-700" : "text-slate-700"}>{percentText(value)}</span>;
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const ID = /^\d+$/;

/**
 * A link may open the page on a given period and filter (Kitchen Copilot's
 * "Open in Spending Analysis" does): date_from, date_to, compare,
 * category_id, item_id. Anything malformed is ignored.
 */
function initialFilters(query: URLSearchParams) {
  const from = query.get("date_from") ?? "";
  const to = query.get("date_to") ?? "";
  const compare = query.get("compare");
  const category = query.get("category_id") ?? "";
  const item = query.get("item_id") ?? "";
  const custom = ISO_DAY.test(from) && ISO_DAY.test(to) && from <= to;
  return {
    preset: (custom ? "custom" : "month") as Preset,
    period: custom ? { from, to } : presetPeriod("month", new Date()),
    compare: (compare === "full" || compare === "previous" || compare === "elapsed" ? compare : "elapsed") as CompareMode,
    categoryId: ID.test(category) ? category : "",
    itemId: ID.test(item) ? item : "",
  };
}

/** DASH01–DASH05: purchase expenditure, comparisons, price and quantity effects, drill-down to bills. */
export default function SpendingAnalysisPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={5} />}>
      <SpendingAnalysis />
    </Suspense>
  );
}

function SpendingAnalysis() {
  const query = useSearchParams();
  const [initial] = useState(() => initialFilters(new URLSearchParams(query.toString())));
  const [preset, setPreset] = useState<Preset>(initial.preset);
  const [period, setPeriod] = useState(initial.period);
  const [compare, setCompare] = useState<CompareMode>(initial.compare);
  const [categoryId, setCategoryId] = useState(initial.categoryId);
  const [itemId, setItemId] = useState(initial.itemId);
  const [supplierId, setSupplierId] = useState("");
  const [options, setOptions] = useState<AnalyticsOptions | null>(null);
  const [data, setData] = useState<SpendingAnalysis | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [drill, setDrill] = useState<Drill | null>(null);
  const [linesState, setLinesState] = useState<{ key: string; data: { items: TransactionLine[]; total: number; line_total: string } } | null>(null);
  const [billId, setBillId] = useState<number | null>(null);

  const invalid = periodError(period.from, period.to);
  const params = new URLSearchParams({ date_from: period.from, date_to: period.to, compare });
  if (categoryId) params.set("category_id", categoryId);
  if (itemId) params.set("item_id", itemId);
  if (supplierId) params.set("supplier_id", supplierId);
  const url = `${ANALYTICS_SPENDING_ENDPOINT}?${params}`;
  const key = `${url}#${reloadKey}`;
  const loading = loadedKey !== key;

  useEffect(() => {
    api.get<AnalyticsOptions>(ANALYTICS_OPTIONS_ENDPOINT).then(setOptions).catch(() => setOptions(null));
  }, []);

  useEffect(() => {
    if (invalid) return;
    let active = true;
    api.get<SpendingAnalysis>(url)
      .then((r) => { if (active) { setData(r); setError(""); } })
      .catch((err: unknown) => active && setError(errorMessage(err, "Unable to load the analysis.")))
      .finally(() => active && setLoadedKey(key));
    return () => { active = false; };
  }, [url, key, invalid]);

  const drillQuery = (() => {
    if (!drill) return "";
    const p = new URLSearchParams({ date_from: drill.date_from, date_to: drill.date_to, page_size: "200" });
    if (drill.category_id ?? categoryId) p.set("category_id", String(drill.category_id ?? categoryId));
    if (drill.item_id ?? itemId) p.set("item_id", String(drill.item_id ?? itemId));
    if (supplierId) p.set("supplier_id", supplierId);
    return p.toString();
  })();
  const lines = linesState && linesState.key === drillQuery ? linesState.data : null;

  useEffect(() => {
    if (!drillQuery) return;
    let active = true;
    api.get<{ items: TransactionLine[]; total: number; line_total: string }>(`${ANALYTICS_TRANSACTIONS_ENDPOINT}?${drillQuery}`)
      .then((r) => active && setLinesState({ key: drillQuery, data: r }))
      .catch(() => active && setLinesState({ key: drillQuery, data: { items: [], total: 0, line_total: "0.00" } }));
    return () => { active = false; };
  }, [drillQuery]);

  function choosePreset(value: Preset) {
    setPreset(value);
    if (value === "month") { setPeriod(presetPeriod("month", new Date())); setCompare("elapsed"); }
    if (value === "last_month") { const p = lastMonth(new Date()); setPeriod(p); setCompare("full"); }
  }

  const shown = invalid ? null : data;
  const cur = shown?.periods.current;
  const prev = shown?.periods.previous;
  const currentDrill = (title: string, extra: Partial<Drill> = {}) => cur && setDrill({ title, date_from: cur.date_from, date_to: cur.date_to, ...extra });
  const filtered = Boolean(categoryId || itemId || supplierId);
  const itemOptions = (options?.items ?? []).filter((i) => !categoryId || String(i.category_id) === categoryId);

  return (
    <div className="space-y-6 pb-6">
      <PageHeader eyebrow="Reports" icon={ChartColumn} title="Spending analysis"
        description="Purchase expenditure compared with a matching earlier period: categories, unit-price changes, and how much of each change came from prices and how much from quantities. Select a figure to see the bills behind it." />

      <Card>
        <CardBody className="space-y-4">
          <div className="overflow-x-auto">
            <SegmentedControl<Preset> label="Period" value={preset} onChange={choosePreset}
              options={[{ value: "month", label: "This month" }, { value: "last_month", label: "Last month" }, { value: "custom", label: "Custom" }]} />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 xl:items-end">
            <Field label="From">
              {({ id }) => <TextInput id={id} type="date" value={period.from} max={period.to || undefined}
                onChange={(e) => { setPreset("custom"); setPeriod((p) => ({ ...p, from: e.target.value })); }} />}
            </Field>
            <Field label="To" error={invalid && period.from && period.to ? invalid : undefined}>
              {({ id, describedBy }) => <TextInput id={id} type="date" aria-describedby={describedBy} value={period.to} min={period.from || undefined}
                onChange={(e) => { setPreset("custom"); setPeriod((p) => ({ ...p, to: e.target.value })); }} />}
            </Field>
            <Field label="Compare with">
              {({ id }) => (
                <SelectInput id={id} value={compare} onChange={(e) => setCompare(e.target.value as CompareMode)}>
                  <option value="elapsed">Same days, previous month</option>
                  <option value="full">Full months</option>
                  <option value="previous">Previous equal period</option>
                </SelectInput>
              )}
            </Field>
            <Field label="Category">
              {({ id }) => <SearchSelect id={id} value={categoryId} noun="categories" emptyLabel="All categories"
                options={(options?.categories ?? []).map((c) => ({ value: String(c.id), label: c.name }))}
                onChange={(v) => { setCategoryId(v); setItemId(""); }} />}
            </Field>
            <Field label="Item">
              {({ id }) => <SearchSelect id={id} value={itemId} noun="items" emptyLabel="All items"
                options={itemOptions.map((i) => ({ value: String(i.id), label: i.name }))} onChange={setItemId} />}
            </Field>
            <Field label="Supplier">
              {({ id }) => <SearchSelect id={id} value={supplierId} noun="suppliers" emptyLabel="All suppliers"
                options={(options?.suppliers ?? []).map((s) => ({ value: String(s.id), label: s.name }))} onChange={setSupplierId} />}
            </Field>
          </div>
          {filtered && (
            <Button size="sm" variant="ghost" icon={<X size={14} aria-hidden />} onClick={() => { setCategoryId(""); setItemId(""); setSupplierId(""); }}>
              Clear filters
            </Button>
          )}
        </CardBody>
      </Card>

      {invalid ? <Card><EmptyState icon={ChartColumn} title="Check the period" description={invalid} /></Card>
        : error && !loading ? <Card><ErrorState title="Couldn't load the analysis" message={error} onRetry={() => setReloadKey((k) => k + 1)} /></Card>
        : !shown || !cur || !prev ? <Card><TableSkeleton rows={4} columns={6} /></Card> : (
          <div className={loading ? "space-y-6 opacity-60" : "space-y-6"} aria-busy={loading} data-analysis>
            <p className="text-sm text-slate-600" data-periods>
              <strong>{formatDay(cur.date_from)} – {formatDay(cur.date_to)}</strong> ({cur.days} days) compared with{" "}
              <strong>{formatDay(prev.date_from)} – {formatDay(prev.date_to)}</strong> ({prev.days} days).
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <button type="button" className="text-left" onClick={() => currentDrill("Bills in the current period")}>
                <StatCard label="Purchase expenditure" icon={Wallet} value={formatRupees(shown.totals.current)}
                  description={`${shown.totals.basis} · select to see the bills`} />
              </button>
              <StatCard label="Previous period" icon={Wallet} value={formatRupees(shown.totals.previous)}
                description={`${formatDay(prev.date_from)} – ${formatDay(prev.date_to)}`} />
              <StatCard label="Change" icon={TrendingUp} value={formatRupees(shown.totals.change)}
                description={shown.totals.change_percent === null ? "Not comparable (no previous spending)" : `${percentText(shown.totals.change_percent)} on the previous period`} />
              <StatCard label="Price vs quantity" icon={TrendingUp} value={formatRupees(shown.totals.price_effect)}
                description={`price effect · quantity effect ${formatRupees(shown.totals.quantity_effect)}`} />
            </div>
            {shown.totals.current_bills && (
              <p className="text-xs text-slate-500">
                Bills: {shown.totals.current_bills.bill_count} · line totals {formatRupees(shown.totals.current_bills.subtotal)} · discounts{" "}
                {formatRupees(shown.totals.current_bills.discount)} · extra charges {formatRupees(shown.totals.current_bills.extra_charges)} (not allocated to items).
                {shown.totals.excluded_lines > 0 && ` ${shown.totals.excluded_lines} line(s) excluded from price comparisons: no conversion to the item's standard unit.`}
              </p>
            )}

            <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
              <Card>
                <CardHeader title="Monthly expenditure" subtitle={`Last 12 months · ${shown.monthly[0]?.basis ?? ""}`} icon={ChartColumn} />
                <div className="px-5 pb-5">
                  <AreaChart points={shown.monthly.map((m) => ({ date: `${m.month}-01`, value: Number(m.expenditure) }))}
                    color={SERIES.blue} seriesLabel="Expenditure" formatValue={(v) => formatRupees(v)} />
                </div>
              </Card>
              <Card>
                <CardHeader title="Spending by category" subtitle="Current period, line totals · select a category for its bills" icon={ChartColumn} />
                <div className="px-5 pb-5">
                  {shown.categories.length === 0 ? <p className="text-sm text-slate-500">No purchases in this period.</p> : (
                    <BarList color={SERIES.blue} measureLabel="Spending by category" rows={shown.categories.map((c) => ({
                      id: c.category_id, label: c.category_name ?? "—", value: Number(c.current_value), display: formatRupees(c.current_value),
                      meta: c.value_change_percent === null ? "Not comparable" : percentText(c.value_change_percent),
                      trailing: <Button size="sm" variant="ghost" icon={<FileSearch size={13} aria-hidden />}
                        onClick={() => currentDrill(`${c.category_name} — bills`, { category_id: c.category_id })}>Bills</Button>,
                    }))} />
                  )}
                </div>
              </Card>
            </div>

            {itemId && shown.monthly.some((m) => m.average_price) && (
              <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                <Card>
                  <CardHeader title={`${shown.filters.item_name} — price trend`} subtitle="Weighted average price per standard unit, by month" icon={TrendingUp} />
                  <div className="px-5 pb-5">
                    <AreaChart points={shown.monthly.filter((m) => m.average_price).map((m) => ({ date: `${m.month}-01`, value: Number(m.average_price) }))}
                      color={SERIES.orange} seriesLabel="Average price" formatValue={(v) => formatRupees(v)} />
                  </div>
                </Card>
                <Card>
                  <CardHeader title={`${shown.filters.item_name} — quantity trend`} subtitle="Purchased quantity in the standard unit, by month" icon={TrendingUp} />
                  <div className="px-5 pb-5">
                    <AreaChart points={shown.monthly.map((m) => ({ date: `${m.month}-01`, value: Number(m.quantity ?? 0) }))}
                      color={SERIES.blue} seriesLabel="Quantity" formatValue={(v) => plainQuantity(String(v))} />
                  </div>
                </Card>
              </div>
            )}

            <Card>
              <CardHeader title="Largest unit-price increases" subtitle="Comparable items only (same item, standard unit)" icon={TrendingUp} />
              {shown.top_price_increases.length === 0 ? <p className="px-5 pb-5 text-sm text-slate-500">No comparable item became dearer.</p> : (
                <Table minWidth="640px">
                  <THead><tr><TH>Item</TH><TH align="right">Previous price</TH><TH align="right">Current price</TH><TH align="right">Change</TH></tr></THead>
                  <TBody>
                    {shown.top_price_increases.map((r) => (
                      <TR key={r.item_id}>
                        <TD className="font-medium">{r.item_name}<span className="text-xs text-slate-500"> · per {r.standard_unit_symbol}</span></TD>
                        <TD align="right" className="tabular-nums">{formatRupees(r.previous_price)}</TD>
                        <TD align="right" className="tabular-nums">{formatRupees(r.current_price)}</TD>
                        <TD align="right"><Change value={r.price_change_percent} /></TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              )}
            </Card>

            <Card>
              <CardHeader title="Item comparison" subtitle="Quantities in each item's standard unit; weighted average price = value ÷ quantity; price effect + quantity effect = change" icon={ChartColumn} />
              {shown.items.length === 0 ? <p className="px-5 pb-5 text-sm text-slate-500">No item purchases in either period.</p> : (
                <Table minWidth="1180px">
                  <THead>
                    <tr>
                      <TH>Item</TH><TH align="right">Quantity (prev → now)</TH><TH align="right">Avg price (prev → now)</TH><TH align="right">Price %</TH>
                      <TH align="right">Value (prev → now)</TH><TH align="right">Change %</TH><TH align="right">Price effect</TH><TH align="right">Quantity effect</TH><TH>Status</TH><TH />
                    </tr>
                  </THead>
                  <TBody>
                    {shown.items.map((r) => (
                      <TR key={r.item_id}>
                        <TD className="font-medium">{r.item_name}<div className="text-xs text-slate-500">{r.category_name}</div></TD>
                        <TD align="right" className="whitespace-nowrap tabular-nums">{plainQuantity(r.previous_quantity)} → {plainQuantity(r.current_quantity)} {r.standard_unit_symbol}</TD>
                        <TD align="right" className="whitespace-nowrap tabular-nums">{r.previous_price ? formatRupees(r.previous_price) : "—"} → {r.current_price ? formatRupees(r.current_price) : "—"}</TD>
                        <TD align="right"><Change value={r.price_change_percent} /></TD>
                        <TD align="right" className="whitespace-nowrap tabular-nums">{formatRupees(r.previous_value)} → {formatRupees(r.current_value)}</TD>
                        <TD align="right"><Change value={r.value_change_percent} /></TD>
                        <TD align="right" className="tabular-nums">{r.price_effect ? formatRupees(r.price_effect) : "—"}</TD>
                        <TD align="right" className="tabular-nums">{r.quantity_effect ? formatRupees(r.quantity_effect) : "—"}</TD>
                        <TD><Badge tone={r.status === "COMPARABLE" ? "success" : "neutral"}>{STATUS_LABELS[r.status]}</Badge>
                          {r.excluded_lines > 0 && <div className="text-xs text-amber-700">{r.excluded_lines} line(s) without a conversion</div>}</TD>
                        <TD><Button size="sm" variant="ghost" icon={<FileSearch size={13} aria-hidden />}
                          onClick={() => currentDrill(`${r.item_name} — bills`, { item_id: r.item_id })}>Bills</Button></TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              )}
            </Card>
            <ul className="list-disc space-y-1 pl-5 text-xs text-slate-500">{shown.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          </div>
        )}

      {drill && (
        <Modal open size="xl" title={drill.title} description={`${formatDay(drill.date_from)} – ${formatDay(drill.date_to)}. Open a bill to see its lines, payments and attachments.`}
          onClose={() => setDrill(null)} footer={<Button variant="secondary" onClick={() => setDrill(null)}>Close</Button>}>
          {lines === null ? <Spinner label="Loading the bills" /> : lines.items.length === 0 ? <p className="text-sm text-slate-600">No bill lines.</p> : (
            <div className="space-y-2" data-drilldown>
              <p className="text-sm text-slate-600">{lines.total} line(s) · {formatRupees(lines.line_total)}</p>
              <Table minWidth="760px">
                <THead><tr><TH>Bill</TH><TH>Item</TH><TH align="right">Quantity</TH><TH align="right">Line total</TH><TH /></tr></THead>
                <TBody>
                  {lines.items.map((l) => (
                    <TR key={l.purchase_item_id}>
                      <TD><span className="font-medium">{l.invoice_number}</span><div className="text-xs text-slate-500">{formatDay(l.purchase_date)} · {l.supplier_name}</div></TD>
                      <TD>{l.item_name}<div className="text-xs text-slate-500">{l.category_name}</div></TD>
                      <TD align="right" className="whitespace-nowrap tabular-nums">{plainQuantity(l.quantity)} {l.unit_symbol}
                        {l.standard_quantity && l.unit_symbol !== l.standard_unit_symbol && <div className="text-xs text-slate-500">= {plainQuantity(l.standard_quantity)} {l.standard_unit_symbol}</div>}</TD>
                      <TD align="right" className="tabular-nums">{formatRupees(l.line_total)}</TD>
                      <TD align="right"><Button size="sm" variant="secondary" icon={l.attachment_count ? <Paperclip size={13} aria-hidden /> : undefined}
                        onClick={() => setBillId(l.purchase_id)}>Open bill{l.attachment_count ? ` (${l.attachment_count})` : ""}</Button></TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          )}
        </Modal>
      )}
      {billId !== null && (
        <BillDetailModal purchaseId={billId} canRecord={false} reloadKey={0} onClose={() => setBillId(null)}
          onRecordPayment={() => undefined} canUpload={false} canReview={false} />
      )}
    </div>
  );
}
