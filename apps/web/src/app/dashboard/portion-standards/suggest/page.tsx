"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Calculator, History, Save } from "lucide-react";

import { api } from "@/lib/api/client";
import {
  PORTION_STANDARD_OPTIONS_ENDPOINT,
  PORTION_STANDARD_SUGGESTION_ENDPOINT,
  PORTION_STANDARD_SUGGESTION_PREVIEW_ENDPOINT,
  PORTION_STANDARD_SUGGESTION_RECORDS_ENDPOINT,
} from "@/lib/api/endpoints";
import { errorMessage, formatDay } from "@/lib/payments";
import type { StandardDetail, StandardOptions, Suggestion, SuggestionRecord } from "@/lib/planning";
import { plainQuantity } from "@/lib/stockMath";
import Alert from "@/components/ui/Alert";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import SearchSelect from "@/components/ui/SearchSelect";
import PageHeader from "@/components/ui/PageHeader";
import { TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

/**
 * PLAN03: suggested quantity per person = total net usage ÷ total people
 * served, over the closed meal records the user selects. The result is saved
 * as a DRAFT standard with its basis; it applies only after approval.
 */
export default function SuggestStandardPage() {
  const router = useRouter();
  const toast = useToast();
  const [options, setOptions] = useState<StandardOptions | null>(null);
  const [menuId, setMenuId] = useState("");
  const [itemId, setItemId] = useState("");
  const [sameSession, setSameSession] = useState(true);
  const [records, setRecords] = useState<SuggestionRecord[] | null>(null);
  const [sessionNotes, setSessionNotes] = useState<string[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [unitId, setUnitId] = useState("");
  const [preview, setPreview] = useState<Suggestion | null>(null);
  const [effective, setEffective] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<StandardOptions>(PORTION_STANDARD_OPTIONS_ENDPOINT)
      .then((response) => { setOptions(response); setEffective(response.today); })
      .catch((err: unknown) => setError(errorMessage(err, "Unable to load the form.")));
  }, []);

  const menu = options?.menus.find((m) => String(m.id) === menuId);
  const item = options?.items.find((i) => String(i.id) === itemId);
  const query = itemId && (!sameSession || menu) ? `${itemId}|${sameSession && menu ? menu.meal_session_id : ""}` : "";

  useEffect(() => {
    if (!query) return;
    let active = true;
    const [item_id, session] = query.split("|");
    const params = new URLSearchParams({ item_id });
    if (session) params.set("meal_session_id", session);
    api.get<{ items: SuggestionRecord[]; session_notes: string[] }>(`${PORTION_STANDARD_SUGGESTION_RECORDS_ENDPOINT}?${params}`)
      .then((response) => {
        if (!active) return;
        setRecords(response.items);
        setSessionNotes(response.session_notes);
        setSelected(response.items.map((r) => r.id));
        setPreview(null);
      })
      .catch((err: unknown) => { if (active) setError(errorMessage(err, "Unable to load past meals.")); });
    return () => {
      active = false;
    };
  }, [query]);

  const body = () => ({ menu_id: Number(menuId), item_id: Number(itemId), meal_record_ids: selected, unit_id: unitId ? Number(unitId) : null });

  async function calculate() {
    setError("");
    if (!menuId || !itemId || !selected.length || !unitId) {
      setError("Choose the menu, the item, at least one meal and the unit.");
      return;
    }
    setBusy(true);
    try {
      setPreview(await api.post<Suggestion>(PORTION_STANDARD_SUGGESTION_PREVIEW_ENDPOINT, body()));
    } catch (err: unknown) {
      setError(errorMessage(err, "Unable to calculate the suggestion."));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setError("");
    setBusy(true);
    try {
      const saved = await api.post<StandardDetail>(PORTION_STANDARD_SUGGESTION_ENDPOINT, {
        ...body(), effective_from: effective, notes: notes.trim() || null });
      toast.success("Suggestion saved as a draft standard.");
      router.push(`/dashboard/portion-standards/${saved.id}`);
    } catch (err: unknown) {
      setError(errorMessage(err, "Unable to save the suggestion."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6 pb-6">
      <Link href="/dashboard/portion-standards" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
        <ArrowLeft size={15} aria-hidden />
        Portion Standards
      </Link>
      <PageHeader eyebrow="Menu Planning" icon={History} title="Suggest a standard from past meals"
        description="Average per person = total quantity used ÷ total people served, over closed meal records you choose. Usage is the net kitchen issues of each meal at its closing. The result is saved as a draft for review and approval." />
      {error && <Alert tone="error" onDismiss={() => setError("")}>{error}</Alert>}
      {!options ? (
        <Card><TableSkeleton rows={3} columns={3} /></Card>
      ) : (
        <>
          <Card className="space-y-4 p-5">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Field label="Menu" required>
                {({ id }) => (
                  <SelectInput id={id} value={menuId} onChange={(event) => setMenuId(event.target.value)}>
                    <option value="">Choose a menu…</option>
                    {options.menus.map((m) => <option key={m.id} value={m.id}>{m.name} ({m.meal_session_name})</option>)}
                  </SelectInput>
                )}
              </Field>
              <Field label="Item" required>
                {({ id }) => (
                  <SearchSelect id={id} value={itemId} noun="items" placeholder="Choose an item…"
                    options={options.items.filter((i) => i.item_kind !== "OUTSOURCED").map((i) => ({ value: String(i.id), label: i.name }))}
                    onChange={(value) => { setItemId(value); setUnitId(""); }} />
                )}
              </Field>
              <Field label="Suggest in" required>
                {({ id }) => (
                  <SelectInput id={id} value={unitId} disabled={!item} onChange={(event) => { setUnitId(event.target.value); setPreview(null); }}>
                    <option value="">Choose a unit…</option>
                    {(item?.unit_choices ?? []).map((u) => <option key={u.id} value={u.id}>{u.symbol}</option>)}
                  </SelectInput>
                )}
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={sameSession} onChange={(event) => setSameSession(event.target.checked)} />
              Only meals of the menu&apos;s meal session{menu ? ` (${menu.meal_session_name})` : ""}
            </label>
            {sessionNotes.map((note) => <Alert key={note} tone="warning">{note}</Alert>)}
          </Card>

          {query && (
            <Card>
              <CardHeader title="Closed meals that used this item" subtitle="Tick the meals that represent normal portions." />
              {!records ? <TableSkeleton rows={3} columns={4} /> : records.length === 0 ? (
                <p className="px-5 pb-5 text-sm text-slate-600">No closed meal record used this item.</p>
              ) : (
                <Table minWidth="560px">
                  <THead><tr><TH className="w-10"><span className="sr-only">Use</span></TH><TH>Meal</TH><TH align="right">Net usage</TH><TH align="right">People served</TH></tr></THead>
                  <TBody>
                    {records.map((r) => (
                      <TR key={r.id} muted={!selected.includes(r.id)}>
                        <TD>
                          <input type="checkbox" className="h-4 w-4 accent-brand-600" aria-label={`Use ${r.meal_session_name} ${r.meal_date}`}
                            checked={selected.includes(r.id)}
                            onChange={(event) => { setPreview(null); setSelected((all) => event.target.checked ? [...all, r.id] : all.filter((x) => x !== r.id)); }} />
                        </TD>
                        <TD><Link href={`/dashboard/meals/${r.id}`} className="text-brand-700 hover:underline">{r.meal_session_name} · {formatDay(r.meal_date)}</Link></TD>
                        <TD align="right">{plainQuantity(r.net_quantity)} {r.unit_symbol}</TD>
                        <TD align="right">{r.actual_total ?? "—"}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              )}
              <div className="flex justify-end px-5 py-4">
                <Button icon={<Calculator size={15} aria-hidden />} loading={busy && !preview} disabled={!records?.length} onClick={calculate}>Calculate</Button>
              </div>
            </Card>
          )}

          {preview && (
            <Card className="space-y-4 p-5">
              <CardHeader className="p-0" title="Suggestion"
                subtitle={`${plainQuantity(preview.total_quantity_used)} ${preview.base_unit_symbol} used ÷ ${preview.total_people_served} people served`} />
              {preview.included_count === 0 ? (
                <Alert tone="warning">None of the selected meals can be used.</Alert>
              ) : (
                <p className="text-2xl font-semibold text-slate-900">
                  {plainQuantity(preview.suggested_quantity_per_person)} {preview.unit_symbol} per person
                  <span className="ml-2 text-sm font-normal text-slate-500">({preview.per_person_in_base_unit} {preview.base_unit_symbol} unrounded)</span>
                </p>
              )}
              {preview.records.some((r) => !r.included) && (
                <ul className="space-y-1 text-sm">
                  {preview.records.filter((r) => !r.included).map((r) => (
                    <li key={r.meal_record_id}><Badge tone="neutral">left out</Badge> {r.meal_session_name} · {formatDay(r.meal_date)}: {r.excluded_reason}</li>
                  ))}
                </ul>
              )}
              {preview.included_count > 0 && (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_auto] sm:items-end">
                  <Field label="Effective from" required>
                    {({ id }) => <TextInput id={id} type="date" min={options.today} value={effective} onChange={(event) => setEffective(event.target.value)} />}
                  </Field>
                  <Field label="Notes">
                    {({ id }) => <TextInput id={id} maxLength={500} value={notes} onChange={(event) => setNotes(event.target.value)} />}
                  </Field>
                  <Button icon={<Save size={15} aria-hidden />} loading={busy} onClick={save}>Save as draft</Button>
                </div>
              )}
            </Card>
          )}
        </>
      )}
    </div>
  );
}
