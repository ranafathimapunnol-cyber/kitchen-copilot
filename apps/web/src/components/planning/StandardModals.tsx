"use client";

import { useState } from "react";

import { api } from "@/lib/api/client";
import { PORTION_STANDARDS_ENDPOINT, PORTION_STANDARD_COPY_ENDPOINT, portionStandardEndpoint } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/payments";
import { perPersonError } from "@/lib/planMath";
import { KIND_LABELS, type CopyResult, type StandardDetail, type StandardOptions } from "@/lib/planning";
import { plainQuantity } from "@/lib/stockMath";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import SearchSelect from "@/components/ui/SearchSelect";
import Modal from "@/components/ui/Modal";

/**
 * A new draft standard (menu, item, quantity per person, unit, effective
 * date) or a change to a draft. Only units with an explicit conversion to
 * the item's standard unit are offered (S6-3); the date is today or later.
 */
export function StandardModal({
  options,
  standard,
  onClose,
  onSaved,
}: {
  options: StandardOptions;
  standard?: StandardDetail;
  onClose: () => void;
  onSaved: (saved: StandardDetail) => void;
}) {
  const [menuId, setMenuId] = useState(standard ? String(standard.menu_id) : "");
  const [itemId, setItemId] = useState(standard ? String(standard.item_id) : "");
  const [quantity, setQuantity] = useState(standard ? plainQuantity(standard.quantity_per_person) : "");
  const [unitId, setUnitId] = useState(standard ? String(standard.unit_id) : "");
  const [effective, setEffective] = useState(standard?.effective_from ?? options.today);
  const [notes, setNotes] = useState(standard?.notes ?? "");
  const [showErrors, setShowErrors] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const item = options.items.find((i) => String(i.id) === itemId);
  const errors: Record<string, string> = {};
  if (!menuId) errors.menu = "Choose the menu.";
  if (!itemId) errors.item = "Choose the item.";
  const quantityError = perPersonError(quantity);
  if (quantityError) errors.quantity = quantityError;
  if (!unitId) errors.unit = "Choose a unit.";
  if (!effective || effective < options.today) errors.effective = "Today or later (standards are not back-dated).";

  async function save() {
    setShowErrors(true);
    setError("");
    if (Object.keys(errors).length) return;
    setBusy(true);
    try {
      const body = { quantity_per_person: quantity.trim(), unit_id: Number(unitId), effective_from: effective, notes: notes.trim() || null };
      const saved = standard
        ? await api.put<StandardDetail>(portionStandardEndpoint(standard.id), body)
        : await api.post<StandardDetail>(PORTION_STANDARDS_ENDPOINT, { ...body, menu_id: Number(menuId), item_id: Number(itemId) });
      onSaved(saved);
    } catch (err: unknown) {
      setError(errorMessage(err, "Unable to save the standard."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} dismissible={!busy} size="lg"
      title={standard ? "Edit draft standard" : "New draft standard"}
      description="A per-person quantity of one item for one menu. It is used only after an Admin or Kitchen Manager approves it."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={save} loading={busy}>{standard ? "Save draft" : "Create draft"}</Button>
        </>
      }>
      {error && <Alert tone="error" className="mb-4">{error}</Alert>}
      <div className="grid gap-x-4 gap-y-5 sm:grid-cols-2">
        <Field label="Menu" required error={showErrors ? errors.menu : undefined}>
          {({ id, describedBy }) => (
            <SelectInput id={id} aria-describedby={describedBy} value={menuId} disabled={Boolean(standard)}
              onChange={(event) => setMenuId(event.target.value)}>
              <option value="">Choose a menu…</option>
              {options.menus.map((m) => <option key={m.id} value={m.id}>{m.name} ({m.meal_session_name})</option>)}
            </SelectInput>
          )}
        </Field>
        <Field label="Item" required error={showErrors ? errors.item : undefined}
          hint={item ? (item.item_kind ? `${KIND_LABELS[item.item_kind]} · stock in ${item.base_unit_symbol}` : "Not classified yet: an Admin or Kitchen Manager classifies it before approval.") : undefined}>
          {({ id, describedBy }) => (
            <SearchSelect id={id} aria-describedby={describedBy} value={itemId} disabled={Boolean(standard)}
              aria-invalid={Boolean(showErrors && errors.item)} noun="items" placeholder="Choose an item…"
              options={options.items.filter((i) => i.item_kind !== "OUTSOURCED").map((i) => ({ value: String(i.id), label: i.name }))}
              onChange={(value) => { setItemId(value); setUnitId(""); }} />
          )}
        </Field>
        <Field label="Quantity per person" required error={showErrors ? errors.quantity : undefined}>
          {({ id, describedBy }) => (
            <TextInput id={id} inputMode="decimal" aria-describedby={describedBy} value={quantity} data-autofocus
              onChange={(event) => setQuantity(event.target.value)} />
          )}
        </Field>
        <Field label="Unit" required error={showErrors ? errors.unit : undefined}
          hint="Units with an approved conversion to the item's stock unit">
          {({ id, describedBy }) => (
            <SelectInput id={id} aria-describedby={describedBy} value={unitId} disabled={!item && !standard}
              onChange={(event) => setUnitId(event.target.value)}>
              <option value="">Choose a unit…</option>
              {(item?.unit_choices ?? []).map((u) => <option key={u.id} value={u.id}>{u.symbol}</option>)}
              {standard && !item && <option value={standard.unit_id}>{standard.unit_symbol}</option>}
            </SelectInput>
          )}
        </Field>
        <Field label="Effective from" required error={showErrors ? errors.effective : undefined}>
          {({ id, describedBy }) => (
            <TextInput id={id} type="date" min={options.today} aria-describedby={describedBy} value={effective}
              onChange={(event) => setEffective(event.target.value)} />
          )}
        </Field>
        <Field label="Notes">
          {({ id }) => <TextInput id={id} maxLength={500} value={notes} onChange={(event) => setNotes(event.target.value)} />}
        </Field>
      </div>
    </Modal>
  );
}

/** Copies a menu's main items into DRAFT standards (6-2, S6-4). Nothing is approved. */
export function CopyModal({ options, onClose, onCopied }: { options: StandardOptions; onClose: () => void; onCopied: () => void }) {
  const [menuId, setMenuId] = useState("");
  const [effective, setEffective] = useState(options.today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<CopyResult | null>(null);

  async function copy() {
    if (!menuId || !effective || effective < options.today) {
      setError("Choose a menu and an effective date of today or later.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setResult(await api.post<CopyResult>(PORTION_STANDARD_COPY_ENDPOINT, { menu_id: Number(menuId), effective_from: effective }));
      onCopied();
    } catch (err: unknown) {
      setError(errorMessage(err, "Unable to copy the menu main items."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} dismissible={!busy} size="lg" title="Copy menu main items into draft standards"
      description="Each main item of the menu becomes a draft standard with the same quantity and unit. Menu main items are not changed, and every draft needs approval before plans can use it."
      footer={result
        ? <Button onClick={onClose}>Done</Button>
        : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>Cancel</Button>
            <Button onClick={copy} loading={busy}>Copy as drafts</Button>
          </>
        )}>
      {error && <Alert tone="error" className="mb-4">{error}</Alert>}
      {result ? (
        <div className="space-y-3 text-sm">
          <Alert tone="success" title={`${result.created.length} draft${result.created.length === 1 ? "" : "s"} created from ${result.menu_name}`}>
            {result.note}
          </Alert>
          {result.created.length > 0 && (
            <ul className="list-disc pl-5">{result.created.map((c) => <li key={c.id}>{c.item_name}: {plainQuantity(c.quantity_per_person)} {c.unit_symbol}</li>)}</ul>
          )}
          {result.skipped.length > 0 && (
            <>
              <p className="font-medium text-slate-700">Not copied</p>
              <ul className="list-disc pl-5 text-slate-600">{result.skipped.map((s) => <li key={s.menu_main_item_id}>{s.item_name}: {s.reason}</li>)}</ul>
            </>
          )}
        </div>
      ) : (
        <div className="grid gap-x-4 gap-y-5 sm:grid-cols-2">
          <Field label="Menu" required>
            {({ id }) => (
              <SelectInput id={id} value={menuId} onChange={(event) => setMenuId(event.target.value)}>
                <option value="">Choose a menu…</option>
                {options.menus.map((m) => <option key={m.id} value={m.id}>{m.name} ({m.meal_session_name})</option>)}
              </SelectInput>
            )}
          </Field>
          <Field label="Effective from" required>
            {({ id }) => <TextInput id={id} type="date" min={options.today} value={effective} onChange={(event) => setEffective(event.target.value)} />}
          </Field>
        </div>
      )}
    </Modal>
  );
}
