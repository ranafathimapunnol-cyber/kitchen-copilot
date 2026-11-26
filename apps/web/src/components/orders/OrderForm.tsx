"use client";

import { useEffect, useRef, useState } from "react";
import type { SubmitEvent } from "react";
import Link from "next/link";
import { Plus, Save, Trash2 } from "lucide-react";

import { ENDPOINTS } from "@/lib/api/endpoints";
import { fetchAllRecords } from "@/lib/api/list";
import {
  hasOrderErrors,
  validateOrderDraft,
  type OrderDraft,
  type OrderErrors,
  type OrderLineDraft,
} from "@/lib/orderForm";
import { errorMessage, todayISO } from "@/lib/payments";
import { allowedUnits, type ConversionRecord, type UnitRecord } from "@/lib/units";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, SelectInput, TextArea, TextInput } from "@/components/ui/Field";
import IconButton from "@/components/ui/IconButton";
import SearchSelect from "@/components/ui/SearchSelect";
import { ErrorState, Spinner } from "@/components/ui/States";

type Supplier = { id: number; name: string; is_active: boolean };
type Item = { id: number; name: string; category_id: number; standard_unit_id: number; is_active: boolean };
type Category = { id: number; name: string };
type MasterData = {
  suppliers: Supplier[];
  items: Item[];
  units: UnitRecord[];
  categories: Category[];
  conversions: ConversionRecord[];
};

const byName = <T extends { name: string }>(a: T, b: T) => a.name.localeCompare(b.name);

export const emptyOrderLine = (): OrderLineDraft => ({ itemId: "", quantity: "", unitId: "", remarks: "" });

export const emptyOrderDraft = (): OrderDraft => ({
  supplierId: "",
  orderDate: todayISO(),
  expectedDate: "",
  remarks: "",
  lines: [emptyOrderLine()],
});

/**
 * The purchase-order form: supplier, dates, remarks and item lines (item,
 * quantity, unit). Used to create an order and to edit a draft. Items and
 * units follow the same rules as bill entry.
 */
export default function OrderForm({
  initial,
  submitLabel,
  cancelHref,
  onSubmit,
}: {
  initial: OrderDraft;
  submitLabel: string;
  cancelHref: string;
  /** Resolves when saved; rejects with the API's message. */
  onSubmit: (draft: OrderDraft) => Promise<void>;
}) {
  const [master, setMaster] = useState<MasterData | null>(null);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [draft, setDraft] = useState<OrderDraft>(initial);
  const nextKey = useRef(initial.lines.length);
  const [lineKeys, setLineKeys] = useState<number[]>(() => initial.lines.map((_line, index) => index));
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchAllRecords<Supplier>(ENDPOINTS.suppliers),
      fetchAllRecords<Item>(ENDPOINTS.items),
      fetchAllRecords<UnitRecord>(ENDPOINTS.units),
      fetchAllRecords<Category>(ENDPOINTS.categories),
      fetchAllRecords<ConversionRecord>(ENDPOINTS.unitConversions),
    ])
      .then(([suppliers, items, units, categories, conversions]) => {
        if (!active) return;
        setMaster({
          suppliers: suppliers.rows.filter((row) => row.is_active).sort(byName),
          items: items.rows.filter((row) => row.is_active).sort(byName),
          units: units.rows,
          categories: categories.rows,
          conversions: conversions.rows,
        });
        setLoadError("");
      })
      .catch((err: unknown) => {
        if (active) setLoadError(errorMessage(err, "Unable to load suppliers, items and units."));
      });
    return () => {
      active = false;
    };
  }, [reloadKey]);

  const today = todayISO();
  const unitsFor = (line: OrderLineDraft) =>
    master ? allowedUnits(master, line.itemId).map((unit) => String(unit.id)) : [];
  const errors: OrderErrors | null = showErrors ? validateOrderDraft(draft, unitsFor, today) : null;

  function setField<K extends keyof OrderDraft>(key: K, value: OrderDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function setLine(index: number, patch: Partial<OrderLineDraft>) {
    setDraft((current) => ({
      ...current,
      lines: current.lines.map((line, i) => (i === index ? { ...line, ...patch } : line)),
    }));
  }

  function addLine() {
    setDraft((current) => ({ ...current, lines: [...current.lines, emptyOrderLine()] }));
    setLineKeys((keys) => [...keys, nextKey.current++]);
  }

  function removeLine(index: number) {
    setDraft((current) => ({ ...current, lines: current.lines.filter((_line, i) => i !== index) }));
    setLineKeys((keys) => keys.filter((_key, i) => i !== index));
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setShowErrors(true);
    setSubmitError("");
    if (hasOrderErrors(validateOrderDraft(draft, unitsFor, today))) return;
    setSaving(true);
    onSubmit(draft)
      .catch((err: unknown) => setSubmitError(errorMessage(err, "The order could not be saved.")))
      .finally(() => setSaving(false));
  }

  if (loadError) {
    return (
      <Card>
        <ErrorState
          title="Couldn't load the order form"
          message={`${loadError} Ordering needs read access to suppliers, items and units.`}
          onRetry={() => {
            setLoadError("");
            setReloadKey((key) => key + 1);
          }}
        />
      </Card>
    );
  }

  if (!master) {
    return (
      <Card>
        <CardBody>
          <Spinner label="Loading suppliers, items and units" />
        </CardBody>
      </Card>
    );
  }

  // A draft may name a supplier or item deactivated since; keep it visible.
  const supplierOptions = master.suppliers.some((row) => String(row.id) === draft.supplierId) || !draft.supplierId
    ? master.suppliers
    : [...master.suppliers, { id: Number(draft.supplierId), name: "Inactive supplier", is_active: false }];
  const itemOptions = master.items.map((row) => ({ value: String(row.id), label: row.name }));

  return (
    <form onSubmit={submit} noValidate className="space-y-6" data-order-form>
      {submitError && (
        <Alert tone="error" title="Order not saved">
          {submitError}
        </Alert>
      )}
      {errors && hasOrderErrors(errors) && <Alert tone="error">Check the highlighted fields.</Alert>}

      <Card>
        <CardHeader title="Order details" />
        <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Field label="Supplier" required error={errors?.supplier}>
            {({ id, describedBy }) => (
              <SearchSelect
                id={id}
                aria-describedby={describedBy}
                aria-invalid={Boolean(errors?.supplier)}
                value={draft.supplierId}
                disabled={saving}
                noun="suppliers"
                placeholder={master.suppliers.length ? "Choose a supplier" : "No active suppliers"}
                options={supplierOptions.map((row) => ({ value: String(row.id), label: row.name }))}
                onChange={(value) => setField("supplierId", value)}
              />
            )}
          </Field>
          <Field label="Order date" required error={errors?.orderDate}>
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                type="date"
                max={today}
                aria-describedby={describedBy}
                aria-invalid={Boolean(errors?.orderDate)}
                value={draft.orderDate}
                disabled={saving}
                onChange={(event) => setField("orderDate", event.target.value)}
              />
            )}
          </Field>
          <Field label="Expected delivery" hint="Optional" error={errors?.expectedDate}>
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                type="date"
                min={draft.orderDate || undefined}
                aria-describedby={describedBy}
                aria-invalid={Boolean(errors?.expectedDate)}
                value={draft.expectedDate}
                disabled={saving}
                onChange={(event) => setField("expectedDate", event.target.value)}
              />
            )}
          </Field>
          <Field label="Order remarks" className="sm:col-span-3">
            {({ id, describedBy }) => (
              <TextArea
                id={id}
                aria-describedby={describedBy}
                rows={2}
                maxLength={1000}
                value={draft.remarks}
                disabled={saving}
                onChange={(event) => setField("remarks", event.target.value)}
              />
            )}
          </Field>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Items to order"
          subtitle={`${draft.lines.length} line${draft.lines.length === 1 ? "" : "s"} · quantities only; prices come from the supplier's bill`}
        />
        <CardBody className="space-y-4">
          {errors?.lines && <Alert tone="error">{errors.lines}</Alert>}
          {draft.lines.map((line, index) => {
            const lineErrors = errors?.lineErrors[index] ?? {};
            const units = allowedUnits(master, line.itemId);
            const item = master.items.find((row) => String(row.id) === line.itemId);
            const category = master.categories.find((row) => row.id === item?.category_id)?.name;
            return (
              <fieldset
                key={lineKeys[index]}
                className="rounded-lg border border-slate-200 p-4"
                aria-label={`Order line ${index + 1}`}
              >
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,3fr)_minmax(0,1.3fr)_minmax(0,1.2fr)_minmax(0,2.5fr)_auto] lg:items-start">
                  <Field label="Item" required error={lineErrors.item} hint={category ? `Category: ${category}` : undefined}>
                    {({ id, describedBy }) => (
                      <SearchSelect
                        id={id}
                        aria-describedby={describedBy}
                        aria-invalid={Boolean(lineErrors.item)}
                        value={line.itemId}
                        disabled={saving}
                        noun="items"
                        placeholder={master.items.length ? "Choose an item" : "No active items"}
                        options={itemOptions}
                        onChange={(value) => {
                          const chosen = master.items.find((row) => String(row.id) === value);
                          setLine(index, {
                            itemId: value,
                            unitId: chosen ? String(chosen.standard_unit_id) : "",
                          });
                        }}
                      />
                    )}
                  </Field>
                  <Field label="Quantity" required error={lineErrors.quantity}>
                    {({ id, describedBy }) => (
                      <TextInput
                        id={id}
                        aria-describedby={describedBy}
                        aria-invalid={Boolean(lineErrors.quantity)}
                        inputMode="decimal"
                        autoComplete="off"
                        placeholder="0"
                        className="tabular-nums"
                        value={line.quantity}
                        disabled={saving}
                        onChange={(event) => setLine(index, { quantity: event.target.value })}
                      />
                    )}
                  </Field>
                  <Field label="Unit" required error={lineErrors.unit}>
                    {({ id, describedBy }) => (
                      <SelectInput
                        id={id}
                        aria-describedby={describedBy}
                        aria-invalid={Boolean(lineErrors.unit)}
                        value={line.unitId}
                        disabled={saving || !line.itemId}
                        onChange={(event) => setLine(index, { unitId: event.target.value })}
                      >
                        <option value="">{line.itemId ? "Choose" : "—"}</option>
                        {units.map((unit) => (
                          <option key={unit.id} value={unit.id}>
                            {unit.symbol}
                          </option>
                        ))}
                      </SelectInput>
                    )}
                  </Field>
                  <Field label="Line remarks">
                    {({ id }) => (
                      <TextInput
                        id={id}
                        maxLength={500}
                        value={line.remarks}
                        disabled={saving}
                        onChange={(event) => setLine(index, { remarks: event.target.value })}
                      />
                    )}
                  </Field>
                  <div className="lg:pt-7">
                    <IconButton
                      label={`Remove order line ${index + 1}`}
                      icon={<Trash2 size={16} />}
                      tone="danger"
                      disabled={saving || draft.lines.length === 1}
                      onClick={() => removeLine(index)}
                    />
                  </div>
                </div>
              </fieldset>
            );
          })}
          <Button variant="secondary" icon={<Plus size={15} aria-hidden />} disabled={saving} onClick={addLine}>
            Add item
          </Button>
        </CardBody>
      </Card>

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
        <Link
          href={cancelHref}
          className="inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-medium text-slate-600 hover:bg-slate-100"
        >
          Cancel
        </Link>
        <Button type="submit" icon={<Save size={15} aria-hidden />} loading={saving}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
