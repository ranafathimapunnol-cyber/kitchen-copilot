"use client";

import { headcountError, lineFigures, overrideErrors } from "@/lib/planMath";
import { KIND_LABELS, type PrefillItem } from "@/lib/planning";
import { plainQuantity } from "@/lib/stockMath";
import Badge from "@/components/ui/Badge";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

export type LineDraft = { selected: boolean; override: boolean; quantity: string; unitId: string; reason: string };

export const emptyLine = (): LineDraft => ({ selected: false, override: false, quantity: "", unitId: "", reason: "" });

/** Problems that block saving (PLAN01: at least one main item; PLAN06: overrides complete). */
export function linesProblems(items: PrefillItem[], drafts: Record<number, LineDraft>, headcount: string): string[] {
  const problems: string[] = [];
  if (headcountError(headcount)) problems.push(headcountError(headcount) as string);
  const chosen = items.filter((item) => drafts[item.item_id]?.selected);
  if (!chosen.length) problems.push("Choose at least one main item.");
  for (const item of chosen) {
    const draft = drafts[item.item_id];
    if (draft.override && Object.keys(overrideErrors(draft)).length) {
      problems.push(`${item.item_name}: a one-day override needs a quantity per person, a unit and a reason.`);
    }
  }
  return problems;
}

export function linesPayload(items: PrefillItem[], drafts: Record<number, LineDraft>) {
  return items
    .filter((item) => drafts[item.item_id]?.selected)
    .map((item) => {
      const draft = drafts[item.item_id];
      return draft.override
        ? { item_id: item.item_id, override_quantity_per_person: draft.quantity.trim(),
            override_unit_id: Number(draft.unitId), override_reason: draft.reason.trim() }
        : { item_id: item.item_id };
    });
}

/**
 * The main items of a menu with an approved standard in effect on the plan
 * date (PLAN01: choose only the ones needed). Figures recalculate as the
 * headcount, the selection or an override changes (PLAN04); the API
 * recalculates them again when the plan is saved.
 */
export default function PlanLinesEditor({
  items,
  drafts,
  headcount,
  showErrors,
  onChange,
}: {
  items: PrefillItem[];
  drafts: Record<number, LineDraft>;
  headcount: string;
  showErrors: boolean;
  onChange: (itemId: number, draft: LineDraft) => void;
}) {
  const people = headcountError(headcount) ? 0 : Number(headcount);

  return (
    <Table minWidth="1040px">
      <THead>
        <tr>
          <TH className="w-10"><span className="sr-only">Use</span></TH>
          <TH>Main item</TH>
          <TH>Per person</TH>
          <TH align="right">Required</TH>
          <TH align="right">In stock unit</TH>
          <TH align="right">Current stock</TH>
          <TH align="right">To buy</TH>
        </tr>
      </THead>
      <TBody>
        {items.map((item) => {
          const draft = drafts[item.item_id] ?? { selected: false, override: false, quantity: "", unitId: "", reason: "" };
          const choice = item.unit_choices.find((u) => String(u.id) === draft.unitId);
          const overriding = draft.override;
          const figures = draft.selected && people
            ? lineFigures({
                headcount: people,
                perPerson: overriding ? draft.quantity : item.standard.quantity_per_person,
                unitDimension: overriding ? choice?.dimension ?? "" : item.standard.unit_dimension,
                factorToBase: overriding ? choice?.factor_to_base ?? null : item.standard.factor_to_base,
                baseDimension: item.base_unit_dimension,
                available: item.available_stock,
                display: !overriding || choice?.id === item.standard.unit_id ? item.display : null,
              })
            : null;
          const unit = overriding ? choice?.symbol ?? "" : item.standard.unit_symbol;
          const errors = showErrors && overriding ? overrideErrors(draft) : {};
          const set = (patch: Partial<LineDraft>) => onChange(item.item_id, { ...draft, ...patch });
          return (
            <TR key={item.item_id} muted={!draft.selected}>
              <TD>
                <input type="checkbox" className="h-4 w-4 accent-brand-600" aria-label={`Use ${item.item_name}`}
                  checked={draft.selected} onChange={(event) => set({ selected: event.target.checked })} />
              </TD>
              <TD>
                <span className="font-medium text-slate-900">{item.item_name}</span>
                <div className="text-xs text-slate-500">{KIND_LABELS[item.item_kind]} · stock in {item.base_unit_symbol}</div>
              </TD>
              <TD className="min-w-64">
                <div className={overriding ? "text-slate-400 line-through" : undefined}>
                  {plainQuantity(item.standard.quantity_per_person)} {item.standard.unit_symbol}
                  <span className="text-xs text-slate-500"> · standard v{item.standard.version_no}</span>
                </div>
                {draft.selected && (
                  <label className="mt-1 flex items-center gap-2 text-xs text-slate-600">
                    <input type="checkbox" className="h-3.5 w-3.5 accent-amber-600" checked={overriding}
                      onChange={(event) => set({ override: event.target.checked,
                        unitId: draft.unitId || String(item.standard.unit_id) })} />
                    One-day override (this plan only)
                  </label>
                )}
                {draft.selected && overriding && (
                  <div className="mt-2 grid grid-cols-[minmax(0,6rem)_minmax(0,5rem)] gap-2">
                    <Field label="Per person" error={errors.quantity}>
                      {({ id, describedBy }) => (
                        <TextInput id={id} inputMode="decimal" className="h-9" aria-describedby={describedBy}
                          value={draft.quantity} onChange={(event) => set({ quantity: event.target.value })} />
                      )}
                    </Field>
                    <Field label="Unit" error={errors.unit}>
                      {({ id, describedBy }) => (
                        <SelectInput id={id} className="h-9" aria-describedby={describedBy} value={draft.unitId}
                          onChange={(event) => set({ unitId: event.target.value })}>
                          <option value="">…</option>
                          {item.unit_choices.map((u) => <option key={u.id} value={u.id}>{u.symbol}</option>)}
                        </SelectInput>
                      )}
                    </Field>
                    <Field label="Reason" className="col-span-2" error={errors.reason}>
                      {({ id, describedBy }) => (
                        <TextInput id={id} className="h-9" maxLength={500} aria-describedby={describedBy}
                          placeholder="e.g. Exam week, larger portions" value={draft.reason}
                          onChange={(event) => set({ reason: event.target.value })} />
                      )}
                    </Field>
                  </div>
                )}
              </TD>
              <TD align="right" className="whitespace-nowrap">
                {figures ? (
                  <>
                    {figures.required} {unit}
                    {figures.display && <div className="text-xs text-slate-500">= {figures.display}</div>}
                    {figures.roundedUp && <div><Badge tone="brand">rounded up</Badge></div>}
                  </>
                ) : "—"}
              </TD>
              <TD align="right" className="whitespace-nowrap">{figures?.base ? `${figures.base} ${item.base_unit_symbol}` : "—"}</TD>
              <TD align="right" className="whitespace-nowrap">{plainQuantity(item.available_stock)} {item.base_unit_symbol}</TD>
              <TD align="right" className="whitespace-nowrap font-semibold">{figures?.gap ? `${figures.gap} ${item.base_unit_symbol}` : "—"}</TD>
            </TR>
          );
        })}
      </TBody>
    </Table>
  );
}
