"use client";

import { useEffect, useRef, useState } from "react";
import type { SubmitEvent } from "react";
import Link from "next/link";
import { Plus, Save, Trash2 } from "lucide-react";

import { api } from "@/lib/api/client";
import { OUTSOURCED_OPTIONS_ENDPOINT } from "@/lib/api/endpoints";
import type { OutsourcedOptions } from "@/lib/outsourced";
import {
  hasOrderErrors,
  lineTotal,
  sumMoney,
  validateOrder,
  type OrderDraft,
  type OrderErrors,
  type OrderLineDraft,
} from "@/lib/outsourcedMath";
import { errorMessage, formatRupees } from "@/lib/payments";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, SelectInput, TextArea, TextInput } from "@/components/ui/Field";
import IconButton from "@/components/ui/IconButton";
import SearchSelect from "@/components/ui/SearchSelect";
import { ErrorState, Spinner } from "@/components/ui/States";

export const emptyOutsourcedLine = (): OrderLineDraft => ({ itemId: "", quantity: "", unitId: "", rate: "", remarks: "" });

export const emptyOutsourcedDraft = (today: string): OrderDraft => ({
  orderDate: today,
  mealDate: today,
  sessionId: "",
  supplierId: "",
  notes: "",
  lines: [emptyOutsourcedLine()],
});

/**
 * The outsourced order form: meal date and exact meal session, supplier,
 * notes, and OUTSOURCED items with quantity, explicit unit and rate (the
 * planned cost; expenditure comes from the linked supplier bill). Used to
 * create an order and to edit a draft. ADMIN and KITCHEN_MANAGER only.
 */
export default function OutsourcedOrderForm({
  initial,
  submitLabel,
  cancelHref,
  onSubmit,
}: {
  /** null: a new order, started from the campus's today. */
  initial: OrderDraft | null;
  submitLabel: string;
  cancelHref: string;
  onSubmit: (draft: OrderDraft) => Promise<void>;
}) {
  const [options, setOptions] = useState<OutsourcedOptions | null>(null);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [draft, setDraft] = useState<OrderDraft | null>(initial);
  const nextKey = useRef(initial?.lines.length ?? 1);
  const [lineKeys, setLineKeys] = useState<number[]>(() => (initial?.lines ?? [null]).map((_l, i) => i));
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    let active = true;
    api
      .get<OutsourcedOptions>(OUTSOURCED_OPTIONS_ENDPOINT)
      .then((response) => {
        if (!active) return;
        setOptions(response);
        setDraft((current) => current ?? emptyOutsourcedDraft(response.today));
        setLoadError("");
      })
      .catch((err: unknown) => {
        if (active) setLoadError(errorMessage(err, "Unable to load meal sessions, suppliers and outsourced items."));
      });
    return () => {
      active = false;
    };
  }, [reloadKey]);

  if (loadError) {
    return (
      <Card>
        <ErrorState title="Couldn't load the order form" message={loadError}
          onRetry={() => { setLoadError(""); setReloadKey((key) => key + 1); }} />
      </Card>
    );
  }
  if (!options || !draft) {
    return (
      <Card>
        <CardBody>
          <Spinner label="Loading meal sessions, suppliers and outsourced items" />
        </CardBody>
      </Card>
    );
  }

  const errors: OrderErrors | null = showErrors ? validateOrder(draft, options.today, options.latest_meal_date) : null;
  const activeItems = options.items.filter((item) => item.is_active);
  const activeSuppliers = options.suppliers.filter((s) => s.is_active);
  const activeSessions = options.meal_sessions.filter((s) => s.is_active);
  const totals = draft.lines.map((line) => lineTotal(line.quantity, line.rate));
  const planned = sumMoney(totals);

  function setField<K extends keyof OrderDraft>(key: K, value: OrderDraft[K]) {
    setDraft((current) => (current ? { ...current, [key]: value } : current));
  }

  function setLine(index: number, patch: Partial<OrderLineDraft>) {
    setDraft((current) =>
      current ? { ...current, lines: current.lines.map((line, i) => (i === index ? { ...line, ...patch } : line)) } : current,
    );
  }

  function addLine() {
    setDraft((current) => (current ? { ...current, lines: [...current.lines, emptyOutsourcedLine()] } : current));
    setLineKeys((keys) => [...keys, nextKey.current++]);
  }

  function removeLine(index: number) {
    setDraft((current) => (current ? { ...current, lines: current.lines.filter((_l, i) => i !== index) } : current));
    setLineKeys((keys) => keys.filter((_k, i) => i !== index));
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft || !options) return;
    setShowErrors(true);
    setSubmitError("");
    if (hasOrderErrors(validateOrder(draft, options.today, options.latest_meal_date))) return;
    setSaving(true);
    onSubmit(draft)
      .catch((err: unknown) => setSubmitError(errorMessage(err, "The order could not be saved.")))
      .finally(() => setSaving(false));
  }

  // A draft may name a supplier, session or item deactivated since; keep it visible.
  const keep = <T extends { id: number; name: string }>(rows: T[], all: T[], value: string) =>
    !value || rows.some((row) => String(row.id) === value) ? rows : [...rows, ...all.filter((row) => String(row.id) === value)];
  const itemOptions = keep(activeItems, options.items, "").map((item) => ({ value: String(item.id), label: item.name }));

  return (
    <form onSubmit={submit} noValidate className="space-y-6" data-outsourced-form>
      {submitError && <Alert tone="error" title="Order not saved">{submitError}</Alert>}
      {errors && hasOrderErrors(errors) && <Alert tone="error">Check the highlighted fields.</Alert>}
      {activeItems.length === 0 && (
        <Alert tone="warning" title="No outsourced items">
          No item is classified as outsourced food yet. An Admin or Kitchen Manager sets an item&rsquo;s kind to
          &ldquo;Outsourced&rdquo; under Items; items with stock movements cannot be outsourced.
        </Alert>
      )}

      <Card>
        <CardHeader title="Meal and supplier" subtitle="The food is added to the meal record of this exact date and meal session." />
        <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Meal date" required error={errors?.mealDate}>
            {({ id, describedBy }) => (
              <TextInput id={id} type="date" aria-describedby={describedBy} aria-invalid={Boolean(errors?.mealDate)}
                min={draft.orderDate || undefined} max={options.latest_meal_date} value={draft.mealDate} disabled={saving}
                onChange={(event) => setField("mealDate", event.target.value)} />
            )}
          </Field>
          <Field label="Meal session" required error={errors?.session}>
            {({ id, describedBy }) => (
              <SelectInput id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors?.session)}
                value={draft.sessionId} disabled={saving} onChange={(event) => setField("sessionId", event.target.value)}>
                <option value="">Choose</option>
                {keep(activeSessions, options.meal_sessions, draft.sessionId).map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </SelectInput>
            )}
          </Field>
          <Field label="Supplier" required error={errors?.supplier}>
            {({ id, describedBy }) => (
              <SearchSelect id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors?.supplier)}
                value={draft.supplierId} disabled={saving} noun="suppliers"
                placeholder={activeSuppliers.length ? "Choose a supplier" : "No active suppliers"}
                options={keep(activeSuppliers, options.suppliers, draft.supplierId).map((s) => ({ value: String(s.id), label: s.name }))}
                onChange={(value) => setField("supplierId", value)} />
            )}
          </Field>
          <Field label="Order date" required error={errors?.orderDate}>
            {({ id, describedBy }) => (
              <TextInput id={id} type="date" max={options.today} aria-describedby={describedBy}
                aria-invalid={Boolean(errors?.orderDate)} value={draft.orderDate} disabled={saving}
                onChange={(event) => setField("orderDate", event.target.value)} />
            )}
          </Field>
          <Field label="Notes" className="sm:col-span-2 lg:col-span-4">
            {({ id }) => (
              <TextArea id={id} rows={2} maxLength={1000} value={draft.notes} disabled={saving}
                onChange={(event) => setField("notes", event.target.value)} />
            )}
          </Field>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Food ordered"
          subtitle={`${draft.lines.length} line${draft.lines.length === 1 ? "" : "s"} · planned cost ${formatRupees(planned)} (the supplier's bill is the expenditure)`}
        />
        <CardBody className="space-y-4">
          {errors?.lines && <Alert tone="error">{errors.lines}</Alert>}
          {draft.lines.map((line, index) => {
            const lineErrors = errors?.lineErrors[index] ?? {};
            const total = totals[index];
            return (
              <fieldset key={lineKeys[index]} className="rounded-lg border border-slate-200 p-4" aria-label={`Order line ${index + 1}`}>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,2.6fr)_minmax(0,1.1fr)_minmax(0,1.1fr)_minmax(0,1.2fr)_minmax(0,2fr)_auto] lg:items-start">
                  <Field label="Item" required error={lineErrors.item}>
                    {({ id, describedBy }) => (
                      <SearchSelect id={id} aria-describedby={describedBy} aria-invalid={Boolean(lineErrors.item)}
                        value={line.itemId} disabled={saving} noun="items"
                        placeholder={activeItems.length ? "Choose an outsourced item" : "No outsourced items"}
                        options={line.itemId && !itemOptions.some((o) => o.value === line.itemId)
                          ? [...itemOptions, ...options.items.filter((i) => String(i.id) === line.itemId).map((i) => ({ value: String(i.id), label: i.name }))]
                          : itemOptions}
                        onChange={(value) => {
                          const chosen = options.items.find((row) => String(row.id) === value);
                          setLine(index, { itemId: value, unitId: line.unitId || (chosen ? String(chosen.standard_unit_id) : "") });
                        }} />
                    )}
                  </Field>
                  <Field label="Quantity" required error={lineErrors.quantity}>
                    {({ id, describedBy }) => (
                      <TextInput id={id} aria-describedby={describedBy} aria-invalid={Boolean(lineErrors.quantity)}
                        inputMode="decimal" autoComplete="off" placeholder="0" className="tabular-nums"
                        value={line.quantity} disabled={saving} onChange={(event) => setLine(index, { quantity: event.target.value })} />
                    )}
                  </Field>
                  <Field label="Unit" required error={lineErrors.unit}>
                    {({ id, describedBy }) => (
                      <SelectInput id={id} aria-describedby={describedBy} aria-invalid={Boolean(lineErrors.unit)}
                        value={line.unitId} disabled={saving} onChange={(event) => setLine(index, { unitId: event.target.value })}>
                        <option value="">Choose</option>
                        {options.units.map((unit) => <option key={unit.id} value={unit.id}>{unit.symbol}</option>)}
                      </SelectInput>
                    )}
                  </Field>
                  <Field label="Rate (₹ per unit)" required error={lineErrors.rate}
                    hint={total ? `Line total ${formatRupees(total)}` : undefined}>
                    {({ id, describedBy }) => (
                      <TextInput id={id} aria-describedby={describedBy} aria-invalid={Boolean(lineErrors.rate)}
                        inputMode="decimal" autoComplete="off" placeholder="0.00" className="tabular-nums"
                        value={line.rate} disabled={saving} onChange={(event) => setLine(index, { rate: event.target.value })} />
                    )}
                  </Field>
                  <Field label="Line remarks">
                    {({ id }) => (
                      <TextInput id={id} maxLength={500} value={line.remarks} disabled={saving}
                        onChange={(event) => setLine(index, { remarks: event.target.value })} />
                    )}
                  </Field>
                  <div className="lg:pt-7">
                    <IconButton label={`Remove order line ${index + 1}`} icon={<Trash2 size={16} />} tone="danger"
                      disabled={saving || draft.lines.length === 1} onClick={() => removeLine(index)} />
                  </div>
                </div>
              </fieldset>
            );
          })}
          <Button variant="secondary" icon={<Plus size={15} aria-hidden />} disabled={saving} onClick={addLine}>Add item</Button>
        </CardBody>
      </Card>

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
        <Link href={cancelHref} className="inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-medium text-slate-600 hover:bg-slate-100">
          Cancel
        </Link>
        <Button type="submit" icon={<Save size={15} aria-hidden />} loading={saving}>{submitLabel}</Button>
      </div>
    </form>
  );
}
