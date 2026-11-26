"use client";

import { useEffect, useRef, useState } from "react";
import type { SubmitEvent } from "react";

import { api } from "@/lib/api/client";
import { ENDPOINTS, billPaymentsEndpoint } from "@/lib/api/endpoints";
import {
  AMOUNT_PATTERN,
  PAYMENT_METHODS,
  errorMessage,
  fetchAllPages,
  formatDay,
  formatRupees,
  toAmount,
  todayISO,
  type BillBalance,
  type RecordPaymentResponse,
  type SupplierBalance,
} from "@/lib/payments";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Field, SelectInput, TextArea, TextInput } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";
import SearchSelect from "@/components/ui/SearchSelect";
import { useToast } from "@/components/ui/Toast";

type Props = {
  onClose: () => void;
  onRecorded: (result: RecordPaymentResponse) => void;
  /** Preselects this bill; supplier and bill are then fixed. */
  bill?: BillBalance;
};

type Errors = Partial<Record<"supplier" | "bill" | "amount" | "date" | "method", string>>;

const FORM_ID = "record-payment-form";

/** Whole paise, so comparisons never meet floating-point rounding. */
function toPaise(value: string): number {
  return Math.round(toAmount(value) * 100);
}

/**
 * Records a payment against one open supplier bill.
 *
 * Mount it only while open (the parent renders it conditionally), so every
 * opening starts from a clean form. The API repeats every check made here.
 */
export default function RecordPaymentModal({ onClose, onRecorded, bill }: Props) {
  const toast = useToast();
  const locked = Boolean(bill);

  const [suppliers, setSuppliers] = useState<SupplierBalance[] | null>(
    bill ? [] : null
  );
  const [loadError, setLoadError] = useState("");

  const [supplierId, setSupplierId] = useState(
    bill ? String(bill.supplier_id) : ""
  );
  const [bills, setBills] = useState<BillBalance[]>(bill ? [bill] : []);
  const [billsLoading, setBillsLoading] = useState(false);
  const [billId, setBillId] = useState(bill ? String(bill.purchase_id) : "");

  const [amount, setAmount] = useState(bill?.outstanding ?? "");
  const [paymentDate, setPaymentDate] = useState(todayISO);
  const [method, setMethod] = useState<string>("BANK_TRANSFER");
  const [reference, setReference] = useState("");
  const [remarks, setRemarks] = useState("");

  const [errors, setErrors] = useState<Errors>({});
  const [submitError, setSubmitError] = useState("");
  const [saving, setSaving] = useState(false);

  // Ignores a slower response for a supplier that is no longer selected.
  const billsRequest = useRef(0);

  useEffect(() => {
    if (bill) return;
    let active = true;

    fetchAllPages<SupplierBalance>(ENDPOINTS.supplierBalances)
      .then(({ items }) => {
        if (active) {
          setSuppliers(
            items.filter((row) => toAmount(row.outstanding) > 0)
          );
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setSuppliers([]);
          setLoadError(errorMessage(error, "Unable to load suppliers."));
        }
      });

    return () => {
      active = false;
    };
  }, [bill]);

  const selectedBill = bills.find((row) => String(row.purchase_id) === billId);
  const today = todayISO();

  function chooseSupplier(value: string) {
    setSupplierId(value);
    setBillId("");
    setBills([]);
    setAmount("");
    setLoadError("");
    setErrors((current) => ({ ...current, supplier: undefined, bill: undefined }));

    if (!value) return;

    const request = ++billsRequest.current;
    setBillsLoading(true);

    fetchAllPages<BillBalance>(
      `${ENDPOINTS.supplierBillBalances}?supplier_id=${value}&open_only=true`
    )
      .then(({ items }) => {
        if (request !== billsRequest.current) return;
        setBills(items);
        if (items.length === 1) {
          setBillId(String(items[0].purchase_id));
          setAmount(items[0].outstanding);
        }
      })
      .catch((error: unknown) => {
        if (request !== billsRequest.current) return;
        setLoadError(errorMessage(error, "Unable to load this supplier's bills."));
      })
      .finally(() => {
        if (request === billsRequest.current) setBillsLoading(false);
      });
  }

  function chooseBill(value: string) {
    setBillId(value);
    const next = bills.find((row) => String(row.purchase_id) === value);
    setAmount(next?.outstanding ?? "");
    setErrors((current) => ({ ...current, bill: undefined, amount: undefined }));
  }

  function validate(): Errors {
    const found: Errors = {};

    if (!locked && !supplierId) found.supplier = "Choose a supplier.";
    if (!selectedBill) {
      found.bill = "Choose the bill this payment settles.";
      return found;
    }

    const trimmed = amount.trim();
    if (!AMOUNT_PATTERN.test(trimmed)) {
      found.amount = "Enter an amount with up to two decimal places.";
    } else if (toPaise(trimmed) <= 0) {
      found.amount = "The amount must be more than zero.";
    } else if (toPaise(trimmed) > toPaise(selectedBill.outstanding)) {
      found.amount = `The amount cannot exceed the outstanding ${formatRupees(selectedBill.outstanding)}.`;
    }

    if (!paymentDate) {
      found.date = "Enter the payment date.";
    } else if (paymentDate > today) {
      found.date = "The payment date cannot be in the future.";
    } else if (paymentDate < selectedBill.purchase_date) {
      found.date = `The payment date cannot be earlier than the bill date (${formatDay(selectedBill.purchase_date)}).`;
    }

    if (!method) found.method = "Choose a payment method.";

    return found;
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError("");

    const found = validate();
    setErrors(found);
    if (Object.values(found).some(Boolean) || !selectedBill) return;

    setSaving(true);

    api
      .post<RecordPaymentResponse>(billPaymentsEndpoint(selectedBill.purchase_id), {
        payment_date: paymentDate,
        amount: amount.trim(),
        payment_method: method,
        reference_number: reference.trim() || null,
        remarks: remarks.trim() || null,
      })
      .then((result) => {
        toast.success(
          `Payment of ${formatRupees(result.payment.amount)} recorded for bill ${result.bill.invoice_number}.`
        );
        onRecorded(result);
      })
      .catch((error: unknown) => {
        setSubmitError(errorMessage(error, "The payment could not be recorded."));
      })
      .finally(() => setSaving(false));
  }

  const afterPayment =
    selectedBill && AMOUNT_PATTERN.test(amount.trim())
      ? Math.max(toPaise(selectedBill.outstanding) - toPaise(amount.trim()), 0) / 100
      : null;

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      dismissible={!saving}
      title="Record supplier payment"
      description="The payment counts towards the bill's balance straight away and is written to the audit log. Payments cannot be edited afterwards."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" form={FORM_ID} loading={saving}>
            Record payment
          </Button>
        </>
      }
    >
      <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-5">
        {submitError && (
          <Alert tone="error" title="Payment not recorded">
            {submitError}
          </Alert>
        )}
        {loadError && <Alert tone="error">{loadError}</Alert>}

        {locked && bill ? (
          <dl className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-slate-50/70 p-4 text-sm sm:grid-cols-2">
            <div className="min-w-0">
              <dt className="text-xs text-slate-500">Supplier</dt>
              <dd className="truncate font-medium text-slate-900">
                {bill.supplier_name ?? `Supplier #${bill.supplier_id}`}
              </dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-slate-500">Bill</dt>
              <dd className="truncate font-medium text-slate-900">
                {bill.invoice_number} · {formatDay(bill.purchase_date)}
              </dd>
            </div>
          </dl>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Supplier" required error={errors.supplier}>
              {({ id, describedBy }) => (
                <SearchSelect
                  id={id}
                  data-autofocus
                  aria-describedby={describedBy}
                  aria-invalid={Boolean(errors.supplier)}
                  value={supplierId}
                  disabled={saving}
                  loading={suppliers === null}
                  loadingText="Loading suppliers…"
                  noun="suppliers"
                  placeholder={suppliers?.length ? "Choose a supplier" : "No supplier is owed money"}
                  options={(suppliers ?? []).map((row) => ({
                    value: String(row.supplier_id),
                    label: `${row.supplier_name ?? `Supplier #${row.supplier_id}`} · ${formatRupees(row.outstanding)} owed`,
                  }))}
                  onChange={(value) => chooseSupplier(value)}
                />
              )}
            </Field>

            <Field
              label="Bill"
              required
              error={errors.bill}
              hint={supplierId && !billsLoading && !bills.length ? "This supplier has no open bills." : undefined}
            >
              {({ id, describedBy }) => (
                <SelectInput
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={Boolean(errors.bill)}
                  value={billId}
                  disabled={!supplierId || billsLoading || saving}
                  onChange={(event) => chooseBill(event.target.value)}
                >
                  <option value="">
                    {billsLoading ? "Loading bills…" : "Choose an open bill"}
                  </option>
                  {bills.map((row) => (
                    <option key={row.purchase_id} value={row.purchase_id}>
                      {row.invoice_number} · {formatDay(row.purchase_date)} ·{" "}
                      {formatRupees(row.outstanding)} due
                    </option>
                  ))}
                </SelectInput>
              )}
            </Field>
          </div>
        )}

        {selectedBill && (
          <dl className="grid grid-cols-2 gap-3 rounded-lg border border-slate-200 p-4 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs text-slate-500">Bill total</dt>
              <dd className="font-medium text-slate-900 tabular-nums">
                {formatRupees(selectedBill.grand_total)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Already paid</dt>
              <dd className="font-medium text-slate-900 tabular-nums">
                {formatRupees(selectedBill.paid_total)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Outstanding</dt>
              <dd className="font-semibold text-slate-900 tabular-nums">
                {formatRupees(selectedBill.outstanding)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">After this payment</dt>
              <dd className="font-medium text-slate-900 tabular-nums">
                {afterPayment === null ? "—" : formatRupees(afterPayment)}
              </dd>
            </div>
          </dl>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field
            label="Amount (₹)"
            required
            error={errors.amount}
            hint="Up to the outstanding balance, to the paisa."
          >
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                data-autofocus={locked ? true : undefined}
                aria-describedby={describedBy}
                aria-invalid={Boolean(errors.amount)}
                inputMode="decimal"
                autoComplete="off"
                placeholder="0.00"
                value={amount}
                disabled={saving}
                onChange={(event) => setAmount(event.target.value)}
                className="tabular-nums"
              />
            )}
          </Field>

          <Field label="Payment date" required error={errors.date}>
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                type="date"
                aria-describedby={describedBy}
                aria-invalid={Boolean(errors.date)}
                value={paymentDate}
                min={selectedBill?.purchase_date}
                max={today}
                disabled={saving}
                onChange={(event) => setPaymentDate(event.target.value)}
              />
            )}
          </Field>

          <Field label="Method" required error={errors.method}>
            {({ id, describedBy }) => (
              <SelectInput
                id={id}
                aria-describedby={describedBy}
                aria-invalid={Boolean(errors.method)}
                value={method}
                disabled={saving}
                onChange={(event) => setMethod(event.target.value)}
              >
                {PAYMENT_METHODS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </SelectInput>
            )}
          </Field>

          <Field
            label="Reference number"
            hint="UTR, cheque or receipt number. Used once per bill."
          >
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                aria-describedby={describedBy}
                maxLength={100}
                autoComplete="off"
                value={reference}
                disabled={saving}
                onChange={(event) => setReference(event.target.value)}
              />
            )}
          </Field>
        </div>

        <Field label="Remarks">
          {({ id, describedBy }) => (
            <TextArea
              id={id}
              aria-describedby={describedBy}
              maxLength={500}
              rows={2}
              value={remarks}
              disabled={saving}
              onChange={(event) => setRemarks(event.target.value)}
            />
          )}
        </Field>
      </form>
    </Modal>
  );
}
