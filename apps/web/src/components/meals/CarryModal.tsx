"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api/client";
import { MEAL_RETAINED_ENDPOINT, mealActionEndpoint } from "@/lib/api/endpoints";
import { sessionLabel, type MealRecord, type RetainedFood } from "@/lib/meals";
import { errorMessage } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import { TableSkeleton } from "@/components/ui/States";

/**
 * Carries retained food from a closed earlier meal into this one, whole, as
 * its own dish line with the same name and unit (interim rule while client
 * question Q11 is open). Each retained line can be carried once.
 */
export default function CarryModal({
  record,
  onClose,
  onSaved,
}: {
  record: MealRecord;
  onClose: () => void;
  onSaved: (updated: MealRecord) => void;
}) {
  const [items, setItems] = useState<RetainedFood[] | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api
      .get<{ items: RetainedFood[] }>(`${MEAL_RETAINED_ENDPOINT}?for_record=${record.id}`)
      .then((response) => {
        if (active) setItems(response.items);
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load retained food."));
      });
    return () => {
      active = false;
    };
  }, [record.id]);

  async function carry() {
    if (chosen === null) return;
    setBusy(true);
    setError("");
    try {
      onSaved(await api.post<MealRecord>(mealActionEndpoint(record.id, "carry"), { leftover_id: chosen }));
    } catch (err: unknown) {
      setError(errorMessage(err, "The retained food was not carried."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      size="md"
      onClose={() => (busy ? undefined : onClose())}
      dismissible={!busy}
      title="Carry retained food into this meal"
      description="Interim process until the client confirms how retained leftovers are handled (Q11): the whole retained quantity comes in as its own dish, same name and unit, and is then served or classified like any dish. It is never a purchase and never changes stock."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button loading={busy} disabled={chosen === null} onClick={carry}>Carry into this meal</Button>
        </>
      }
    >
      <div className="space-y-3">
        {error && <Alert tone="error">{error}</Alert>}
        {items === null && !error ? (
          <TableSkeleton rows={3} columns={2} />
        ) : items && items.length === 0 ? (
          <p className="text-sm text-slate-600">No retained food from closed meals on or before this date is waiting to be carried.</p>
        ) : (
          <ul className="space-y-2" aria-label="Retained food">
            {(items ?? []).map((item) => (
              <li key={item.leftover_id}>
                <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 p-3 hover:bg-slate-50">
                  <input type="radio" name="retained" className="mt-1" checked={chosen === item.leftover_id}
                    onChange={() => setChosen(item.leftover_id)} />
                  <span className="min-w-0">
                    <span className="block font-medium text-slate-900">{item.dish_name} · {plainQuantity(item.quantity)} {item.unit_symbol}</span>
                    <span className="block text-xs text-slate-500">From {sessionLabel(item.record)} · {item.remarks}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}
