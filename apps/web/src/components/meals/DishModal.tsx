"use client";

import { useState } from "react";

import { api } from "@/lib/api/client";
import { mealActionEndpoint, mealDishEndpoint } from "@/lib/api/endpoints";
import { checkDish } from "@/lib/mealMath";
import type { MealDish, MealOptions, MealRecord } from "@/lib/meals";
import { errorMessage } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";

/**
 * Adds a prepared dish (name, optional menu of the record's session, output
 * quantity and unit) or edits one. Carried-in retained food keeps its name,
 * quantity and unit; only its remarks can change. So does received
 * outsourced food (Stage 8a).
 */
export default function DishModal({
  record,
  dish,
  options,
  onClose,
  onSaved,
}: {
  record: MealRecord;
  dish?: MealDish;
  options: MealOptions;
  onClose: () => void;
  onSaved: (updated: MealRecord) => void;
}) {
  // Carried-in retained food and received outsourced food (Stage 8a) keep
  // their name, quantity and unit; only their remarks change.
  const carried = Boolean(dish?.carried_in || dish?.received_from);
  const received = Boolean(dish?.received_from);
  const [name, setName] = useState(dish?.dish_name ?? "");
  const [menuId, setMenuId] = useState(dish?.menu_id ? String(dish.menu_id) : "");
  const [output, setOutput] = useState(dish ? plainQuantity(dish.output_quantity) : "");
  const [unitId, setUnitId] = useState(dish ? String(dish.unit_id) : "");
  const [remarks, setRemarks] = useState(dish?.remarks ?? "");
  const [showErrors, setShowErrors] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const menus = options.menus.filter((menu) => menu.meal_session_id === record.meal_session_id);
  const errors = carried ? {} : checkDish({ name, output, unitId });
  const locked = Boolean(dish && dish.distributed_quantity !== null);

  async function save() {
    setShowErrors(true);
    setError("");
    if (Object.keys(errors).length) return;
    setBusy(true);
    try {
      const updated = carried && dish
        ? await api.put<MealRecord>(mealDishEndpoint(record.id, dish.id, "remarks"), { remarks: remarks.trim() || null })
        : dish
          ? await api.put<MealRecord>(mealDishEndpoint(record.id, dish.id), {
              dish_name: name.trim(), menu_id: menuId ? Number(menuId) : null, output_quantity: output.trim(),
              unit_id: Number(unitId), remarks: remarks.trim() || null })
          : await api.post<MealRecord>(mealActionEndpoint(record.id, "dishes"), {
              dish_name: name.trim(), menu_id: menuId ? Number(menuId) : null, output_quantity: output.trim(),
              unit_id: Number(unitId), remarks: remarks.trim() || null });
      onSaved(updated);
    } catch (err: unknown) {
      setError(errorMessage(err, "The dish was not saved."));
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
      title={dish ? `Edit ${dish.dish_name}` : "Add a prepared dish"}
      description={received
        ? "Received outsourced food keeps the name, quantity and unit of its confirmed delivery. Only its remarks can change."
        : carried
        ? "Carried-in retained food keeps its name, quantity and unit. Only its remarks can change."
        : "The output is the quantity prepared, in a unit suitable for the dish. Prepared food never changes ingredient stock."}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button loading={busy} onClick={save}>{dish ? "Save changes" : "Add dish"}</Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        {!carried && (
          <>
            <Field label="Dish" required error={showErrors ? errors.name : undefined}>
              {({ id, describedBy }) => (
                <TextInput id={id} maxLength={200} data-autofocus aria-describedby={describedBy} value={name}
                  placeholder="e.g. Veg biryani" onChange={(event) => setName(event.target.value)} />
              )}
            </Field>
            <Field label="Menu" hint={menus.length ? undefined : "No active menu for this session"}>
              {({ id }) => (
                <SelectInput id={id} value={menuId} onChange={(event) => setMenuId(event.target.value)}>
                  <option value="">No menu</option>
                  {menus.map((menu) => <option key={menu.id} value={menu.id}>{menu.name}</option>)}
                </SelectInput>
              )}
            </Field>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Output" required error={showErrors ? errors.output : undefined}
                hint={locked ? "Clear the distribution to change the output or unit" : undefined}>
                {({ id, describedBy }) => (
                  <TextInput id={id} inputMode="decimal" placeholder="0.000" aria-describedby={describedBy} value={output}
                    disabled={locked} onChange={(event) => setOutput(event.target.value)} />
                )}
              </Field>
              <Field label="Unit" required error={showErrors ? errors.unit : undefined}>
                {({ id, describedBy }) => (
                  <SelectInput id={id} aria-describedby={describedBy} value={unitId} disabled={locked}
                    onChange={(event) => setUnitId(event.target.value)}>
                    <option value="">Choose…</option>
                    {options.units.map((unit) => <option key={unit.id} value={unit.id}>{unit.symbol} ({unit.name})</option>)}
                  </SelectInput>
                )}
              </Field>
            </div>
          </>
        )}
        <Field label="Remarks">
          {({ id }) => <TextInput id={id} maxLength={500} value={remarks} onChange={(event) => setRemarks(event.target.value)} />}
        </Field>
      </div>
    </Modal>
  );
}
