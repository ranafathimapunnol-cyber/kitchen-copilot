"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, ListTodo, Pencil, Play, Plus, RotateCcw, XCircle } from "lucide-react";

import { api } from "@/lib/api/client";
import { errorMessage, formatDateTime } from "@/lib/payments";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Field, SelectInput, TextArea, TextInput } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { useToast } from "@/components/ui/Toast";

type Task = {
  id: number; title: string; description: string | null; category: string; priority: "LOW" | "NORMAL" | "HIGH";
  status: "OPEN" | "IN_PROGRESS" | "DONE" | "CANCELLED"; assigned_to: number; assigned_to_name: string | null;
  due_date: string | null; staff_note: string | null; created_by_name: string | null; created_at: string;
  updated_at: string; completed_at: string | null; version: number;
};
type Listing = { items: Task[]; can_manage: boolean; can_update_own: boolean; staff: { id: number; full_name: string }[];
  categories: string[]; priorities: string[] };
type Form = { id?: number; version?: number; title: string; description: string; category: string; priority: string;
  assigned_to: string; due_date: string };

const TASKS = "/api/tasks";
const CATEGORY_LABELS: Record<string, string> = {
  PURCHASE: "Purchase", INVENTORY: "Inventory", STOCK_COUNT: "Stock counting", GOODS_RECEIPT: "Goods receipt",
  MEAL_PREPARATION: "Meal preparation", CLEANING: "Cleaning", WASTE: "Waste", GENERAL: "General kitchen work",
};
const STATUS_LABEL = { OPEN: "Open", IN_PROGRESS: "In progress", DONE: "Done", CANCELLED: "Cancelled" } as const;
const STATUS_TONE = { OPEN: "neutral", IN_PROGRESS: "warning", DONE: "success", CANCELLED: "neutral" } as const;
const PRIORITY_TONE = { LOW: "neutral", NORMAL: "neutral", HIGH: "danger" } as const;
const EMPTY: Form = { title: "", description: "", category: "GENERAL", priority: "NORMAL", assigned_to: "", due_date: "" };

/** Staff tasks: Admins assign and track; Staff see and update their own. */
export default function TasksPage() {
  const toast = useToast();
  const [filter, setFilter] = useState<"ACTIVE" | "DONE" | "CANCELLED" | "ALL">("ACTIVE");
  const [data, setData] = useState<Listing | null>(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState<Form | null>(null);
  const [formError, setFormError] = useState("");
  const [note, setNote] = useState<{ task: Task; status: Task["status"]; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const q = filter === "ALL" ? "" : `?status=${filter}`;
    api.get<Listing>(`${TASKS}${q}`).then((d) => { setData(d); setError(""); })
      .catch((err: unknown) => setError(errorMessage(err, "Unable to load tasks.")));
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  async function save() {
    if (!form) return;
    setBusy(true);
    setFormError("");
    const body = { title: form.title.trim(), description: form.description.trim() || null, category: form.category,
      priority: form.priority, assigned_to: Number(form.assigned_to), due_date: form.due_date || null };
    try {
      if (form.id) await api.put(`${TASKS}/${form.id}?version=${form.version}`, body);
      else await api.post(TASKS, body);
      toast.success(form.id ? "Task updated." : "Task assigned.");
      setForm(null);
      load();
    } catch (err) {
      setFormError(errorMessage(err, "The task could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  async function move(task: Task, status: Task["status"], text?: string) {
    setBusy(true);
    try {
      await api.post(`${TASKS}/${task.id}/status`, { status, version: task.version, note: text?.trim() || null });
      toast.success(`Task ${STATUS_LABEL[status].toLowerCase()}.`);
      setNote(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "The status could not be changed."));
      load();
    } finally {
      setBusy(false);
    }
  }

  const manage = Boolean(data?.can_manage);
  const own = Boolean(data?.can_update_own) && !manage;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Overview" icon={ListTodo} title="Tasks"
        description={manage ? "Assign kitchen work to Staff and follow it through to done." : "Work assigned to you. Mark it started and done as you go."}
        actions={manage ? <Button icon={<Plus size={16} />} onClick={() => { setFormError(""); setForm({ ...EMPTY, assigned_to: String(data?.staff[0]?.id ?? "") }); }}>New task</Button> : undefined} />
      <SegmentedControl label="Show" value={filter} onChange={setFilter}
        options={[{ value: "ACTIVE", label: "Open and in progress" }, { value: "DONE", label: "Done" }, { value: "CANCELLED", label: "Cancelled" }, { value: "ALL", label: "All" }]} />

      {error ? <ErrorState message={error} onRetry={load} /> : !data ? <TableSkeleton rows={4} /> : data.items.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white"><EmptyState icon={ListTodo} title="No tasks here"
          description={manage ? (data.staff.length ? "Assign the first task with New task." : "Add Staff on User Accounts first; tasks are assigned to Staff.") : "Nothing assigned to you in this view."} /></div>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2" data-task-list>
          {data.items.map((t) => (
            <li key={t.id} className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4" data-task={t.status}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold tracking-[0.12em] text-slate-500 uppercase">{CATEGORY_LABELS[t.category] ?? t.category}</p>
                  <p className="mt-0.5 font-semibold text-slate-900">{t.title}</p>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  {t.priority === "HIGH" && <Badge tone={PRIORITY_TONE.HIGH}>High</Badge>}
                  <Badge tone={STATUS_TONE[t.status]} dot>{STATUS_LABEL[t.status]}</Badge>
                </div>
              </div>
              {t.description && <p className="text-sm whitespace-pre-line text-slate-600">{t.description}</p>}
              <p className="text-xs text-slate-500">
                {manage && <>For <span className="font-medium text-slate-700">{t.assigned_to_name}</span> · </>}
                {t.due_date ? `Due ${t.due_date}` : "No due date"} · assigned by {t.created_by_name} {formatDateTime(t.created_at)}
                {t.completed_at && <> · done {formatDateTime(t.completed_at)}</>}
              </p>
              {t.staff_note && <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700"><span className="font-medium">Note:</span> {t.staff_note}</p>}
              <div className="flex flex-wrap gap-2">
                {manage && t.status !== "DONE" && t.status !== "CANCELLED" && <>
                  <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => { setFormError(""); setForm({ id: t.id, version: t.version, title: t.title, description: t.description ?? "", category: t.category, priority: t.priority, assigned_to: String(t.assigned_to), due_date: t.due_date ?? "" }); }}>Edit</Button>
                  <Button size="sm" variant="ghost" icon={<XCircle size={14} />} loading={busy} onClick={() => move(t, "CANCELLED")}>Cancel task</Button>
                </>}
                {manage && (t.status === "DONE" || t.status === "CANCELLED") && <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} loading={busy} onClick={() => move(t, "OPEN")}>Reopen</Button>}
                {own && t.status === "OPEN" && <Button size="sm" variant="secondary" icon={<Play size={14} />} loading={busy} onClick={() => move(t, "IN_PROGRESS")}>Start</Button>}
                {own && (t.status === "OPEN" || t.status === "IN_PROGRESS") && <Button size="sm" icon={<CheckCircle2 size={14} />} onClick={() => setNote({ task: t, status: "DONE", text: t.staff_note ?? "" })}>Mark done</Button>}
                {own && t.status === "DONE" && <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} loading={busy} onClick={() => move(t, "IN_PROGRESS")}>Not finished</Button>}
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal open={form !== null} onClose={() => !busy && setForm(null)} size="lg" dismissible={!busy}
        title={form?.id ? "Edit task" : "New task"} description="Tasks are assigned to active Staff of this campus."
        footer={<><Button variant="secondary" onClick={() => setForm(null)} disabled={busy}>Cancel</Button>
          <Button loading={busy} disabled={!form || form.title.trim().length < 3 || !form.assigned_to} onClick={save}>{form?.id ? "Save" : "Assign task"}</Button></>}>
        {formError && <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">{formError}</p>}
        {form && data && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Title" required className="sm:col-span-2">{({ id }) => <TextInput id={id} value={form.title} maxLength={200} onChange={(e) => setForm({ ...form, title: e.target.value })} data-autofocus />}</Field>
            <Field label="Type of work">{({ id }) => (
              <SelectInput id={id} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {data.categories.map((c) => <option key={c} value={c}>{CATEGORY_LABELS[c] ?? c}</option>)}
              </SelectInput>)}</Field>
            <Field label="Assign to" required>{({ id }) => (
              <SelectInput id={id} value={form.assigned_to} onChange={(e) => setForm({ ...form, assigned_to: e.target.value })}>
                {data.staff.length === 0 && <option value="">No active Staff</option>}
                {data.staff.map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
              </SelectInput>)}</Field>
            <Field label="Priority">{({ id }) => (
              <SelectInput id={id} value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                <option value="LOW">Low</option><option value="NORMAL">Normal</option><option value="HIGH">High</option>
              </SelectInput>)}</Field>
            <Field label="Due date">{({ id }) => <TextInput id={id} type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />}</Field>
            <Field label="Details" className="sm:col-span-2">{({ id }) => <TextArea id={id} rows={3} maxLength={2000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}</Field>
          </div>
        )}
      </Modal>

      <Modal open={note !== null} onClose={() => !busy && setNote(null)} size="sm" title="Mark the task done?"
        description={note?.task.title}
        footer={<><Button variant="secondary" onClick={() => setNote(null)} disabled={busy}>Cancel</Button>
          <Button loading={busy} onClick={() => note && move(note.task, note.status, note.text)}>Mark done</Button></>}>
        <Field label="Note for the Admin (optional)">{({ id }) => <TextArea id={id} rows={3} maxLength={1000} value={note?.text ?? ""} onChange={(e) => note && setNote({ ...note, text: e.target.value })} data-autofocus />}</Field>
      </Modal>
    </div>
  );
}
