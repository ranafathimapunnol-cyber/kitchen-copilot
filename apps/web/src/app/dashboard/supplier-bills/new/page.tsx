"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import type { SubmitEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, CheckCircle2, ClipboardList, FilePlus2, Plus, Trash2 } from "lucide-react";

import { api } from "@/lib/api/client";
import { ENDPOINTS, billableOrdersEndpoint, duplicateCheckEndpoint } from "@/lib/api/endpoints";
import { fetchAllRecords } from "@/lib/api/list";
import {
  billTotals,
  hasErrors,
  validateBillDraft,
  type BillDraft,
  type DraftErrors,
  type DraftLine,
} from "@/lib/billMath";
import {
  canRecordPayments,
  errorMessage,
  formatDay,
  formatRupees,
  newBillBalance,
  toAmount,
  todayISO,
  type SupplierBill,
  type SimilarBill,
} from "@/lib/payments";
import { billLinesFromOrder, exceedsOrder, trimQuantity } from "@/lib/orderForm";
import type { BillableOrder } from "@/lib/purchaseOrders";
import { allowedUnits } from "@/lib/units";
import BillAttachments from "@/components/payments/BillAttachments";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import RecordPaymentModal from "@/components/payments/RecordPaymentModal";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, SelectInput, TextArea, TextInput } from "@/components/ui/Field";
import IconButton from "@/components/ui/IconButton";
import PageHeader from "@/components/ui/PageHeader";
import SearchSelect from "@/components/ui/SearchSelect";
import { ErrorState, Spinner } from "@/components/ui/States";
import { useToast } from "@/components/ui/Toast";

type Supplier = { id: number; name: string; is_active: boolean };
type Item = {
  id: number;
  name: string;
  category_id: number;
  standard_unit_id: number;
  is_active: boolean;
};
type Unit = { id: number; name: string; symbol: string; dimension: string; is_active: boolean };
type Category = { id: number; name: string };
type Conversion = { from_unit_id: number; to_unit_id: number };

type MasterData = {
  suppliers: Supplier[];
  items: Item[];
  units: Unit[];
  categories: Category[];
  conversions: Conversion[];
};

const FORM_ID = "supplier-bill-form";

const emptyLine = (): DraftLine => ({
  itemId: "",
  quantity: "",
  unitId: "",
  unitRate: "",
  remarks: "",
});

const emptyDraft = (): BillDraft => ({
  supplierId: "",
  invoiceNumber: "",
  purchaseDate: todayISO(),
  discount: "",
  extraCharges: "",
  remarks: "",
  lines: [emptyLine()],
});

const byName = <T extends { name: string }>(a: T, b: T) => a.name.localeCompare(b.name);

// Units a line's item may be bought in: allowedUnits (lib/units), the same
// rule the API applies to bills and purchase orders.

const lineIsBlank = (line: DraftLine) =>
  !line.itemId && !line.quantity.trim() && !line.unitRate.trim() && !line.remarks.trim();

function NewSupplierBill() {
  // Arriving from a purchase order: ?supplier=…&order=… pre-selects both.
  const searchParams = useSearchParams();
  const { role, permissions } = useAuthorization();
  const canRecord = canRecordPayments(role, permissions);
  const toast = useToast();

  const [master, setMaster] = useState<MasterData | null>(null);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const [draft, setDraft] = useState<BillDraft>(() => ({
    ...emptyDraft(),
    supplierId: searchParams.get("supplier") ?? "",
  }));
  // Stable keys, so removing a line never moves another line's inputs.
  const nextKey = useRef(1);
  const [lineKeys, setLineKeys] = useState<number[]>([0]);
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [saved, setSaved] = useState<SupplierBill | null>(null);
  const [paying, setPaying] = useState(false);

  // Duplicate invoice check (PUR01), against bills already saved for this
  // supplier. An exact match would be refused; a possible match needs the
  // user to confirm it is a different bill before saving.
  const [duplicateCheck, setDuplicateCheck] = useState<{
    key: string;
    exact: boolean;
    possible: SimilarBill[];
  } | null>(null);
  const [confirmedDifferent, setConfirmedDifferent] = useState(false);
  const checkKey = `${draft.supplierId}|${draft.invoiceNumber.trim()}`;

  // Placed purchase orders of the chosen supplier (Stage 3): the bill may be
  // entered against one, linking its lines to the order's lines.
  const [orders, setOrders] = useState<{ supplierId: string; items: BillableOrder[] } | null>(null);
  const [orderId, setOrderId] = useState(() => searchParams.get("order") ?? "");

  useEffect(() => {
    const supplierId = draft.supplierId;
    if (!supplierId) return;
    let active = true;
    api
      .get<{ items: BillableOrder[] }>(billableOrdersEndpoint(supplierId))
      .then((result) => {
        if (active) setOrders({ supplierId, items: result.items });
      })
      .catch(() => {
        // Bills can always be entered without an order.
        if (active) setOrders({ supplierId, items: [] });
      });
    return () => {
      active = false;
    };
  }, [draft.supplierId]);

  const supplierOrders = orders?.supplierId === draft.supplierId ? orders.items : [];
  const selectedOrder = supplierOrders.find((order) => String(order.id) === orderId);
  const orderLineFor = (line: DraftLine) =>
    selectedOrder?.items.find((orderLine) => orderLine.id === line.orderLineId);

  function chooseOrder(value: string) {
    setOrderId(value);
    const order = supplierOrders.find((row) => String(row.id) === value);
    setDraft((current) => {
      // Links to another order's lines are dropped.
      const unlinked = current.lines.map((line) => ({ ...line, orderLineId: null }));
      if (!order || !unlinked.every(lineIsBlank)) return { ...current, lines: unlinked };
      const lines = billLinesFromOrder(order.items);
      return { ...current, lines: lines.length ? lines : unlinked };
    });
    setLineKeys((keys) => {
      const count = order && draft.lines.every(lineIsBlank)
        ? Math.max(billLinesFromOrder(order.items).length, 1)
        : keys.length;
      return count === keys.length ? keys : Array.from({ length: count }, () => nextKey.current++);
    });
  }

  function fillFromOrder() {
    if (!selectedOrder) return;
    const lines = billLinesFromOrder(selectedOrder.items);
    if (!lines.length) return;
    setDraft((current) => ({ ...current, lines }));
    setLineKeys(lines.map(() => nextKey.current++));
  }

  useEffect(() => {
    const supplierId = draft.supplierId;
    const invoice = draft.invoiceNumber.trim();
    let active = true;
    const timer = setTimeout(() => {
      if (!supplierId || !invoice) {
        if (active) setDuplicateCheck(null);
        return;
      }
      api
        .get<{ exact_duplicate: boolean; possible_duplicates: SimilarBill[] }>(
          duplicateCheckEndpoint(supplierId, invoice)
        )
        .then((result) => {
          if (active) {
            setDuplicateCheck({
              key: `${supplierId}|${invoice}`,
              exact: result.exact_duplicate,
              possible: result.possible_duplicates,
            });
          }
        })
        .catch(() => {
          // The save itself still refuses an exact duplicate.
        });
    }, 400);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [draft.supplierId, draft.invoiceNumber]);

  // Only a check for the numbers now on screen counts.
  const check = duplicateCheck?.key === checkKey ? duplicateCheck : null;
  const exactDuplicate = Boolean(check?.exact);
  const possibleDuplicates = check?.possible ?? [];

  useEffect(() => {
    let active = true;

    Promise.all([
      fetchAllRecords<Supplier>(ENDPOINTS.suppliers),
      fetchAllRecords<Item>(ENDPOINTS.items),
      fetchAllRecords<Unit>(ENDPOINTS.units),
      fetchAllRecords<Category>(ENDPOINTS.categories),
      fetchAllRecords<Conversion>(ENDPOINTS.unitConversions),
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
        if (active) {
          setLoadError(
            errorMessage(err, "Unable to load suppliers, items and units.")
          );
        }
      });

    return () => {
      active = false;
    };
  }, [reloadKey]);

  const unitsFor = (line: DraftLine) =>
    master ? allowedUnits(master, line.itemId).map((unit) => String(unit.id)) : [];
  const errors: DraftErrors | null = showErrors ? validateBillDraft(draft, unitsFor) : null;
  const totals = billTotals(draft);

  function setField<K extends keyof BillDraft>(key: K, value: BillDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function setLine(index: number, patch: Partial<DraftLine>) {
    setDraft((current) => ({
      ...current,
      lines: current.lines.map((line, i) => (i === index ? { ...line, ...patch } : line)),
    }));
  }

  function chooseItem(index: number, itemId: string) {
    const item = master?.items.find((row) => String(row.id) === itemId);
    // Start each line in the item's standard unit. A line linked to an
    // order line keeps the link only while it bills the same item.
    const orderLine = orderLineFor(draft.lines[index]);
    setLine(index, {
      itemId,
      unitId: item ? String(item.standard_unit_id) : "",
      ...(orderLine && String(orderLine.item_id) !== itemId ? { orderLineId: null } : {}),
    });
  }

  function addLine() {
    setDraft((current) => ({ ...current, lines: [...current.lines, emptyLine()] }));
    setLineKeys((keys) => [...keys, nextKey.current++]);
  }

  function removeLine(index: number) {
    setDraft((current) => ({
      ...current,
      lines: current.lines.filter((_, i) => i !== index),
    }));
    setLineKeys((keys) => keys.filter((_, i) => i !== index));
  }

  function startAnother() {
    setConfirmedDifferent(false);
    setOrderId("");
    setDraft(emptyDraft());
    setLineKeys([nextKey.current++]);
    setShowErrors(false);
    setSubmitError("");
    setSaved(null);
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setShowErrors(true);
    setSubmitError("");

    if (hasErrors(validateBillDraft(draft, unitsFor))) return;
    if (exactDuplicate) {
      setSubmitError("This supplier already has a bill with this invoice number.");
      return;
    }
    if (possibleDuplicates.length > 0 && !confirmedDifferent) {
      setSubmitError("Confirm that this is a different bill from the similar invoices shown.");
      return;
    }

    setSaving(true);

    api
      .post<SupplierBill>(ENDPOINTS.supplierBills, {
        supplier_id: Number(draft.supplierId),
        invoice_number: draft.invoiceNumber.trim(),
        purchase_date: draft.purchaseDate,
        discount: draft.discount.trim() || "0",
        extra_charges: draft.extraCharges.trim() || "0",
        remarks: draft.remarks.trim() || null,
        purchase_order_id: selectedOrder ? selectedOrder.id : null,
        items: draft.lines.map((line) => ({
          item_id: Number(line.itemId),
          quantity: line.quantity.trim(),
          unit_id: Number(line.unitId),
          unit_rate: line.unitRate.trim(),
          remarks: line.remarks.trim() || null,
          purchase_order_item_id: selectedOrder && orderLineFor(line) ? line.orderLineId : null,
        })),
      })
      .then((bill) => {
        setSaved(bill);
        toast.success(`Bill ${bill.invoice_number} saved.`);
      })
      .catch((err: unknown) => {
        setSubmitError(errorMessage(err, "The bill could not be saved."));
      })
      .finally(() => setSaving(false));
  }

  const backLink = (
    <Link
      href="/dashboard/supplier-bills"
      className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
    >
      <ArrowLeft size={15} aria-hidden />
      All bills
    </Link>
  );

  const header = (
    <PageHeader
      eyebrow="Purchasing"
      icon={FilePlus2}
      title="New supplier bill"
      description="Enter the bill exactly as the supplier issued it. Line totals are quantity × unit rate, worked out to the paisa; discount and extra charges are kept separate."
      actions={backLink}
    />
  );

  if (saved) {
    const balance = newBillBalance(saved);
    return (
      <div className="space-y-6 pb-6">
        {header}
        <Card>
          <CardBody className="space-y-5">
            <div className="flex items-start gap-3">
              <CheckCircle2 size={22} aria-hidden className="mt-0.5 shrink-0 text-emerald-600" />
              <div className="min-w-0">
                <h2 className="text-lg font-semibold text-slate-900">
                  Bill {saved.invoice_number} saved
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  {saved.supplier_name} · {formatDay(saved.purchase_date)} ·{" "}
                  {saved.purchase_order_number && <>against {saved.purchase_order_number} · </>}
                  {saved.items.length} line{saved.items.length === 1 ? "" : "s"} · total{" "}
                  <span className="font-semibold text-slate-900">
                    {formatRupees(saved.grand_total)}
                  </span>
                </p>
              </div>
            </div>
            {saved.flagged_as_possible_duplicate && (
              <Alert tone="warning" title="Flagged as a possible duplicate">
                Similar invoice numbers from this supplier:{" "}
                {(saved.possible_duplicates ?? []).map((bill) => bill.invoice_number).join(", ")}.
                It is listed under Possible duplicates until it is reviewed.
              </Alert>
            )}
            <BillAttachments purchaseId={saved.id} canUpload />
            <div className="flex flex-wrap gap-2">
              {canRecord && toAmount(saved.grand_total) > 0 && (
                <Button onClick={() => setPaying(true)}>Record payment</Button>
              )}
              <Button variant="secondary" onClick={startAnother}>
                Enter another bill
              </Button>
              {backLink}
            </div>
          </CardBody>
        </Card>

        {paying && (
          <RecordPaymentModal
            bill={balance}
            onClose={() => setPaying(false)}
            onRecorded={() => setPaying(false)}
          />
        )}
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="space-y-6 pb-6">
        {header}
        <Card>
          <ErrorState
            title="Couldn't load the bill form"
            message={`${loadError} Entering a bill needs read access to suppliers, items and units.`}
            onRetry={() => {
              setLoadError("");
              setReloadKey((key) => key + 1);
            }}
          />
        </Card>
      </div>
    );
  }

  if (!master) {
    return (
      <div className="space-y-6 pb-6">
        {header}
        <Card>
          <CardBody>
            <Spinner label="Loading suppliers, items and units" />
          </CardBody>
        </Card>
      </div>
    );
  }

  const categoryName = (itemId: string) => {
    const item = master.items.find((row) => String(row.id) === itemId);
    return master.categories.find((c) => c.id === item?.category_id)?.name;
  };
  const itemOptions = master.items.map((item) => ({ value: String(item.id), label: item.name }));

  return (
    <div className="space-y-6 pb-6">
      {header}

      <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-6">
        {submitError && (
          <Alert tone="error" title="Bill not saved">
            {submitError}
          </Alert>
        )}
        {errors && hasErrors(errors) && (
          <Alert tone="error">Check the highlighted fields.</Alert>
        )}

        <Card>
          <CardHeader title="Bill details" />
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
                  options={master.suppliers.map((row) => ({ value: String(row.id), label: row.name }))}
                  onChange={(value) => {
                    setConfirmedDifferent(false);
                    setOrderId("");
                    setDraft((current) => ({
                      ...current,
                      supplierId: value,
                      lines: current.lines.map((line) => ({ ...line, orderLineId: null })),
                    }));
                  }}
                />
              )}
            </Field>

            <Field
              label="Invoice number"
              required
              error={
                errors?.invoiceNumber ??
                (exactDuplicate
                  ? "This supplier already has a bill with this invoice number."
                  : undefined)
              }
            >
              {({ id, describedBy }) => (
                <TextInput
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={Boolean(errors?.invoiceNumber)}
                  maxLength={100}
                  autoComplete="off"
                  value={draft.invoiceNumber}
                  disabled={saving}
                  onChange={(event) => {
                    setConfirmedDifferent(false);
                    setField("invoiceNumber", event.target.value);
                  }}
                />
              )}
            </Field>

            <Field label="Bill date" required error={errors?.purchaseDate}>
              {({ id, describedBy }) => (
                <TextInput
                  id={id}
                  type="date"
                  aria-describedby={describedBy}
                  aria-invalid={Boolean(errors?.purchaseDate)}
                  value={draft.purchaseDate}
                  disabled={saving}
                  onChange={(event) => setField("purchaseDate", event.target.value)}
                />
              )}
            </Field>

            {supplierOrders.length > 0 && (
              <div className="space-y-3 sm:col-span-3" data-order-picker>
                <Field
                  label="Against purchase order"
                  hint="Optional. Links the bill's lines to what was ordered, so ordered, billed and received quantities can be compared."
                >
                  {({ id, describedBy }) => (
                    <SelectInput
                      id={id}
                      aria-describedby={describedBy}
                      value={orderId}
                      disabled={saving}
                      onChange={(event) => chooseOrder(event.target.value)}
                    >
                      <option value="">Not against an order</option>
                      {supplierOrders.map((order) => (
                        <option key={order.id} value={order.id}>
                          {order.order_number} · ordered {formatDay(order.order_date)}
                        </option>
                      ))}
                    </SelectInput>
                  )}
                </Field>
                {selectedOrder && !draft.lines.some((line) => orderLineFor(line)) && (
                  <Alert tone="info">
                    <span className="flex flex-wrap items-center gap-3">
                      <span>Fill the items from {selectedOrder.order_number}? This replaces the lines below.</span>
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={<ClipboardList size={14} aria-hidden />}
                        onClick={fillFromOrder}
                      >
                        Use order lines
                      </Button>
                    </span>
                  </Alert>
                )}
              </div>
            )}

            <Field label="Bill remarks" className="sm:col-span-3">
              {({ id, describedBy }) => (
                <TextArea
                  id={id}
                  aria-describedby={describedBy}
                  rows={2}
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
            title="Items"
            subtitle={`${draft.lines.length} line${draft.lines.length === 1 ? "" : "s"}`}
          />
          <CardBody className="space-y-4">
            {errors?.lines && <Alert tone="error">{errors.lines}</Alert>}

            {draft.lines.map((line, index) => {
              const lineErrors = errors?.lineErrors[index] ?? {};
              const units = allowedUnits(master, line.itemId);
              const category = categoryName(line.itemId);

              return (
                <fieldset
                  key={lineKeys[index]}
                  className="rounded-lg border border-slate-200 p-4"
                  aria-label={`Line ${index + 1}`}
                >
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,3fr)_minmax(0,1.2fr)_minmax(0,1.2fr)_minmax(0,1.4fr)_minmax(0,1.3fr)_auto] lg:items-start">
                    <Field
                      label="Item"
                      required
                      error={lineErrors.item}
                      hint={category ? `Category: ${category}` : undefined}
                    >
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
                          onChange={(value) => chooseItem(index, value)}
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
                          value={line.quantity}
                          disabled={saving}
                          onChange={(event) => setLine(index, { quantity: event.target.value })}
                          className="tabular-nums"
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

                    <Field label="Unit rate (₹)" required error={lineErrors.unitRate}>
                      {({ id, describedBy }) => (
                        <TextInput
                          id={id}
                          aria-describedby={describedBy}
                          aria-invalid={Boolean(lineErrors.unitRate)}
                          inputMode="decimal"
                          autoComplete="off"
                          placeholder="0.00"
                          value={line.unitRate}
                          disabled={saving}
                          onChange={(event) => setLine(index, { unitRate: event.target.value })}
                          className="tabular-nums"
                        />
                      )}
                    </Field>

                    <div className="min-w-0 space-y-1.5">
                      <p className="text-sm font-medium text-slate-700">Line total</p>
                      <p
                        className="flex h-10 items-center text-sm font-semibold text-slate-900 tabular-nums"
                        aria-live="polite"
                        data-line-total
                      >
                        {totals.lineTotals[index] === null
                          ? "—"
                          : formatRupees(totals.lineTotals[index])}
                      </p>
                    </div>

                    <div className="lg:pt-7">
                      <IconButton
                        label={`Remove line ${index + 1}`}
                        icon={<Trash2 size={16} />}
                        tone="danger"
                        disabled={saving || draft.lines.length === 1}
                        onClick={() => removeLine(index)}
                      />
                    </div>
                  </div>

                  {(() => {
                    const orderLine = orderLineFor(line);
                    if (!orderLine || !selectedOrder) return null;
                    const over = exceedsOrder(line.quantity, line.unitId, orderLine);
                    return (
                      <p className="mt-3 text-xs text-slate-600" data-order-line-hint>
                        <span className="font-medium text-brand-700">{selectedOrder.order_number}</span>: ordered{" "}
                        {trimQuantity(orderLine.ordered_quantity)} {orderLine.unit_symbol}, already billed{" "}
                        {trimQuantity(orderLine.billed_quantity)} {orderLine.unit_symbol}, left to bill{" "}
                        {trimQuantity(orderLine.left_to_bill)}{" "}
                        {orderLine.unit_symbol}.
                        {over && (
                          <span className="ml-1 font-medium text-amber-700" data-over-order>
                            This bills more than is left on the order. It will be saved as entered and shown on the order.
                          </span>
                        )}
                      </p>
                    );
                  })()}

                  <Field label="Line remarks" error={lineErrors.remarks} className="mt-3">
                    {({ id, describedBy }) => (
                      <TextInput
                        id={id}
                        aria-describedby={describedBy}
                        maxLength={500}
                        value={line.remarks}
                        disabled={saving}
                        onChange={(event) => setLine(index, { remarks: event.target.value })}
                      />
                    )}
                  </Field>
                </fieldset>
              );
            })}

            <Button
              variant="secondary"
              icon={<Plus size={15} aria-hidden />}
              disabled={saving}
              onClick={addLine}
            >
              Add line
            </Button>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Totals" />
          <CardBody className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Discount (₹)" error={errors?.discount}>
                {({ id, describedBy }) => (
                  <TextInput
                    id={id}
                    aria-describedby={describedBy}
                    aria-invalid={Boolean(errors?.discount)}
                    inputMode="decimal"
                    autoComplete="off"
                    placeholder="0.00"
                    value={draft.discount}
                    disabled={saving}
                    onChange={(event) => setField("discount", event.target.value)}
                    className="tabular-nums"
                  />
                )}
              </Field>
              <Field label="Extra charges (₹)" error={errors?.extraCharges}>
                {({ id, describedBy }) => (
                  <TextInput
                    id={id}
                    aria-describedby={describedBy}
                    aria-invalid={Boolean(errors?.extraCharges)}
                    inputMode="decimal"
                    autoComplete="off"
                    placeholder="0.00"
                    value={draft.extraCharges}
                    disabled={saving}
                    onChange={(event) => setField("extraCharges", event.target.value)}
                    className="tabular-nums"
                  />
                )}
              </Field>
            </div>

            <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 self-end text-sm" data-bill-totals>
              <dt className="text-slate-500">Subtotal</dt>
              <dd className="text-right tabular-nums">{formatRupees(totals.subtotal)}</dd>
              <dt className="text-slate-500">Discount</dt>
              <dd className="text-right tabular-nums">− {formatRupees(totals.discount)}</dd>
              <dt className="text-slate-500">Extra charges</dt>
              <dd className="text-right tabular-nums">+ {formatRupees(totals.extraCharges)}</dd>
              <div aria-hidden className="col-span-2 my-1 border-t border-slate-200" />
              <dt className="font-semibold text-slate-900">Bill total</dt>
              <dd
                className="text-right text-base font-semibold text-slate-900 tabular-nums"
                data-grand-total
              >
                {totals.complete ? formatRupees(totals.grandTotal) : "—"}
              </dd>
            </dl>
          </CardBody>
        </Card>

        {possibleDuplicates.length > 0 && !exactDuplicate && (
          <Alert tone="warning" title="Possible duplicate invoice">
            <p>
              This supplier already has bills whose invoice numbers match once
              case, spaces and punctuation are ignored:
            </p>
            <ul className="mt-1 list-disc pl-5" data-similar-invoices>
              {possibleDuplicates.map((bill) => (
                <li key={bill.purchase_id}>
                  {bill.invoice_number} · {formatDay(bill.purchase_date)} ·{" "}
                  {formatRupees(bill.grand_total)}
                </li>
              ))}
            </ul>
            <label className="mt-3 flex items-start gap-2 font-medium">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4"
                checked={confirmedDifferent}
                onChange={(event) => setConfirmedDifferent(event.target.checked)}
                data-confirm-different
              />
              I have checked: this is a different bill. It will be saved and
              flagged for review.
            </label>
          </Alert>
        )}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Link
            href="/dashboard/supplier-bills"
            className="inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          >
            Cancel
          </Link>
          <Button type="submit" form={FORM_ID} loading={saving}>
            Save bill
          </Button>
        </div>
      </form>
    </div>
  );
}

function KeyedNewSupplierBill() {
  // The page is kept (hidden) by Next.js between visits. Arriving with a
  // different supplier/order to pre-select starts the form afresh, so the
  // pre-selection is never lost to a form kept from an earlier visit.
  const presets = useSearchParams().toString();
  return <NewSupplierBill key={presets} />;
}

export default function NewSupplierBillPage() {
  return (
    <Suspense
      fallback={
        <Card>
          <CardBody>
            <Spinner label="Loading the bill form" />
          </CardBody>
        </Card>
      }
    >
      <KeyedNewSupplierBill />
    </Suspense>
  );
}
