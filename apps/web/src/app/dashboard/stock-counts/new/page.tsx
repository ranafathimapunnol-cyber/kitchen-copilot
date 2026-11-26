"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, CircleCheck, ClipboardCheck, EyeOff, Save } from "lucide-react";

import { api } from "@/lib/api/client";
import { STOCK_COUNTS_ENDPOINT, STOCK_COUNT_OPTIONS_ENDPOINT } from "@/lib/api/endpoints";
import { checkCount, type CountLineDraft } from "@/lib/countMath";
import { errorMessage } from "@/lib/payments";
import { canViewCounts, type CountOptions, type CountPayload, type CountReceipt, type StockCount } from "@/lib/stockCounts";
import { allowedUnits } from "@/lib/units";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { Field, SelectInput, TextArea, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import SearchInput from "@/components/ui/SearchInput";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, TableSkeleton } from "@/components/ui/States";
import { useToast } from "@/components/ui/Toast";

type Entry = { quantity: string; unitId: string; remarks: string };
type Show = "ALL" | "COUNTED";

/**
 * Blind count entry (decision S6): items and units only. The system
 * balance is never shown here; the server records it, with the difference,
 * at the moment the count is saved.
 */
export default function NewStockCountPage() {
  const router = useRouter();
  const toast = useToast();
  const { role, permissions } = useAuthorization();
  const viewer = canViewCounts(role, permissions);
  const leave = viewer ? "/dashboard/stock-counts" : "/dashboard";
  const [options, setOptions] = useState<CountOptions | null>(null);
  const [loadError, setLoadError] = useState("");
  const [reason, setReason] = useState("");
  const [remarks, setRemarks] = useState("");
  const [entries, setEntries] = useState<Record<string, Entry>>({});
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [show, setShow] = useState<Show>("ALL");
  const [showErrors, setShowErrors] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [saved, setSaved] = useState<CountReceipt | null>(null);

  useEffect(() => {
    let active = true;
    api
      .get<CountOptions>(STOCK_COUNT_OPTIONS_ENDPOINT)
      .then((response) => {
        if (active) setOptions(response);
      })
      .catch((err: unknown) => {
        if (active) setLoadError(errorMessage(err, "Unable to load the items to count."));
      });
    return () => {
      active = false;
    };
  }, []);

  const categories = useMemo(
    () => [...new Set((options?.items ?? []).map((item) => item.category_name ?? "Uncategorised"))],
    [options]
  );

  const drafts: CountLineDraft[] = useMemo(
    () =>
      (options?.items ?? []).map((item) => {
        const entry = entries[String(item.id)];
        return {
          key: String(item.id),
          itemId: String(item.id),
          quantity: entry?.quantity ?? "",
          unitId: entry?.unitId ?? String(item.standard_unit_id),
          remarks: entry?.remarks ?? "",
        };
      }),
    [options, entries]
  );
  const check = checkCount({ reason, lines: drafts }, options?.max_lines ?? 500);

  if (loadError) {
    return (
      <div className="space-y-4 pb-6">
        <Alert tone="error" title="Couldn't load the count form">{loadError}</Alert>
      </div>
    );
  }
  if (!options) {
    return (
      <div className="space-y-4 pb-6">
        <Card><TableSkeleton rows={6} columns={4} /></Card>
      </div>
    );
  }

  const unitSymbol = (id: string) => options.units.find((unit) => String(unit.id) === id)?.symbol ?? "";
  const term = search.trim().toLowerCase();
  const visible = options.items.filter(
    (item) =>
      (!term || item.name.toLowerCase().includes(term)) &&
      (!category || (item.category_name ?? "Uncategorised") === category) &&
      (show === "ALL" || (entries[String(item.id)]?.quantity ?? "").trim() !== "")
  );

  function update(itemId: number, standardUnitId: number, patch: Partial<Entry>) {
    setEntries((current) => {
      const key = String(itemId);
      const base = current[key] ?? { quantity: "", unitId: String(standardUnitId), remarks: "" };
      return { ...current, [key]: { ...base, ...patch } };
    });
  }

  function reset() {
    setEntries({});
    setReason("");
    setRemarks("");
    setShowErrors(false);
    setSaved(null);
    setShow("ALL");
  }

  async function save() {
    setSaving(true);
    setSubmitError("");
    const payload: CountPayload = {
      reason: reason.trim(),
      remarks: remarks.trim() || null,
      lines: check.counted.map((line) => ({
        item_id: Number(line.itemId),
        quantity: line.quantity.trim(),
        unit_id: Number(line.unitId),
        remarks: line.remarks.trim() || null,
      })),
    };
    try {
      const response = await api.post<StockCount | CountReceipt>(STOCK_COUNTS_ENDPOINT, payload);
      setConfirming(false);
      if ("lines" in response) {
        toast.success(`${response.count_number} saved: the system balances were recorded.`);
        router.push(`/dashboard/stock-counts/${response.id}`);
      } else {
        setSaved(response);
      }
    } catch (err: unknown) {
      setConfirming(false);
      setSubmitError(errorMessage(err, "Unable to save the count."));
    } finally {
      setSaving(false);
    }
  }

  const back = viewer ? (
    <Link href="/dashboard/stock-counts" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
      <ArrowLeft size={15} aria-hidden />
      Stock counts
    </Link>
  ) : null;

  if (saved) {
    return (
      <div className="space-y-6 pb-6">
        <PageHeader eyebrow="Inventory" icon={ClipboardCheck} title="Count saved" />
        <Alert tone="success" title={`${saved.count_number} saved with ${saved.line_count} item${saved.line_count === 1 ? "" : "s"}`}>
          The system balances and differences were recorded by the server. Stock does not change until an Admin or Kitchen
          Manager approves an adjustment.
        </Alert>
        <Button icon={<ClipboardCheck size={16} aria-hidden />} onClick={reset}>Record another count</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-6">
      {back}
      <PageHeader
        eyebrow="Inventory"
        icon={ClipboardCheck}
        title="New stock count"
        description="Count what is physically in the store and enter the quantity found. Leave an item blank if you did not count it; enter 0 if none was found. You are recorded as the verifier."
      />

      <Alert tone="info" title="Blind count">
        <span className="inline-flex items-start gap-1.5">
          <EyeOff size={15} className="mt-0.5 shrink-0" aria-hidden />
          The system balance is not shown while you count. It is recorded when you save, together with the difference.
        </span>
      </Alert>

      {submitError && (
        <Alert tone="error" title="The count was not saved" onDismiss={() => setSubmitError("")}>{submitError}</Alert>
      )}

      <Card className="grid grid-cols-1 gap-4 p-5 md:grid-cols-2">
        <Field label="Reason for the count" required error={showErrors ? check.reason : undefined}>
          {({ id, describedBy }) => (
            <TextInput id={id} maxLength={500} aria-describedby={describedBy} value={reason}
              placeholder="e.g. Month-end store verification" onChange={(event) => setReason(event.target.value)} />
          )}
        </Field>
        <Field label="Remarks">
          {({ id }) => (
            <TextArea id={id} rows={1} maxLength={500} value={remarks} onChange={(event) => setRemarks(event.target.value)} />
          )}
        </Field>
      </Card>

      <Card>
        <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 lg:flex-row lg:items-end lg:justify-between">
          <SegmentedControl<Show>
            label="Items shown"
            value={show}
            onChange={setShow}
            options={[
              { value: "ALL", label: "All items", count: options.items.length },
              { value: "COUNTED", label: "Counted", count: check.counted.length },
            ]}
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,14rem)_minmax(0,12rem)] sm:items-end">
            <SearchInput value={search} onChange={setSearch} label="Search items" placeholder="Item name" />
            <Field label="Category">
              {({ id }) => (
                <SelectInput id={id} className="h-9" value={category} onChange={(event) => setCategory(event.target.value)}>
                  <option value="">All categories</option>
                  {categories.map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </SelectInput>
              )}
            </Field>
          </div>
        </div>

        {showErrors && check.form && <div className="px-5 pt-4"><Alert tone="error">{check.form}</Alert></div>}

        {visible.length === 0 ? (
          <EmptyState icon={ClipboardCheck} title="No items here" description={show === "COUNTED" ? "Nothing counted yet." : "Try another search or category."} />
        ) : (
          <ul className="divide-y divide-slate-100" aria-label="Items to count">
            {visible.map((item) => {
              const key = String(item.id);
              const entry = entries[key];
              const errors = showErrors ? check.lines[key] : undefined;
              const units = allowedUnits(options, key);
              const unitId = entry?.unitId ?? String(item.standard_unit_id);
              const counted = (entry?.quantity ?? "").trim() !== "";
              return (
                <li key={item.id} data-item={item.name}
                  className={`grid grid-cols-1 gap-3 px-5 py-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,0.8fr)_minmax(0,1.4fr)] sm:items-start ${counted ? "bg-brand-50/40" : ""}`}>
                  <div className="min-w-0 sm:pt-7">
                    <p className="flex items-center gap-1.5 font-medium text-slate-900">
                      {counted && <CircleCheck size={14} className="shrink-0 text-brand-600" aria-label="Counted" />}
                      <span className="truncate">{item.name}</span>
                    </p>
                    <p className="text-xs text-slate-500">{item.category_name ?? "Uncategorised"}</p>
                  </div>
                  <Field label="Quantity found" error={errors?.quantity}>
                    {({ id, describedBy }) => (
                      <TextInput id={id} inputMode="decimal" placeholder="Not counted" aria-describedby={describedBy}
                        aria-invalid={Boolean(errors?.quantity)} value={entry?.quantity ?? ""}
                        onChange={(event) => update(item.id, item.standard_unit_id, { quantity: event.target.value })} />
                    )}
                  </Field>
                  <Field label="Unit" error={errors?.unit}>
                    {({ id, describedBy }) => (
                      <SelectInput id={id} aria-describedby={describedBy} value={unitId}
                        onChange={(event) => update(item.id, item.standard_unit_id, { unitId: event.target.value })}>
                        {units.map((unit) => (
                          <option key={unit.id} value={unit.id}>{unit.symbol}</option>
                        ))}
                      </SelectInput>
                    )}
                  </Field>
                  <Field label="Line remarks">
                    {({ id }) => (
                      <TextInput id={id} maxLength={500} value={entry?.remarks ?? ""}
                        onChange={(event) => update(item.id, item.standard_unit_id, { remarks: event.target.value })} />
                    )}
                  </Field>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-slate-600">
          <span className="font-semibold text-slate-900">{check.counted.length}</span> item{check.counted.length === 1 ? "" : "s"} counted.
          A saved count cannot be changed; a mistake is corrected by counting again.
        </p>
        <div className="flex flex-col-reverse gap-2 sm:flex-row">
          <Button variant="secondary" onClick={() => router.push(leave)} disabled={saving}>Cancel</Button>
          <Button icon={<Save size={16} aria-hidden />}
            onClick={() => {
              setShowErrors(true);
              if (check.valid) setConfirming(true);
            }}>
            Save count
          </Button>
        </div>
      </Card>

      <ConfirmDialog
        open={confirming}
        tone="warning"
        title="Save this count?"
        description={
          <>
            {check.counted.length} item{check.counted.length === 1 ? "" : "s"} will be saved
            {check.counted.length > 0 && (
              <> ({check.counted.slice(0, 3).map((line) => {
                const item = options.items.find((entry) => String(entry.id) === line.itemId);
                return `${item?.name} ${line.quantity.trim()} ${unitSymbol(line.unitId)}`;
              }).join(", ")}{check.counted.length > 3 ? ", …" : ""})</>
            )}
            . The server records each item&apos;s system balance now, with the difference. Stock does not change until an
            adjustment is approved.
          </>
        }
        confirmLabel="Save count"
        busy={saving}
        onCancel={() => setConfirming(false)}
        onConfirm={save}
      />
    </div>
  );
}
