"use client";

import { useState } from "react";
import { CornerUpLeft } from "lucide-react";

import { api } from "@/lib/api/client";
import { kitchenIssueActionEndpoint } from "@/lib/api/endpoints";
import { errorMessage, todayISO } from "@/lib/payments";
import type { KitchenIssue } from "@/lib/kitchen";
import { checkReturn } from "@/lib/kitchenMath";
import { plainQuantity } from "@/lib/stockMath";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";

type Row = { lineId: number; quantity: string; unitId: string };

/**
 * Records a draft return of unused stock against a confirmed issue. Each
 * line offers the item's standard unit and, if different, the unit it was
 * issued in. A line cannot give back more than was issued minus what other
 * returns already hold; the API checks again on confirmation.
 */
export default function ReturnModal({
  issue,
  onClose,
  onSaved,
}: {
  issue: KitchenIssue | null;
  onClose: () => void;
  onSaved: (issue: KitchenIssue) => void;
}) {
  const returnable = (issue?.lines ?? []).filter((line) => Number(line.returnable_quantity) > 0);
  const [date, setDate] = useState(todayISO());
  const [remarks, setRemarks] = useState("");
  const [rows, setRows] = useState<Row[]>(() =>
    returnable.map((line) => ({ lineId: line.id, quantity: "", unitId: String(line.standard_unit_id) }))
  );
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  if (!issue) return null;
  const today = todayISO();
  const factorOf = (lineId: number, unitId: string) => {
    const line = issue.lines.find((entry) => entry.id === lineId);
    if (!line || unitId === String(line.standard_unit_id)) return 1;
    return Number(line.conversion_factor);
  };
  const check = checkReturn(
    {
      date,
      issueDate: issue.issue_date,
      lines: rows.map((row) => ({
        key: String(row.lineId),
        quantity: row.quantity,
        factor: factorOf(row.lineId, row.unitId),
        returnable: issue.lines.find((line) => line.id === row.lineId)?.returnable_quantity ?? "0.000",
      })),
    },
    today
  );

  async function save() {
    setShowErrors(true);
    setError("");
    if (!check.valid || !issue) return;
    setSaving(true);
    try {
      const saved = await api.post<KitchenIssue>(kitchenIssueActionEndpoint(issue.id, "returns"), {
        return_date: date,
        remarks: remarks.trim() || null,
        lines: rows
          .filter((row) => row.quantity.trim())
          .map((row) => ({ issue_item_id: row.lineId, quantity: row.quantity.trim(), unit_id: Number(row.unitId) })),
      });
      onSaved(saved);
    } catch (err: unknown) {
      setError(errorMessage(err, "Unable to record the return."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      onClose={() => (saving ? undefined : onClose())}
      dismissible={!saving}
      size="lg"
      title={`Return unused stock from ${issue.issue_number}`}
      description="Saved as a draft; confirming it adds the stock back. A return dated today takes effect when confirmed; an earlier date takes effect at the end of that day, never before the issue."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button icon={<CornerUpLeft size={16} aria-hidden />} loading={saving} onClick={save}>Save draft return</Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert tone="error" title="The return was not saved">{error}</Alert>}
        {showErrors && check.form && <Alert tone="error">{check.form}</Alert>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Return date" required error={showErrors ? check.date : undefined}>
            {({ id, describedBy }) => (
              <TextInput id={id} type="date" min={issue.issue_date} max={today} aria-describedby={describedBy} value={date}
                onChange={(event) => setDate(event.target.value)} />
            )}
          </Field>
          <Field label="Remarks">
            {({ id }) => <TextInput id={id} maxLength={500} value={remarks} onChange={(event) => setRemarks(event.target.value)} />}
          </Field>
        </div>
        <ul className="space-y-3">
          {rows.map((row) => {
            const line = issue.lines.find((entry) => entry.id === row.lineId)!;
            const lineError = showErrors ? check.lines[String(row.lineId)] : undefined;
            return (
              <li key={row.lineId} className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 p-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)] sm:items-start">
                <div className="min-w-0 text-sm">
                  <p className="font-medium text-slate-900">{line.item_name}</p>
                  <p className="text-xs text-slate-500">
                    Issued {plainQuantity(line.standard_quantity)} {line.standard_unit_symbol} · can return{" "}
                    {plainQuantity(line.returnable_quantity)} {line.standard_unit_symbol}
                  </p>
                </div>
                <Field label={`Return ${line.item_name}`} error={lineError}>
                  {({ id, describedBy }) => (
                    <TextInput id={id} inputMode="decimal" placeholder="0.000" aria-describedby={describedBy}
                      aria-invalid={Boolean(lineError)} value={row.quantity}
                      onChange={(event) => setRows((current) => current.map((entry) =>
                        entry.lineId === row.lineId ? { ...entry, quantity: event.target.value } : entry))} />
                  )}
                </Field>
                <Field label="Unit">
                  {({ id }) => (
                    <SelectInput id={id} value={row.unitId}
                      onChange={(event) => setRows((current) => current.map((entry) =>
                        entry.lineId === row.lineId ? { ...entry, unitId: event.target.value } : entry))}>
                      <option value={line.standard_unit_id}>{line.standard_unit_symbol}</option>
                      {line.unit_id !== line.standard_unit_id && <option value={line.unit_id}>{line.unit_symbol}</option>}
                    </SelectInput>
                  )}
                </Field>
              </li>
            );
          })}
        </ul>
      </div>
    </Modal>
  );
}
