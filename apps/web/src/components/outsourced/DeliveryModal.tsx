"use client";

import { useState } from "react";

import { api } from "@/lib/api/client";
import { outsourcedDeliveryEndpoint, outsourcedOrderActionEndpoint } from "@/lib/api/endpoints";
import { Q6_NOTE, type OutsourcedDelivery, type OutsourcedOrderDetail } from "@/lib/outsourced";
import {
  acceptedText,
  deliveryPayload,
  hasDeliveryErrors,
  milli,
  fromMilli,
  validateDelivery,
  type DeliveryLineDraft,
} from "@/lib/outsourcedMath";
import { errorMessage, formatDay, todayISO } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";

/**
 * Record (or correct a draft) delivery: per ordered item, received,
 * rejected (with a reason) and accepted = received − rejected. Saved as a
 * draft; confirming adds the accepted food to the meal record. Rejected
 * food is recorded only — no credit or return (client question Q6).
 */
export default function DeliveryModal({
  order,
  delivery,
  today,
  onClose,
  onSaved,
}: {
  order: OutsourcedOrderDetail;
  /** A DRAFT delivery to correct; omitted to record a new one. */
  delivery?: OutsourcedDelivery;
  /** The campus's today (from the options); the browser's otherwise. */
  today?: string;
  onClose: () => void;
  onSaved: (updated: OutsourcedOrderDetail) => void;
}) {
  const campusToday = today ?? todayISO();
  const existing = new Map((delivery?.lines ?? []).map((line) => [line.order_line_id, line]));
  // What may still be accepted per line: remaining + what this draft holds.
  const remaining: Record<number, string> = {};
  for (const line of order.lines) {
    const held = existing.get(line.id);
    const left = (milli(line.remaining_quantity) ?? 0) + (held ? milli(held.accepted_quantity) ?? 0 : 0);
    remaining[line.id] = fromMilli(left);
  }
  const [date, setDate] = useState(delivery?.delivery_date ?? campusToday);
  const [remarks, setRemarks] = useState(delivery?.remarks ?? "");
  const [lines, setLines] = useState<DeliveryLineDraft[]>(() =>
    order.lines.map((line) => {
      const held = existing.get(line.id);
      return {
        orderLineId: line.id,
        include: delivery ? Boolean(held) : milli(remaining[line.id]) !== 0,
        received: held ? plainQuantity(held.received_quantity) : "",
        rejected: held ? plainQuantity(held.rejected_quantity) : "",
        reason: held?.rejection_reason ?? "",
        remarks: held?.remarks ?? "",
      };
    }),
  );
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const check = validateDelivery({ date, lines }, campusToday, order.order_date, remaining);
  const errors = showErrors ? check : null;
  const anyRejected = lines.some((line) => line.include && (milli(line.rejected) ?? 0) > 0);

  function setLine(id: number, patch: Partial<DeliveryLineDraft>) {
    setLines((current) => current.map((line) => (line.orderLineId === id ? { ...line, ...patch } : line)));
  }

  async function save() {
    setShowErrors(true);
    setError("");
    if (hasDeliveryErrors(check)) return;
    setSaving(true);
    try {
      const payload = deliveryPayload({ date, remarks, lines });
      const updated = delivery
        ? await api.put<OutsourcedOrderDetail>(outsourcedDeliveryEndpoint(delivery.id), payload)
        : await api.post<OutsourcedOrderDetail>(outsourcedOrderActionEndpoint(order.id, "deliveries"), payload);
      onSaved(updated);
    } catch (err: unknown) {
      setError(errorMessage(err, "The delivery could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      size="xl"
      dismissible={!saving}
      onClose={() => (saving ? undefined : onClose())}
      title={delivery ? `Correct draft ${delivery.delivery_number}` : `Record a delivery for ${order.order_number}`}
      description={`${order.supplier_name ?? "Supplier"} · ${order.meal_session_name} on ${formatDay(order.meal_date)}. Saved as a draft; confirm it to add the accepted food to the meal record. Outsourced food never enters stock.`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button loading={saving} onClick={save}>{delivery ? "Save draft" : "Save delivery as draft"}</Button>
        </>
      }
    >
      <div className="space-y-4" data-delivery-form>
        {error && <Alert tone="error" title="Not saved">{error}</Alert>}
        {errors?.lines && <Alert tone="error">{errors.lines}</Alert>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[12rem_minmax(0,1fr)]">
          <Field label="Delivery date" required error={errors?.date}>
            {({ id, describedBy }) => (
              <TextInput id={id} type="date" min={order.order_date} max={campusToday} aria-describedby={describedBy}
                aria-invalid={Boolean(errors?.date)} value={date} disabled={saving} onChange={(event) => setDate(event.target.value)} />
            )}
          </Field>
          <Field label="Remarks">
            {({ id }) => <TextInput id={id} maxLength={500} value={remarks} disabled={saving} onChange={(event) => setRemarks(event.target.value)} />}
          </Field>
        </div>
        <ul className="space-y-3">
          {order.lines.map((orderLine) => {
            const line = lines.find((row) => row.orderLineId === orderLine.id)!;
            const lineErrors = errors?.lineErrors[orderLine.id] ?? {};
            const accepted = line.include ? acceptedText(line.received, line.rejected || "0") : null;
            const unit = orderLine.unit_symbol ?? "";
            const nothingLeft = milli(remaining[orderLine.id]) === 0;
            return (
              <li key={orderLine.id} className="rounded-lg border border-slate-200 p-4" data-delivery-line={orderLine.id}>
                <label className="flex items-start gap-3">
                  <input type="checkbox" className="mt-1 h-4 w-4 rounded border-slate-300" checked={line.include}
                    disabled={saving || (nothingLeft && !line.include)}
                    onChange={(event) => setLine(orderLine.id, { include: event.target.checked })} />
                  <span className="min-w-0">
                    <span className="block font-medium text-slate-900">{orderLine.item_name}</span>
                    <span className="block text-xs text-slate-500">
                      Ordered {plainQuantity(orderLine.ordered_quantity)} {unit} · may still accept {plainQuantity(remaining[orderLine.id])} {unit}
                    </span>
                  </span>
                </label>
                {line.include && (
                  <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[repeat(3,minmax(0,1fr))_minmax(0,2fr)]">
                    <Field label={`Received (${unit})`} required error={lineErrors.received}>
                      {({ id, describedBy }) => (
                        <TextInput id={id} inputMode="decimal" autoComplete="off" className="tabular-nums" aria-describedby={describedBy}
                          aria-invalid={Boolean(lineErrors.received)} value={line.received} disabled={saving}
                          onChange={(event) => setLine(orderLine.id, { received: event.target.value })} />
                      )}
                    </Field>
                    <Field label={`Rejected (${unit})`} error={lineErrors.rejected}>
                      {({ id, describedBy }) => (
                        <TextInput id={id} inputMode="decimal" autoComplete="off" className="tabular-nums" placeholder="0"
                          aria-describedby={describedBy} aria-invalid={Boolean(lineErrors.rejected)} value={line.rejected} disabled={saving}
                          onChange={(event) => setLine(orderLine.id, { rejected: event.target.value })} />
                      )}
                    </Field>
                    <div>
                      <span className="mb-1.5 block text-sm font-medium text-slate-700">Accepted</span>
                      <p className="flex h-10 items-center text-sm font-semibold tabular-nums text-emerald-700" data-accepted>
                        {accepted === null ? "—" : `${accepted} ${unit}`}
                      </p>
                    </div>
                    <Field label="Reason for rejecting" required={(milli(line.rejected) ?? 0) > 0} error={lineErrors.reason}>
                      {({ id, describedBy }) => (
                        <TextInput id={id} maxLength={500} aria-describedby={describedBy} aria-invalid={Boolean(lineErrors.reason)}
                          placeholder={(milli(line.rejected) ?? 0) > 0 ? "e.g. Cold, short-weighted" : "Only when something is rejected"}
                          value={line.reason} disabled={saving} onChange={(event) => setLine(orderLine.id, { reason: event.target.value })} />
                      )}
                    </Field>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        {anyRejected && <Alert tone="warning" title="Rejected food">{Q6_NOTE} The rejected quantity and reason are recorded only.</Alert>}
      </div>
    </Modal>
  );
}
