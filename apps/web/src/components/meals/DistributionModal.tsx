"use client";

import { useState } from "react";

import { api } from "@/lib/api/client";
import { mealDishEndpoint } from "@/lib/api/endpoints";
import { checkDistribution, fromMilli, milli, type LeftoverDraft } from "@/lib/mealMath";
import { LEFTOVER_CLASSES, LEFTOVER_LABELS, sessionLabel, type MealDish, type MealRecord } from "@/lib/meals";
import { errorMessage } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";

/**
 * Distributed and remaining quantities of one dish and the classification
 * of what remains (MEAL03–MEAL05), all in the dish's unit. Available =
 * distributed + remaining exactly; leftovers are left blank until known, or
 * add up exactly to the remaining quantity, each with remarks. A retained
 * line already carried into a later meal cannot change here.
 */
export default function DistributionModal({
  record,
  dish,
  onClose,
  onSaved,
}: {
  record: MealRecord;
  dish: MealDish;
  onClose: () => void;
  onSaved: (updated: MealRecord) => void;
}) {
  const unit = dish.unit_symbol ?? "";
  const [distributed, setDistributed] = useState(dish.distributed_quantity !== null ? plainQuantity(dish.distributed_quantity) : "");
  const [remaining, setRemaining] = useState(dish.remaining_quantity !== null ? plainQuantity(dish.remaining_quantity) : "");
  const [lines, setLines] = useState<LeftoverDraft[]>(() =>
    LEFTOVER_CLASSES.map((classification) => {
      const row = dish.leftovers.find((l) => l.classification === classification);
      return { classification, quantity: row ? plainQuantity(row.quantity) : "", remarks: row?.remarks ?? "" };
    })
  );
  const [showErrors, setShowErrors] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const carried = dish.leftovers.find((l) => l.carried_to);
  const check = checkDistribution({ available: dish.available_quantity, distributed, remaining, leftovers: lines, unit });
  const remainingMilli = milli(remaining);

  function update(classification: string, patch: Partial<LeftoverDraft>) {
    setLines((current) => current.map((line) => (line.classification === classification ? { ...line, ...patch } : line)));
  }

  async function save() {
    setShowErrors(true);
    setError("");
    if (!check.valid) return;
    setBusy(true);
    try {
      onSaved(await api.put<MealRecord>(mealDishEndpoint(record.id, dish.id, "distribution"), {
        distributed_quantity: distributed.trim(),
        remaining_quantity: remaining.trim(),
        leftovers: lines.filter((l) => l.quantity.trim()).map((l) => ({
          classification: l.classification, quantity: l.quantity.trim(), remarks: l.remarks.trim() })),
      }));
    } catch (err: unknown) {
      setError(errorMessage(err, "The distribution was not saved."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      size="lg"
      onClose={() => (busy ? undefined : onClose())}
      dismissible={!busy}
      title={`Distribution of ${dish.dish_name}`}
      description={`Available ${plainQuantity(dish.available_quantity)} ${unit}. Food quantities only: people served are recorded in the headcount.`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button loading={busy} onClick={save}>Save distribution</Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        {carried && (
          <Alert tone="info">
            {plainQuantity(carried.quantity)} {unit} retained is carried into {sessionLabel(carried.carried_to?.record)} and cannot
            change here. Remove it there first while that record is open.
          </Alert>
        )}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={`Distributed (${unit})`} required error={showErrors ? check.distributed : undefined}>
            {({ id, describedBy }) => (
              <TextInput id={id} inputMode="decimal" data-autofocus aria-describedby={describedBy} value={distributed}
                onChange={(event) => setDistributed(event.target.value)} />
            )}
          </Field>
          <Field label={`Remaining (${unit})`} required error={showErrors ? check.remaining : undefined}>
            {({ id, describedBy }) => (
              <TextInput id={id} inputMode="decimal" aria-describedby={describedBy} value={remaining}
                onChange={(event) => setRemaining(event.target.value)} />
            )}
          </Field>
        </div>
        {check.balance && <Alert tone={showErrors ? "error" : "warning"}>{check.balance}</Alert>}
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium text-slate-700">
            Leftovers{remainingMilli ? ` — classify the ${fromMilli(remainingMilli)} ${unit} remaining` : ""}
          </legend>
          <p className="text-xs text-slate-500">Leave blank until known. When entered they must add up to the remaining quantity, each with remarks.</p>
          {lines.map((line) => {
            const lockedLine = carried?.classification === line.classification;
            return (
              <div key={line.classification} data-class={line.classification}
                className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 p-3 sm:grid-cols-[minmax(0,10rem)_minmax(0,8rem)_minmax(0,1fr)] sm:items-start">
                <p className="text-sm font-medium text-slate-900 sm:pt-7">{LEFTOVER_LABELS[line.classification as keyof typeof LEFTOVER_LABELS]}</p>
                <Field label={`Quantity (${unit})`} error={showErrors ? check.leftovers[line.classification] : undefined}>
                  {({ id, describedBy }) => (
                    <TextInput id={id} inputMode="decimal" aria-describedby={describedBy} value={line.quantity} disabled={lockedLine}
                      onChange={(event) => update(line.classification, { quantity: event.target.value })} />
                  )}
                </Field>
                <Field label="Remarks">
                  {({ id }) => (
                    <TextInput id={id} maxLength={500} value={line.remarks}
                      onChange={(event) => update(line.classification, { remarks: event.target.value })} />
                  )}
                </Field>
              </div>
            );
          })}
          {check.leftoverTotal && <Alert tone={showErrors ? "error" : "warning"}>{check.leftoverTotal}</Alert>}
        </fieldset>
      </div>
    </Modal>
  );
}
