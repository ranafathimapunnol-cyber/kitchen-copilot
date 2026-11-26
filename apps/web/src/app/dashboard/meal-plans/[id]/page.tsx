"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Ban, CalendarRange, CircleCheck, History, Pencil, Save, Scale } from "lucide-react";

import { api } from "@/lib/api/client";
import { MEAL_PLAN_PREFILL_ENDPOINT, mealPlanActionEndpoint, mealPlanEndpoint } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime, formatDay } from "@/lib/payments";
import {
  KIND_LABELS,
  PLAN_HISTORY_LABELS,
  PLAN_STATUS_LABELS,
  PLAN_STATUS_TONES,
  canApprovePlanning,
  type Comparison,
  type PlanDetail,
  type Prefill,
} from "@/lib/planning";
import { plainQuantity } from "@/lib/stockMath";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import ReasonModal from "@/components/kitchen/ReasonModal";
import PlanComparison from "@/components/planning/PlanComparison";
import PlanLinesEditor, { linesPayload, linesProblems, type LineDraft } from "@/components/planning/PlanLinesEditor";
import Alert from "@/components/ui/Alert";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { Field, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm break-words text-slate-900">{children}</dd>
    </div>
  );
}

export default function MealPlanPage() {
  const params = useParams<{ id: string }>();
  const { role } = useAuthorization();
  const toast = useToast();
  const [plan, setPlan] = useState<PlanDetail | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [dialog, setDialog] = useState<"approve" | "cancel" | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<{ prefill: Prefill; drafts: Record<number, LineDraft>; headcount: string; notes: string } | null>(null);
  const [showErrors, setShowErrors] = useState(false);

  const load = useCallback(() => {
    api
      .get<PlanDetail>(mealPlanEndpoint(params.id))
      .then((response) => {
        setPlan(response);
        setLoadError("");
        return api.get<Comparison>(mealPlanActionEndpoint(response.id, "comparison"));
      })
      .then((response) => setComparison(response))
      .catch((err: unknown) => setLoadError(errorMessage(err, "Unable to load the meal plan.")));
  }, [params.id]);

  useEffect(() => {
    load();
  }, [load]);

  const back = (
    <Link href="/dashboard/meal-plans" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
      <ArrowLeft size={15} aria-hidden />
      Meal Plans
    </Link>
  );

  if (loadError && !plan) {
    return <div className="space-y-4 pb-6">{back}<Card><ErrorState title="Couldn't load the meal plan" message={loadError} onRetry={load} /></Card></div>;
  }
  if (!plan) {
    return <div className="space-y-4 pb-6">{back}<Card><TableSkeleton rows={5} columns={5} /></Card></div>;
  }

  const approver = canApprovePlanning(role);
  const cancellable = plan.status === "DRAFT" || (plan.status === "APPROVED" && approver);

  async function adopt(updated: PlanDetail, message: string) {
    setPlan(updated);
    setEditing(null);
    setShowErrors(false);
    toast.success(message);
    try {
      setComparison(await api.get<Comparison>(mealPlanActionEndpoint(updated.id, "comparison")));
    } catch {
      setComparison(null);
    }
  }

  async function startEditing() {
    if (!plan) return;
    setActionError("");
    try {
      const query = new URLSearchParams({ plan_date: plan.plan_date, meal_session_id: String(plan.meal_session_id),
        menu_id: String(plan.menu_id) });
      const prefill = await api.get<Prefill>(`${MEAL_PLAN_PREFILL_ENDPOINT}?${query}`);
      const drafts: Record<number, LineDraft> = {};
      for (const item of prefill.items) {
        const line = plan.lines.find((l) => l.item_id === item.item_id);
        drafts[item.item_id] = {
          selected: Boolean(line),
          override: Boolean(line?.override),
          quantity: line?.override ? plainQuantity(line.override.quantity_per_person) : "",
          unitId: line?.override ? String(line.override.unit_id) : "",
          reason: line?.override?.reason ?? "",
        };
      }
      setEditing({ prefill, drafts, headcount: String(plan.expected_headcount), notes: plan.notes ?? "" });
    } catch (err: unknown) {
      setActionError(errorMessage(err, "Unable to load the menu's standards."));
    }
  }

  async function saveEdit() {
    if (!plan || !editing) return;
    setShowErrors(true);
    if (linesProblems(editing.prefill.items, editing.drafts, editing.headcount).length) return;
    setBusy(true);
    setActionError("");
    try {
      const updated = await api.put<PlanDetail>(mealPlanEndpoint(plan.id), {
        expected_headcount: Number(editing.headcount),
        notes: editing.notes.trim() || null,
        lines: linesPayload(editing.prefill.items, editing.drafts),
      });
      await adopt(updated, "Plan updated.");
    } catch (err: unknown) {
      setActionError(errorMessage(err, "Unable to save the plan."));
    } finally {
      setBusy(false);
    }
  }

  const editProblems = editing ? linesProblems(editing.prefill.items, editing.drafts, editing.headcount) : [];

  return (
    <div className="space-y-6 pb-6">
      {back}
      <PageHeader
        eyebrow="Meal plan"
        icon={CalendarRange}
        title={`${plan.plan_number} · ${plan.meal_session_name} · ${formatDay(plan.plan_date)}`}
        description={`${plan.menu_name} · created by ${plan.created_by_name ?? "—"} · ${formatDateTime(plan.created_at)}`}
        meta={<Badge tone={PLAN_STATUS_TONES[plan.status]} dot>{PLAN_STATUS_LABELS[plan.status]}</Badge>}
        actions={
          <>
            {plan.editable && !editing && (
              <Button variant="secondary" icon={<Pencil size={15} aria-hidden />} onClick={startEditing}>Edit draft</Button>
            )}
            {cancellable && !editing && (
              <Button variant="secondary" icon={<Ban size={15} aria-hidden />} onClick={() => setDialog("cancel")}>Cancel plan</Button>
            )}
            {plan.status === "DRAFT" && approver && !editing && (
              <Button icon={<CircleCheck size={16} aria-hidden />} disabled={!plan.editable} onClick={() => setDialog("approve")}>Approve</Button>
            )}
          </>
        }
      />

      {actionError && <Alert tone="error" title="Not done" onDismiss={() => setActionError("")}>{actionError}</Alert>}
      {plan.status === "APPROVED" && (
        <Alert tone="success" title={`Approved by ${plan.approved_by_name} · ${formatDateTime(plan.approved_at)}`}>
          The figures are frozen as approved and never change. To correct the plan, cancel it with a reason and create a new one.
        </Alert>
      )}
      {plan.status === "CANCELLED" && (
        <Alert tone="info" title={`Cancelled by ${plan.cancelled_by_name} · ${formatDateTime(plan.cancelled_at)}`}>
          &ldquo;{plan.cancellation_reason}&rdquo;{plan.approved_at ? " The figures below are the ones that were approved." : ""}
        </Alert>
      )}
      {plan.status === "DRAFT" && plan.approval_problems.length > 0 && (
        <Alert tone="info" title="Before this plan can be approved">
          <ul className="list-disc pl-5">{plan.approval_problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </Alert>
      )}
      {plan.session_warnings.map((warning) => <Alert key={warning} tone="warning" title="Not linked">{warning}</Alert>)}

      <Card className="p-5">
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Fact label="Date">{formatDay(plan.plan_date)}</Fact>
          <Fact label="Meal session">{plan.meal_session_name}</Fact>
          <Fact label="Menu">{plan.menu_name}</Fact>
          <Fact label="Expected headcount">{plan.expected_headcount}</Fact>
          <Fact label="Figures">{plan.calculation === "SNAPSHOT" ? "Snapshot at approval" : "Live — follows the standards in effect on the plan date"}</Fact>
          <Fact label="Meal record">
            {plan.meal_record ? (
              <Link href={`/dashboard/meals/${plan.meal_record.id}`} className="text-brand-700 hover:underline">
                {plan.meal_record.status.toLowerCase()} · {plan.meal_record.expected_total} expected
              </Link>
            ) : "None yet for this date and session"}
          </Fact>
          {plan.notes && <Fact label="Notes">{plan.notes}</Fact>}
        </dl>
      </Card>

      {editing ? (
        <Card>
          <CardHeader title="Edit draft" subtitle={editing.prefill.availability_note} />
          <div className="grid grid-cols-1 gap-4 px-5 pb-4 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]">
            <Field label="Expected headcount" required
              error={showErrors ? editProblems.find((p) => p.startsWith("Enter the expected") || p.startsWith("Use a whole")) : undefined}>
              {({ id, describedBy }) => (
                <TextInput id={id} inputMode="numeric" aria-describedby={describedBy} value={editing.headcount}
                  onChange={(event) => setEditing({ ...editing, headcount: event.target.value })} />
              )}
            </Field>
            <Field label="Notes">
              {({ id }) => <TextInput id={id} maxLength={500} value={editing.notes} onChange={(event) => setEditing({ ...editing, notes: event.target.value })} />}
            </Field>
          </div>
          <PlanLinesEditor items={editing.prefill.items} drafts={editing.drafts} headcount={editing.headcount} showErrors={showErrors}
            onChange={(itemId, draft) => setEditing({ ...editing, drafts: { ...editing.drafts, [itemId]: draft } })} />
          {showErrors && editProblems.length > 0 && (
            <div className="px-5 pt-4"><Alert tone="error"><ul className="list-disc pl-5">{editProblems.map((p) => <li key={p}>{p}</li>)}</ul></Alert></div>
          )}
          <div className="flex flex-col-reverse gap-2 px-5 py-4 sm:flex-row sm:justify-end">
            <Button variant="secondary" onClick={() => { setEditing(null); setShowErrors(false); }} disabled={busy}>Discard changes</Button>
            <Button icon={<Save size={15} aria-hidden />} loading={busy} onClick={saveEdit}>Save draft</Button>
          </div>
        </Card>
      ) : (
        <Card>
          <CardHeader title="Main items" subtitle={plan.availability_note} icon={Scale} />
          <Table minWidth="1000px">
            <THead>
              <tr>
                <TH>Item</TH>
                <TH>Per person</TH>
                <TH align="right">Required</TH>
                <TH align="right">In stock unit</TH>
                <TH align="right">Current stock</TH>
                <TH align="right">To buy</TH>
              </tr>
            </THead>
            <TBody>
              {plan.lines.map((line) => (
                <TR key={line.id}>
                  <TD>
                    <span className="font-medium text-slate-900">{line.item_name}</span>
                    <div className="text-xs text-slate-500">{line.item_kind ? KIND_LABELS[line.item_kind] : "Not classified"}</div>
                    {line.problems.map((p) => <div key={p} className="text-xs text-red-700">{p}</div>)}
                  </TD>
                  <TD>
                    {line.quantity_per_person ? `${plainQuantity(line.quantity_per_person)} ${line.unit_symbol}` : "—"}
                    {line.override ? (
                      <div className="text-xs text-amber-800">
                        One-day override: &ldquo;{line.override.reason}&rdquo; (standard {plainQuantity(line.standard?.quantity_per_person)} {line.standard?.unit_symbol})
                      </div>
                    ) : line.standard ? (
                      <div className="text-xs text-slate-500">standard v{line.standard.version_no}{line.standard.effective_from ? ` from ${formatDay(line.standard.effective_from)}` : ""}</div>
                    ) : null}
                  </TD>
                  <TD align="right" className="whitespace-nowrap">
                    {line.required_quantity ? `${plainQuantity(line.required_quantity)} ${line.unit_symbol}` : "—"}
                    {line.required_display.map((d) => <div key={d.unit_symbol} className="text-xs text-slate-500">= {plainQuantity(d.quantity)} {d.unit_symbol}</div>)}
                    {line.rounded_up && <div><Badge tone="brand">rounded up</Badge></div>}
                  </TD>
                  <TD align="right" className="whitespace-nowrap">{line.required_base_quantity ? `${plainQuantity(line.required_base_quantity)} ${line.base_unit_symbol}` : "—"}</TD>
                  <TD align="right" className="whitespace-nowrap">{plainQuantity(line.available_stock)} {line.base_unit_symbol}</TD>
                  <TD align="right" className="whitespace-nowrap font-semibold">{line.procurement_gap ? `${plainQuantity(line.procurement_gap)} ${line.base_unit_symbol}` : "—"}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      )}

      <Card>
        <CardHeader title="Planned vs actual" subtitle="Against the meal record of the same date and meal session (PLAN08)." />
        <div className="px-5 pb-5">
          {comparison ? <PlanComparison comparison={comparison} /> : <TableSkeleton rows={2} columns={4} />}
        </div>
      </Card>

      <Card>
        <CardHeader title="History" subtitle="Every change, approval and cancellation, oldest first." icon={History} />
        <ol className="space-y-2 px-5 pb-5 text-sm" aria-label="History">
          {plan.history.map((entry) => (
            <li key={entry.id} className="flex flex-wrap gap-x-2">
              <span className="font-medium text-slate-900">{PLAN_HISTORY_LABELS[entry.action] ?? entry.action}</span>
              <span className="text-slate-500">{entry.user_name} · {formatDateTime(entry.created_at)}</span>
              {typeof entry.details.reason === "string" && <span className="text-slate-700">&ldquo;{entry.details.reason}&rdquo;</span>}
            </li>
          ))}
        </ol>
      </Card>

      <ConfirmDialog
        open={dialog === "approve"}
        tone="warning"
        title={`Approve ${plan.plan_number}?`}
        description={plan.approval_problems.length
          ? `It cannot be approved yet: ${plan.approval_problems.join(" ")}`
          : "The figures are saved as they are now, with the standard used for each item, and never change. Approving does not change stock or create a purchase."}
        confirmLabel="Approve"
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={async () => {
          setBusy(true);
          setActionError("");
          try {
            await adopt(await api.post<PlanDetail>(mealPlanActionEndpoint(plan.id, "approve")), "Plan approved.");
          } catch (err: unknown) {
            setActionError(errorMessage(err, "Unable to approve the plan."));
          } finally {
            setBusy(false);
            setDialog(null);
          }
        }}
      />
      {dialog === "cancel" && (
        <ReasonModal
          open
          tone="danger"
          title={`Cancel ${plan.plan_number}?`}
          description={plan.status === "APPROVED"
            ? "The approved figures stay as history. Create a new plan for this date and session afterwards."
            : "The draft is kept as cancelled with your reason; the date and session can be planned again."}
          confirmLabel="Cancel plan"
          placeholder="e.g. Headcount changed after approval"
          onClose={() => setDialog(null)}
          onSubmit={async (reason) => {
            await adopt(await api.post<PlanDetail>(mealPlanActionEndpoint(plan.id, "cancel"), { reason }), "Plan cancelled.");
            setDialog(null);
          }}
        />
      )}
    </div>
  );
}
