"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, CalendarRange, Save } from "lucide-react";

import { api } from "@/lib/api/client";
import { MEAL_PLANS_ENDPOINT, MEAL_PLAN_OPTIONS_ENDPOINT, MEAL_PLAN_PREFILL_ENDPOINT } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/payments";
import type { PlanDetail, PlanOptions, Prefill } from "@/lib/planning";
import PlanLinesEditor, { linesPayload, linesProblems, type LineDraft } from "@/components/planning/PlanLinesEditor";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import { TableSkeleton } from "@/components/ui/States";
import { useToast } from "@/components/ui/Toast";

export default function NewMealPlanPage() {
  const router = useRouter();
  const toast = useToast();
  const [options, setOptions] = useState<PlanOptions | null>(null);
  const [loadError, setLoadError] = useState("");
  const [date, setDate] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [menuId, setMenuId] = useState("");
  const [headcount, setHeadcount] = useState("");
  const [notes, setNotes] = useState("");
  const [prefill, setPrefill] = useState<Prefill | null>(null);
  const [prefillKey, setPrefillKey] = useState("");
  const [prefillError, setPrefillError] = useState("");
  const [drafts, setDrafts] = useState<Record<number, LineDraft>>({});
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    let active = true;
    api
      .get<PlanOptions>(MEAL_PLAN_OPTIONS_ENDPOINT)
      .then((response) => {
        if (!active) return;
        setOptions(response);
        setDate((current) => current || response.today);
      })
      .catch((err: unknown) => {
        if (active) setLoadError(errorMessage(err, "Unable to load the planning form."));
      });
    return () => {
      active = false;
    };
  }, []);

  const wanted = date && sessionId && menuId ? `${date}|${sessionId}|${menuId}` : "";
  useEffect(() => {
    if (!wanted) return;
    let active = true;
    const [planDate, session, menu] = wanted.split("|");
    const params = new URLSearchParams({ plan_date: planDate, meal_session_id: session, menu_id: menu });
    api
      .get<Prefill>(`${MEAL_PLAN_PREFILL_ENDPOINT}?${params}`)
      .then((response) => {
        if (!active) return;
        setPrefill(response);
        setPrefillError("");
        setDrafts(Object.fromEntries(response.items.map((item) => [item.item_id, {
          selected: true, override: false, quantity: "", unitId: "", reason: "" }])));
      })
      .catch((err: unknown) => {
        if (active) {
          setPrefill(null);
          setPrefillError(errorMessage(err, "Unable to load the menu's standards."));
        }
      })
      .finally(() => {
        if (active) setPrefillKey(wanted);
      });
    return () => {
      active = false;
    };
  }, [wanted]);

  const session = options?.meal_sessions.find((s) => String(s.id) === sessionId);
  const menus = options?.menus.filter((menu) => String(menu.meal_session_id) === sessionId) ?? [];
  const current = prefill && prefillKey === wanted ? prefill : null;
  const dateError = !date ? "Choose the plan date." : options && date < options.today ? "Plans are made for today or a later date." : undefined;
  const problems = current ? linesProblems(current.items, drafts, headcount) : [];

  async function save() {
    setShowErrors(true);
    setSubmitError("");
    if (!current || dateError || problems.length || current.existing_plan) return;
    setSaving(true);
    try {
      const plan = await api.post<PlanDetail>(MEAL_PLANS_ENDPOINT, {
        plan_date: date,
        meal_session_id: Number(sessionId),
        menu_id: Number(menuId),
        expected_headcount: Number(headcount),
        notes: notes.trim() || null,
        lines: linesPayload(current.items, drafts),
      });
      toast.success(`Meal plan ${plan.plan_number} saved as a draft.`);
      router.push(`/dashboard/meal-plans/${plan.id}`);
    } catch (err: unknown) {
      setSubmitError(errorMessage(err, "Unable to save the meal plan."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6 pb-6">
      <Link href="/dashboard/meal-plans" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
        <ArrowLeft size={15} aria-hidden />
        Meal Plans
      </Link>
      <PageHeader eyebrow="Menu Planning" icon={CalendarRange} title="New meal plan"
        description="Choose the date, meal session and menu, enter the expected headcount and tick only the main items needed. Quantities recalculate as you type; the plan is saved as a draft and approved separately." />
      {loadError ? (
        <Alert tone="error" title="Couldn't load the form">{loadError}</Alert>
      ) : !options ? (
        <Card><TableSkeleton rows={3} columns={3} /></Card>
      ) : (
        <>
          <Card className="space-y-5 p-5">
            {submitError && <Alert tone="error" title="The meal plan was not saved" onDismiss={() => setSubmitError("")}>{submitError}</Alert>}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="Plan date" required error={showErrors ? dateError : undefined}>
                {({ id, describedBy }) => (
                  <TextInput id={id} type="date" min={options.today} aria-describedby={describedBy} value={date}
                    onChange={(event) => setDate(event.target.value)} />
                )}
              </Field>
              <Field label="Meal session" required error={showErrors && !sessionId ? "Choose the meal session." : undefined}>
                {({ id, describedBy }) => (
                  <SelectInput id={id} aria-describedby={describedBy} value={sessionId}
                    onChange={(event) => { setSessionId(event.target.value); setMenuId(""); }}>
                    <option value="">Choose a session…</option>
                    {options.meal_sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </SelectInput>
                )}
              </Field>
              <Field label="Menu" required error={showErrors && !menuId ? "Choose the menu." : undefined}>
                {({ id, describedBy }) => (
                  <SelectInput id={id} aria-describedby={describedBy} value={menuId} disabled={!sessionId}
                    onChange={(event) => setMenuId(event.target.value)}>
                    <option value="">{sessionId ? "Choose a menu…" : "Choose a session first"}</option>
                    {menus.map((menu) => <option key={menu.id} value={menu.id}>{menu.name}</option>)}
                  </SelectInput>
                )}
              </Field>
              <Field label="Expected headcount" required
                error={showErrors ? problems.find((p) => p.startsWith("Enter the expected") || p.startsWith("Use a whole")) : undefined}>
                {({ id, describedBy }) => (
                  <TextInput id={id} inputMode="numeric" aria-describedby={describedBy} value={headcount}
                    onChange={(event) => setHeadcount(event.target.value)} />
                )}
              </Field>
            </div>
            {session && session.notes.map((note) => <Alert key={note} tone="warning">{note}</Alert>)}
            {current?.meal_record && (
              <Alert tone="info" title={`Meal record of this session: ${current.meal_record.expected_total} expected`}>
                <Button size="sm" variant="secondary" onClick={() => setHeadcount(String(current.meal_record?.expected_total ?? ""))}>
                  Use {current.meal_record.expected_total} as the headcount
                </Button>
              </Alert>
            )}
            {current?.session_warnings.filter((w) => !session?.notes.includes(w)).map((warning) => (
              <Alert key={warning} tone="warning" title="Not linked">{warning}</Alert>
            ))}
            {current?.existing_plan && (
              <Alert tone="error" title="A plan already exists for this date and session">
                <Link href={`/dashboard/meal-plans/${current.existing_plan.id}`} className="underline">{current.existing_plan.plan_number}</Link>
                {" "}({current.existing_plan.status.toLowerCase()}). Cancel it first to plan again.
              </Alert>
            )}
            <Field label="Notes">
              {({ id }) => <TextInput id={id} maxLength={500} value={notes} onChange={(event) => setNotes(event.target.value)} />}
            </Field>
          </Card>

          {wanted && (
            <Card>
              <CardHeader title="Main items" subtitle={current?.availability_note ?? "Current availability, not a forecast."} />
              {prefillError ? (
                <div className="px-5 pb-5"><Alert tone="error">{prefillError}</Alert></div>
              ) : !current ? (
                <TableSkeleton rows={3} columns={6} />
              ) : current.items.length === 0 ? (
                <div className="px-5 pb-5">
                  <Alert tone="info" title="No approved standard for this menu on this date">
                    Approve portion standards for this menu first (Portion Standards).
                  </Alert>
                </div>
              ) : (
                <PlanLinesEditor items={current.items} drafts={drafts} headcount={headcount} showErrors={showErrors}
                  onChange={(itemId, draft) => setDrafts((all) => ({ ...all, [itemId]: draft }))} />
              )}
              {current && current.unavailable_items.length > 0 && (
                <ul className="space-y-0.5 px-5 pb-4 text-xs text-slate-500">
                  {current.unavailable_items.map((item) => <li key={item.item_id}>{item.item_name}: {item.reason}</li>)}
                </ul>
              )}
            </Card>
          )}

          {showErrors && problems.length > 0 && (
            <Alert tone="error" title="Before saving">
              <ul className="list-disc pl-5">{problems.map((p) => <li key={p}>{p}</li>)}</ul>
            </Alert>
          )}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="secondary" onClick={() => router.push("/dashboard/meal-plans")} disabled={saving}>Cancel</Button>
            <Button icon={<Save size={16} aria-hidden />} loading={saving} disabled={!current || Boolean(current.existing_plan)} onClick={save}>
              Save draft plan
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
