"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Ban, CalendarRange, CircleCheck, CornerDownRight, History, Pencil, Plus, RotateCcw, Save, Scale, Trash2, UtensilsCrossed } from "lucide-react";

import { api } from "@/lib/api/client";
import { MEAL_OPTIONS_ENDPOINT, mealActionEndpoint, mealDishEndpoint, mealRecordEndpoint } from "@/lib/api/endpoints";
import { checkCounts } from "@/lib/mealMath";
import {
  HISTORY_LABELS,
  LEFTOVER_LABELS,
  MEAL_STATUS_LABELS,
  MEAL_STATUS_TONES,
  canEditMeals,
  canReopenMeals,
  sessionLabel,
  type HistoryEntry,
  type MealDish,
  type MealOptions,
  type MealRecord,
} from "@/lib/meals";
import { errorMessage, formatDateTime, formatDay } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import ReasonModal from "@/components/kitchen/ReasonModal";
import CarryModal from "@/components/meals/CarryModal";
import DishModal from "@/components/meals/DishModal";
import DistributionModal from "@/components/meals/DistributionModal";
import PlanComparison from "@/components/planning/PlanComparison";
import Alert from "@/components/ui/Alert";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { Field, TextInput } from "@/components/ui/Field";
import IconButton from "@/components/ui/IconButton";
import PageHeader from "@/components/ui/PageHeader";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

type Dialog =
  | { kind: "dish"; dish?: MealDish }
  | { kind: "distribution"; dish: MealDish }
  | { kind: "remove"; dish: MealDish }
  | { kind: "carry" }
  | { kind: "close" }
  | { kind: "cancel" }
  | { kind: "reopen" }
  | null;

const GROUPS = ["students", "staff", "guests"] as const;
const text = (value: number | null) => (value === null ? "" : String(value));

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm break-words text-slate-900">{children}</dd>
    </div>
  );
}

export default function MealRecordPage() {
  const params = useParams<{ id: string }>();
  const { role, permissions } = useAuthorization();
  const toast = useToast();
  const [record, setRecord] = useState<MealRecord | null>(null);
  const [options, setOptions] = useState<MealOptions | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const [expected, setExpected] = useState<[string, string, string]>(["", "", ""]);
  const [actual, setActual] = useState<[string, string, string]>(["", "", ""]);
  const [remarks, setRemarks] = useState("");
  const [countsDirty, setCountsDirty] = useState(false);
  const [showCountErrors, setShowCountErrors] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[] | null>(null);

  const adopt = useCallback((updated: MealRecord) => {
    setRecord(updated);
    setExpected([text(updated.expected_students), text(updated.expected_staff), text(updated.expected_guests)]);
    setActual([text(updated.actual_students), text(updated.actual_staff), text(updated.actual_guests)]);
    setRemarks(updated.remarks ?? "");
    setCountsDirty(false);
    setShowCountErrors(false);
    setHistory(null);
  }, []);

  const load = useCallback(() => {
    api
      .get<MealRecord>(mealRecordEndpoint(params.id))
      .then((response) => {
        adopt(response);
        setLoadError("");
      })
      .catch((err: unknown) => setLoadError(errorMessage(err, "Unable to load the meal record.")));
  }, [params.id, adopt]);

  useEffect(() => {
    load();
  }, [load]);

  const editor = canEditMeals(role, permissions);
  useEffect(() => {
    if (!editor) return;
    api.get<MealOptions>(MEAL_OPTIONS_ENDPOINT).then(setOptions).catch(() => setOptions(null));
  }, [editor]);

  const back = (
    <Link href="/dashboard/meals" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
      <ArrowLeft size={15} aria-hidden />
      Meals
    </Link>
  );

  if (loadError && !record) {
    return <div className="space-y-4 pb-6">{back}<Card><ErrorState title="Couldn't load the meal record" message={loadError} onRetry={load} /></Card></div>;
  }
  if (!record) {
    return <div className="space-y-4 pb-6">{back}<Card><TableSkeleton rows={5} columns={5} /></Card></div>;
  }

  const open = record.status === "OPEN";
  const editable = open && editor;
  const manager = canReopenMeals(role);
  const countCheck = checkCounts({ expected, actual, actualAllowed: record.actual_allowed });

  async function run(call: () => Promise<MealRecord>, done: string) {
    setBusy(true);
    setActionError("");
    try {
      adopt(await call());
      toast.success(done);
      return true;
    } catch (err: unknown) {
      setActionError(errorMessage(err, "The request failed."));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function saveCounts() {
    setShowCountErrors(true);
    if (!countCheck.valid || !record) return;
    const hasActual = actual.every((v) => v.trim() !== "");
    await run(() => api.put<MealRecord>(mealRecordEndpoint(record.id), {
      expected_students: Number(expected[0]), expected_staff: Number(expected[1]), expected_guests: Number(expected[2]),
      ...(hasActual ? { actual_students: Number(actual[0]), actual_staff: Number(actual[1]), actual_guests: Number(actual[2]) } : {}),
      remarks: remarks.trim() || null,
    }), "Headcounts saved.");
  }

  async function loadHistory() {
    if (!record) return;
    try {
      setHistory((await api.get<{ items: HistoryEntry[] }>(mealActionEndpoint(record.id, "history"))).items);
    } catch (err: unknown) {
      setActionError(errorMessage(err, "Unable to load the history."));
    }
  }

  const countInput = (kind: "expected" | "actual", i: number) => {
    const values = kind === "expected" ? expected : actual;
    const setter = kind === "expected" ? setExpected : setActual;
    const label = `${kind === "expected" ? "Expected" : "Actual"} ${GROUPS[i]}`;
    return (
      <Field key={label} label={label} error={showCountErrors ? countCheck.fields[`${kind}_${GROUPS[i]}`] : undefined}>
        {({ id, describedBy }) => (
          <TextInput id={id} inputMode="numeric" aria-describedby={describedBy} value={values[i]}
            disabled={!editable || (kind === "actual" && !record.actual_allowed)}
            placeholder={kind === "actual" && !record.actual_allowed ? "After the meal" : undefined}
            onChange={(event) => {
              setter((current) => current.map((v, j) => (j === i ? event.target.value : v)) as [string, string, string]);
              setCountsDirty(true);
            }} />
        )}
      </Field>
    );
  };

  return (
    <div className="space-y-6 pb-6">
      {back}
      <PageHeader
        eyebrow="Meal record"
        icon={UtensilsCrossed}
        title={`${record.meal_session_name} · ${formatDay(record.meal_date)}`}
        description={`Recorded by ${record.created_by_name ?? "—"} · ${formatDateTime(record.created_at)}`}
        meta={<Badge tone={MEAL_STATUS_TONES[record.status]} dot>{MEAL_STATUS_LABELS[record.status]}</Badge>}
        actions={
          <>
            {editable && (
              <>
                <Button variant="secondary" icon={<Ban size={15} aria-hidden />} onClick={() => setDialog({ kind: "cancel" })}>Cancel record</Button>
                <Button icon={<CircleCheck size={16} aria-hidden />} onClick={() => setDialog({ kind: "close" })}>Close meal</Button>
              </>
            )}
            {record.status === "CLOSED" && manager && (
              <Button variant="warning" icon={<RotateCcw size={15} aria-hidden />} onClick={() => setDialog({ kind: "reopen" })}>Reopen</Button>
            )}
          </>
        }
      />

      {actionError && <Alert tone="error" title="Not done" onDismiss={() => setActionError("")}>{actionError}</Alert>}
      {record.status === "CLOSED" && (
        <Alert tone="success" title={`Closed by ${record.closed_by_name} · ${formatDateTime(record.closed_at)}`}>
          The record reconciles and is read-only.{manager ? " Reopen it with a reason to correct it." : " An Admin or Kitchen Manager can reopen it to correct it."}
        </Alert>
      )}
      {record.status === "CANCELLED" && (
        <Alert tone="info" title={`Cancelled by ${record.cancelled_by_name} · ${formatDateTime(record.cancelled_at)}`}>&ldquo;{record.cancellation_reason}&rdquo;</Alert>
      )}
      {record.reopen_count > 0 && (
        <p className="text-sm text-slate-600">
          Reopened {record.reopen_count}× · last by {record.reopened_by_name} · {formatDateTime(record.reopened_at)} · &ldquo;{record.reopen_reason}&rdquo;
        </p>
      )}
      {record.usage_changes_since_closing.length > 0 && (
        <Alert tone="warning" title="Ingredient issues changed since this meal was closed">
          {record.usage_changes_since_closing.map((c) => `${c.item_name}: ${plainQuantity(c.net_at_closing)} → ${plainQuantity(c.net_now)} ${c.unit_symbol}`).join("; ")}.
          {manager ? " Reopen and close the record again to record the new usage." : ""}
        </Alert>
      )}
      {record.outsourced_pending.length > 0 && (
        <Alert tone="warning" title="Outsourced food waiting — reconciliation pending">
          Confirmed outsourced food for this meal arrived after the record was closed, so it was not added (a closed record is never changed):{" "}
          {record.outsourced_pending.map((p, index) => (
            <span key={p.delivery_line_id}>
              {index > 0 ? "; " : ""}
              {plainQuantity(p.accepted_quantity)} {p.unit_symbol} {p.item_name} (
              <Link href={`/dashboard/outsourced-food/${p.order_id}`} className="underline">{p.order_number}</Link> · {p.delivery_number})
            </span>
          ))}
          .{manager ? " Reopen the record with a reason to add it automatically." : " An Admin or Kitchen Manager can reopen the record to add it."}
        </Alert>
      )}
      {open && record.reconciliation_problems.length > 0 && (
        <Alert tone="info" title="Before this meal can be closed">
          <ul className="list-disc pl-5">{record.reconciliation_problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </Alert>
      )}

      <Card className="space-y-4 p-5">
        <CardHeader title="Headcount" subtitle="People only — never used as food quantities. Expected before the meal, actual people served after it." />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">{GROUPS.map((_g, i) => countInput("expected", i))}</div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">{GROUPS.map((_g, i) => countInput("actual", i))}</div>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Fact label="Expected total">{record.expected_total}</Fact>
          <Fact label="Served total">{record.actual_total ?? "Not recorded"}</Fact>
        </dl>
        {showCountErrors && countCheck.form && <Alert tone="error">{countCheck.form}</Alert>}
        {editable && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <Field label="Remarks">
              {({ id }) => <TextInput id={id} maxLength={500} value={remarks} onChange={(event) => { setRemarks(event.target.value); setCountsDirty(true); }} />}
            </Field>
            <Button icon={<Save size={15} aria-hidden />} disabled={!countsDirty} loading={busy} onClick={saveCounts}>Save headcount</Button>
          </div>
        )}
        {!editable && record.remarks && <p className="text-sm text-slate-700"><span className="font-medium">Remarks:</span> {record.remarks}</p>}
      </Card>

      <Card>
        <CardHeader title="Dishes, distribution and leftovers"
          subtitle="Each dish in its own unit: available = distributed + remaining; leftovers classify what remains." />
        {editable && (
          <div className="flex flex-wrap gap-2 px-5 pb-4">
            <Button size="sm" icon={<Plus size={14} aria-hidden />} disabled={!options} onClick={() => setDialog({ kind: "dish" })}>Add dish</Button>
            <Button size="sm" variant="secondary" icon={<CornerDownRight size={14} aria-hidden />} onClick={() => setDialog({ kind: "carry" })}>Carry retained food in</Button>
          </div>
        )}
        {record.dishes.length === 0 ? (
          <p className="px-5 pb-5 text-sm text-slate-600">No dishes recorded.</p>
        ) : (
          <Table minWidth="980px">
            <THead>
              <tr>
                <TH>Dish</TH>
                <TH align="right">Available</TH>
                <TH align="right">Distributed</TH>
                <TH align="right">Remaining</TH>
                <TH>Leftovers</TH>
                {editable && <TH align="right">Actions</TH>}
              </tr>
            </THead>
            <TBody>
              {record.dishes.map((dish) => {
                const unit = dish.unit_symbol ?? "";
                const carriedOut = dish.leftovers.some((l) => l.carried_to);
                return (
                  <TR key={dish.id}>
                    <TD>
                      <span className="font-medium text-slate-900">{dish.dish_name}</span>
                      {dish.menu_name && <div className="text-xs text-slate-500">{dish.menu_name}</div>}
                      {dish.carried_in && (
                        <div className="text-xs text-amber-800">
                          Retained food carried in from{" "}
                          {dish.carried_in.record ? (
                            <Link href={`/dashboard/meals/${dish.carried_in.record.id}`} className="underline">{sessionLabel(dish.carried_in.record)}</Link>
                          ) : "an earlier meal"}
                        </div>
                      )}
                      {dish.received_from && (
                        <div className="text-xs text-sky-800" data-received-from>
                          Received (outsourced) ·{" "}
                          <Link href={`/dashboard/outsourced-food/${dish.received_from.order_id}`} className="underline">
                            {dish.received_from.order_number}
                          </Link>{" "}
                          · {dish.received_from.delivery_number}
                          {dish.received_from.supplier_name ? ` · ${dish.received_from.supplier_name}` : ""}
                          {Number(dish.received_from.rejected_quantity) > 0 &&
                            ` · ${plainQuantity(dish.received_from.rejected_quantity)} ${unit} rejected at delivery`}
                        </div>
                      )}
                      {dish.remarks && <div className="text-xs text-slate-500">{dish.remarks}</div>}
                    </TD>
                    <TD align="right" className="whitespace-nowrap">
                      {plainQuantity(dish.available_quantity)} {unit}
                      <div className="text-xs text-slate-500">
                        {dish.carried_in ? "carried in" : dish.received_from ? "received (outsourced)" : "prepared"}
                      </div>
                    </TD>
                    <TD align="right" className="whitespace-nowrap">{dish.distributed_quantity === null ? "—" : `${plainQuantity(dish.distributed_quantity)} ${unit}`}</TD>
                    <TD align="right" className="whitespace-nowrap">{dish.remaining_quantity === null ? "—" : `${plainQuantity(dish.remaining_quantity)} ${unit}`}</TD>
                    <TD className="max-w-72">
                      {dish.leftovers.length === 0 ? (
                        <span className="text-slate-400">{dish.remaining_quantity !== null && Number(dish.remaining_quantity) > 0 ? "Not classified" : "—"}</span>
                      ) : (
                        <ul className="space-y-0.5 text-sm">
                          {dish.leftovers.map((l) => (
                            <li key={l.id}>
                              {LEFTOVER_LABELS[l.classification]}: <span className="font-medium">{plainQuantity(l.quantity)} {unit}</span>
                              <span className="text-slate-500"> · {l.remarks}</span>
                              {l.carried_to && (
                                <div className="text-xs text-amber-800">
                                  carried to{" "}
                                  {l.carried_to.record ? <Link href={`/dashboard/meals/${l.carried_to.record.id}`} className="underline">{sessionLabel(l.carried_to.record)}</Link> : "a later meal"}
                                </div>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                      {dish.reconciled ? <Badge tone="success">Reconciled</Badge> : null}
                    </TD>
                    {editable && (
                      <TD align="right" className="whitespace-nowrap">
                        <div className="flex justify-end gap-1">
                          <IconButton label={`Distribution of ${dish.dish_name}`} icon={<Scale size={15} />} onClick={() => setDialog({ kind: "distribution", dish })} />
                          <IconButton label={`Edit ${dish.dish_name}`} icon={<Pencil size={15} />} disabled={!options} onClick={() => setDialog({ kind: "dish", dish })} />
                          {/* Received outsourced food is removed only by cancelling its delivery (Stage 8a). */}
                          {!dish.received_from && (
                            <IconButton label={`Remove ${dish.dish_name}`} tone="danger" icon={<Trash2 size={15} />} disabled={carriedOut}
                              onClick={() => setDialog({ kind: "remove", dish })} />
                          )}
                        </div>
                      </TD>
                    )}
                  </TR>
                );
              })}
            </TBody>
          </Table>
        )}
      </Card>

      <Card>
        <CardHeader title="Ingredient issues and actual usage"
          subtitle="Kitchen issues of the same date and meal session (linked automatically). Net usage = issued − unused returns, in each item's standard unit. Planned quantities are compared below when a meal plan exists." />
        <div className="space-y-4 px-5 pb-5">
          {record.linked_issues.length === 0 ? (
            <p className="text-sm text-slate-600">No kitchen issue recorded for this date and session.</p>
          ) : (
            <ul className="flex flex-wrap gap-2" aria-label="Linked issues">
              {record.linked_issues.map((issue) => (
                <li key={issue.id}>
                  <Link href={`/dashboard/kitchen-issues/${issue.id}`} className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-sm text-brand-700 hover:bg-slate-50">
                    {issue.issue_number}<span className="text-xs text-slate-500">· {issue.status.toLowerCase()}{issue.menu_name ? ` · ${issue.menu_name}` : ""}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {record.usage.length > 0 && (
            <Table minWidth="560px">
              <THead>
                <tr><TH>Item</TH><TH align="right">Issued</TH><TH align="right">Returned</TH><TH align="right">Net usage</TH></tr>
              </THead>
              <TBody>
                {record.usage.map((row) => (
                  <TR key={row.item_id}>
                    <TD>{row.item_name}</TD>
                    <TD align="right">{plainQuantity(row.issued_quantity)} {row.unit_symbol}</TD>
                    <TD align="right">{plainQuantity(row.returned_quantity)} {row.unit_symbol}</TD>
                    <TD align="right" className="font-semibold">{plainQuantity(row.net_quantity)} {row.unit_symbol}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </div>
      </Card>

      {record.planning && (
        <Card>
          <CardHeader title="Planned vs actual" icon={CalendarRange}
            subtitle="The meal plan of this exact date and meal session (MEAL02, PLAN08). Plans in a same-named session are reported, never linked." />
          <div className="space-y-4 px-5 pb-5">
            {record.planning.session_warnings.map((warning) => <Alert key={warning} tone="warning" title="Not linked">{warning}</Alert>)}
            {record.planning.comparison ? (
              <PlanComparison comparison={record.planning.comparison} showPlanLink />
            ) : (
              <p className="text-sm text-slate-600">
                No meal plan for this date and session.{" "}
                <Link href="/dashboard/meal-plans/new" className="text-brand-700 hover:underline">Plan a meal</Link>
              </p>
            )}
          </div>
        </Card>
      )}

      {manager && (
        <Card>
          <CardHeader title="Change history" subtitle="Every recorded change, closing, reopening and cancellation, oldest first." icon={History} />
          <div className="px-5 pb-5">
            {history === null ? (
              <Button size="sm" variant="secondary" icon={<History size={14} aria-hidden />} onClick={loadHistory}>Show history</Button>
            ) : (
              <ol className="space-y-2 text-sm" aria-label="History">
                {history.map((entry) => (
                  <li key={entry.id} className="flex flex-wrap gap-x-2">
                    <span className="font-medium text-slate-900">{HISTORY_LABELS[entry.action] ?? entry.action}</span>
                    <span className="text-slate-500">{entry.user_name} · {formatDateTime(entry.created_at)}</span>
                    {typeof entry.details.reason === "string" && <span className="text-slate-700">&ldquo;{entry.details.reason}&rdquo;</span>}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </Card>
      )}

      {dialog?.kind === "dish" && options && (
        <DishModal key={dialog.dish?.id ?? "new"} record={record} dish={dialog.dish} options={options}
          onClose={() => setDialog(null)}
          onSaved={(updated) => { adopt(updated); setDialog(null); toast.success(dialog.dish ? "Dish updated." : "Dish added."); }} />
      )}
      {dialog?.kind === "distribution" && (
        <DistributionModal key={dialog.dish.id} record={record} dish={dialog.dish} onClose={() => setDialog(null)}
          onSaved={(updated) => { adopt(updated); setDialog(null); toast.success("Distribution saved."); }} />
      )}
      {dialog?.kind === "carry" && (
        <CarryModal record={record} onClose={() => setDialog(null)}
          onSaved={(updated) => { adopt(updated); setDialog(null); toast.success("Retained food carried in."); }} />
      )}
      <ConfirmDialog
        open={dialog?.kind === "remove"}
        tone="danger"
        title={dialog?.kind === "remove" ? `Remove ${dialog.dish.dish_name}?` : "Remove dish"}
        description={dialog?.kind === "remove" && dialog.dish.carried_in
          ? "The carried-in retained food goes back to its source meal, where it can be carried again."
          : "The dish and its distribution and leftovers are removed from this open record. The change is kept in the history."}
        confirmLabel="Remove"
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={async () => {
          if (dialog?.kind !== "remove") return;
          await run(() => api.delete<MealRecord>(mealDishEndpoint(record.id, dialog.dish.id)), "Dish removed.");
          setDialog(null);
        }}
      />
      <ConfirmDialog
        open={dialog?.kind === "close"}
        tone="warning"
        title="Close this meal?"
        description={record.reconciliation_problems.length
          ? `It does not reconcile yet: ${record.reconciliation_problems.join(" ")}`
          : "The record becomes read-only. Only an Admin or Kitchen Manager can reopen it, with a reason."}
        confirmLabel="Close meal"
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={async () => {
          await run(() => api.post<MealRecord>(mealActionEndpoint(record.id, "close")), "Meal closed.");
          setDialog(null);
        }}
      />
      {(dialog?.kind === "cancel" || dialog?.kind === "reopen") && (
        <ReasonModal
          key={dialog.kind}
          open
          tone={dialog.kind === "reopen" ? "warning" : "danger"}
          title={dialog.kind === "reopen" ? "Reopen this meal record?" : "Cancel this meal record?"}
          description={dialog.kind === "reopen"
            ? "It becomes editable again. Your name, the time and the reason are kept on the record and in its history; it must reconcile again before closing. Retained food already carried to a later meal stays locked."
            : "For a record made for the wrong date or session. It is kept as cancelled with your reason, and the date and session can be recorded again."}
          confirmLabel={dialog.kind === "reopen" ? "Reopen" : "Cancel record"}
          placeholder={dialog.kind === "reopen" ? "e.g. Waste was weighed wrongly" : "e.g. Recorded for the wrong session"}
          onClose={() => setDialog(null)}
          onSubmit={async (reason) => {
            const kind = dialog.kind as "cancel" | "reopen";
            adopt(await api.post<MealRecord>(mealActionEndpoint(record.id, kind), { reason }));
            setDialog(null);
            toast.success(kind === "reopen" ? "Meal record reopened." : "Meal record cancelled.");
          }}
        />
      )}
    </div>
  );
}
