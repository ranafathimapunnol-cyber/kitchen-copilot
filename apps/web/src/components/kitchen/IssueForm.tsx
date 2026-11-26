"use client";

import { useEffect, useRef, useState } from "react";
import { Plus, Save, Trash2 } from "lucide-react";

import { api } from "@/lib/api/client";
import { KITCHEN_ISSUES_ENDPOINT, KITCHEN_ISSUE_OPTIONS_ENDPOINT, kitchenIssueEndpoint } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/payments";
import type { FormOptions, IssuePayload, KitchenIssue } from "@/lib/kitchen";
import { checkIssue, type IssueLineDraft } from "@/lib/kitchenMath";
import { plainQuantity } from "@/lib/stockMath";
import { allowedUnits } from "@/lib/units";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import SearchSelect from "@/components/ui/SearchSelect";
import IconButton from "@/components/ui/IconButton";
import { TableSkeleton } from "@/components/ui/States";

function blank(key: number): IssueLineDraft {
  return { key: String(key), itemId: "", quantity: "", unitId: "", remarks: "" };
}

/**
 * Records a draft kitchen issue, or corrects one. A draft changes no stock
 * and may be saved even when stock is short; confirming it is a separate
 * step on the issue page, where the stock check happens.
 */
export default function IssueForm({
  initial,
  onSaved,
  onCancel,
}: {
  initial?: KitchenIssue;
  onSaved: (issue: KitchenIssue) => void;
  onCancel: () => void;
}) {
  const [options, setOptions] = useState<FormOptions | null>(null);
  const [loadError, setLoadError] = useState("");
  const [date, setDate] = useState(initial?.issue_date ?? "");
  const [sessionId, setSessionId] = useState(initial ? String(initial.meal_session_id) : "");
  const [menuId, setMenuId] = useState(initial ? String(initial.menu_id) : "");
  const [remarks, setRemarks] = useState(initial?.remarks ?? "");
  const nextKey = useRef(initial ? initial.lines.length : 1);
  const [lines, setLines] = useState<IssueLineDraft[]>(() =>
    initial
      ? initial.lines.map((line, index) => ({
          key: String(index),
          itemId: String(line.item_id),
          quantity: plainQuantity(line.quantity),
          unitId: String(line.unit_id),
          remarks: line.remarks ?? "",
        }))
      : [blank(0)]
  );
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    let active = true;
    api
      .get<FormOptions>(KITCHEN_ISSUE_OPTIONS_ENDPOINT)
      .then((response) => {
        if (!active) return;
        setOptions(response);
        setDate((current) => current || response.today);
      })
      .catch((err: unknown) => {
        if (active) setLoadError(errorMessage(err, "Unable to load meal sessions, menus and items."));
      });
    return () => {
      active = false;
    };
  }, []);

  if (loadError) {
    return (
      <Alert tone="error" title="Couldn't load the form">
        {loadError}
      </Alert>
    );
  }
  if (!options) {
    return (
      <Card>
        <TableSkeleton rows={4} columns={4} />
      </Card>
    );
  }

  const menus = options.menus.filter((menu) => String(menu.meal_session_id) === sessionId);
  const chosenMenu = options.menus.find((menu) => String(menu.id) === menuId);
  const check = checkIssue(
    { date, sessionId, menuId, menuSessionId: chosenMenu ? String(chosenMenu.meal_session_id) : null, lines },
    options.today
  );
  const used = lines.filter((line) => line.itemId || line.quantity.trim());
  const unitSymbol = (id: number) => options.units.find((unit) => unit.id === id)?.symbol ?? "";

  function update(key: string, patch: Partial<IssueLineDraft>) {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  }

  async function save() {
    setShowErrors(true);
    setSubmitError("");
    if (!check.valid) return;
    const payload: IssuePayload = {
      issue_date: date,
      meal_session_id: Number(sessionId),
      menu_id: Number(menuId),
      remarks: remarks.trim() || null,
      lines: used.map((line) => ({
        item_id: Number(line.itemId),
        quantity: line.quantity.trim(),
        unit_id: Number(line.unitId),
        remarks: line.remarks.trim() || null,
      })),
    };
    setSaving(true);
    try {
      const saved = initial
        ? await api.put<KitchenIssue>(kitchenIssueEndpoint(initial.id), payload)
        : await api.post<KitchenIssue>(KITCHEN_ISSUES_ENDPOINT, payload);
      onSaved(saved);
    } catch (err: unknown) {
      setSubmitError(errorMessage(err, "Unable to save the issue."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="space-y-5 p-5">
      {submitError && (
        <Alert tone="error" title="The issue was not saved" onDismiss={() => setSubmitError("")}>
          {submitError}
        </Alert>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Issue date" required error={showErrors ? check.fields.date : undefined} hint="Today or earlier">
          {({ id, describedBy }) => (
            <TextInput id={id} type="date" max={options.today} aria-describedby={describedBy} value={date}
              onChange={(event) => setDate(event.target.value)} />
          )}
        </Field>
        <Field label="Meal session" required error={showErrors ? check.fields.session : undefined}>
          {({ id, describedBy }) => (
            <SelectInput id={id} aria-describedby={describedBy} value={sessionId}
              onChange={(event) => {
                setSessionId(event.target.value);
                setMenuId("");
              }}>
              <option value="">Choose a session…</option>
              {options.meal_sessions.map((session) => (
                <option key={session.id} value={session.id}>{session.name}</option>
              ))}
            </SelectInput>
          )}
        </Field>
        <Field label="Menu" required error={showErrors ? check.fields.menu : undefined}
          hint={sessionId && menus.length === 0 ? "No active menu for this session" : undefined}>
          {({ id, describedBy }) => (
            <SelectInput id={id} aria-describedby={describedBy} value={menuId} disabled={!sessionId}
              onChange={(event) => setMenuId(event.target.value)}>
              <option value="">{sessionId ? "Choose a menu…" : "Choose a session first"}</option>
              {menus.map((menu) => (
                <option key={menu.id} value={menu.id}>{menu.name}</option>
              ))}
            </SelectInput>
          )}
        </Field>
        <Field label="Remarks">
          {({ id }) => (
            <TextInput id={id} maxLength={500} value={remarks} onChange={(event) => setRemarks(event.target.value)} />
          )}
        </Field>
      </div>

      <div className="space-y-3">
        <p className="text-sm font-medium text-slate-700">Items issued</p>
        {showErrors && check.fields.lines && <Alert tone="error">{check.fields.lines}</Alert>}
        <ul className="space-y-3">
          {lines.map((line, index) => {
            const errors = showErrors ? check.lines[line.key] : undefined;
            const units = line.itemId ? allowedUnits(options, line.itemId) : [];
            const item = options.items.find((entry) => String(entry.id) === line.itemId);
            const onHand = item && options.balances ? options.balances[String(item.id)] ?? "0.000" : null;
            return (
              <li key={line.key}
                className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 p-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.4fr)_auto] sm:items-start">
                <Field label={`Item ${index + 1}`} error={errors?.item}
                  hint={onHand !== null && item ? `In stock: ${plainQuantity(onHand)} ${unitSymbol(item.standard_unit_id)}` : undefined}>
                  {({ id, describedBy }) => (
                    <SearchSelect id={id} aria-describedby={describedBy} aria-invalid={Boolean(errors?.item)} value={line.itemId}
                      noun="items" placeholder="Choose an item…"
                      options={options.items.map((entry) => ({ value: String(entry.id), label: entry.name }))}
                      onChange={(value) => {
                        const chosen = options.items.find((entry) => String(entry.id) === value);
                        update(line.key, { itemId: value, unitId: chosen ? String(chosen.standard_unit_id) : "" });
                      }} />
                  )}
                </Field>
                <Field label="Quantity" error={errors?.quantity}>
                  {({ id, describedBy }) => (
                    <TextInput id={id} inputMode="decimal" placeholder="0.000" aria-describedby={describedBy}
                      aria-invalid={Boolean(errors?.quantity)} value={line.quantity}
                      onChange={(event) => update(line.key, { quantity: event.target.value })} />
                  )}
                </Field>
                <Field label="Unit" error={errors?.unit}>
                  {({ id, describedBy }) => (
                    <SelectInput id={id} aria-describedby={describedBy} value={line.unitId} disabled={!line.itemId}
                      onChange={(event) => update(line.key, { unitId: event.target.value })}>
                      {!line.itemId && <option value="">—</option>}
                      {units.map((unit) => (
                        <option key={unit.id} value={unit.id}>{unit.symbol}</option>
                      ))}
                    </SelectInput>
                  )}
                </Field>
                <Field label="Line remarks">
                  {({ id }) => (
                    <TextInput id={id} maxLength={500} value={line.remarks}
                      onChange={(event) => update(line.key, { remarks: event.target.value })} />
                  )}
                </Field>
                <div className="flex sm:pt-7">
                  <IconButton label={`Remove item ${index + 1}`} tone="danger" icon={<Trash2 size={16} />}
                    onClick={() =>
                      setLines((current) =>
                        current.length === 1 ? [blank(nextKey.current++)] : current.filter((entry) => entry.key !== line.key)
                      )
                    } />
                </div>
              </li>
            );
          })}
        </ul>
        <Button variant="secondary" size="sm" icon={<Plus size={14} aria-hidden />}
          onClick={() => setLines((current) => [...current, blank(nextKey.current++)])}>
          Add another item
        </Button>
      </div>

      <p className="text-xs text-slate-500">
        A draft changes no stock and can be saved even when stock is short. Stock is checked when the issue is
        confirmed. An issue dated today takes effect when it is confirmed; an earlier date takes effect at the end of
        that day.
      </p>
      <div className="flex flex-col-reverse gap-2 border-t border-slate-100 pt-4 sm:flex-row sm:justify-end">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>Cancel</Button>
        <Button icon={<Save size={16} aria-hidden />} loading={saving} onClick={save}>
          {initial ? "Save changes" : "Save draft"}
        </Button>
      </div>
    </Card>
  );
}
