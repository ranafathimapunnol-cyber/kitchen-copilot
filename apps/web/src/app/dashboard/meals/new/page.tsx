"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Save, UtensilsCrossed } from "lucide-react";

import { api } from "@/lib/api/client";
import { MEAL_OPTIONS_ENDPOINT, MEAL_RECORDS_ENDPOINT } from "@/lib/api/endpoints";
import { checkCounts } from "@/lib/mealMath";
import { canViewMeals, type MealOptions, type MealRecord } from "@/lib/meals";
import { errorMessage } from "@/lib/payments";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import { TableSkeleton } from "@/components/ui/States";
import { useToast } from "@/components/ui/Toast";

export default function NewMealRecordPage() {
  const router = useRouter();
  const toast = useToast();
  const { role, permissions } = useAuthorization();
  const viewer = canViewMeals(role, permissions);
  const [options, setOptions] = useState<MealOptions | null>(null);
  const [loadError, setLoadError] = useState("");
  const [date, setDate] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [expected, setExpected] = useState<[string, string, string]>(["", "0", "0"]);
  const [remarks, setRemarks] = useState("");
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    let active = true;
    api
      .get<MealOptions>(MEAL_OPTIONS_ENDPOINT)
      .then((response) => {
        if (!active) return;
        setOptions(response);
        setDate((current) => current || response.today);
      })
      .catch((err: unknown) => {
        if (active) setLoadError(errorMessage(err, "Unable to load the meal sessions."));
      });
    return () => {
      active = false;
    };
  }, []);

  const check = checkCounts({ expected, actual: ["", "", ""], actualAllowed: true });
  const dateError = !date ? "Choose the meal date." : options && date > options.latest_date
    ? `Expected counts can be entered up to 14 days ahead (until ${options.latest_date}).` : undefined;
  const sessionError = sessionId ? undefined : "Choose the meal session.";

  async function save() {
    setShowErrors(true);
    setSubmitError("");
    if (!check.valid || dateError || sessionError) return;
    setSaving(true);
    try {
      const record = await api.post<MealRecord>(MEAL_RECORDS_ENDPOINT, {
        meal_date: date,
        meal_session_id: Number(sessionId),
        expected_students: Number(expected[0]),
        expected_staff: Number(expected[1]),
        expected_guests: Number(expected[2]),
        remarks: remarks.trim() || null,
      });
      toast.success(`${record.meal_session_name} meal recorded.`);
      if (viewer) {
        router.push(`/dashboard/meals/${record.id}`);
      } else {
        // A user who may record but not view meals stays on the form.
        setSessionId("");
        setExpected(["", "0", "0"]);
        setRemarks("");
        setShowErrors(false);
      }
    } catch (err: unknown) {
      setSubmitError(errorMessage(err, "Unable to save the meal record."));
    } finally {
      setSaving(false);
    }
  }

  const counts = ["Students", "Staff", "Guests"];

  return (
    <div className="space-y-6 pb-6">
      {viewer && (
        <Link href="/dashboard/meals" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
          <ArrowLeft size={15} aria-hidden />
          Meals
        </Link>
      )}
      <PageHeader eyebrow="Operations" icon={UtensilsCrossed} title="New meal record"
        description="One record per meal session and date. Enter the expected headcount now; dishes, distribution, leftovers and the actual people served are added on the record." />
      {loadError ? (
        <Alert tone="error" title="Couldn't load the form">{loadError}</Alert>
      ) : !options ? (
        <Card><TableSkeleton rows={3} columns={3} /></Card>
      ) : (
        <Card className="space-y-5 p-5">
          {submitError && <Alert tone="error" title="The meal record was not saved" onDismiss={() => setSubmitError("")}>{submitError}</Alert>}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Meal date" required error={showErrors ? dateError : undefined} hint="Up to 14 days ahead (interim)">
              {({ id, describedBy }) => (
                <TextInput id={id} type="date" max={options.latest_date} aria-describedby={describedBy} value={date}
                  onChange={(event) => setDate(event.target.value)} />
              )}
            </Field>
            <Field label="Meal session" required error={showErrors ? sessionError : undefined}>
              {({ id, describedBy }) => (
                <SelectInput id={id} aria-describedby={describedBy} value={sessionId} onChange={(event) => setSessionId(event.target.value)}>
                  <option value="">Choose a session…</option>
                  {options.meal_sessions.map((session) => (
                    <option key={session.id} value={session.id}>{session.name}</option>
                  ))}
                </SelectInput>
              )}
            </Field>
          </div>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-slate-700">Expected headcount</legend>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {counts.map((label, i) => (
                <Field key={label} label={`Expected ${label.toLowerCase()}`} required
                  error={showErrors ? check.fields[`expected_${label.toLowerCase()}`] : undefined}>
                  {({ id, describedBy }) => (
                    <TextInput id={id} inputMode="numeric" aria-describedby={describedBy} value={expected[i]}
                      onChange={(event) => setExpected((current) => current.map((v, j) => (j === i ? event.target.value : v)) as [string, string, string])} />
                  )}
                </Field>
              ))}
            </div>
          </fieldset>
          <Field label="Remarks">
            {({ id }) => <TextInput id={id} maxLength={500} value={remarks} onChange={(event) => setRemarks(event.target.value)} />}
          </Field>
          <div className="flex flex-col-reverse gap-2 border-t border-slate-100 pt-4 sm:flex-row sm:justify-end">
            <Button variant="secondary" onClick={() => router.push(viewer ? "/dashboard/meals" : "/dashboard")} disabled={saving}>Cancel</Button>
            <Button icon={<Save size={16} aria-hidden />} loading={saving} onClick={save}>Save meal record</Button>
          </div>
        </Card>
      )}
    </div>
  );
}
