"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Pencil, Power, PowerOff, RefreshCw, UserPlus } from "lucide-react";

import { api } from "@/lib/api/client";
import { errorMessage, formatDateTime } from "@/lib/payments";
import { PLATFORM_API, ROLE_LABELS, money, monthToDate, n, query, type CampusDetail, type ErpStatus, type Period, type PlatformUserRow } from "@/lib/platform";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Field, SelectInput, TextArea, TextInput } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { CampusFields, formBody, type CampusForm } from "@/components/platform/CampusForm";
import CampusMediaSection from "@/components/platform/CampusMediaSection";
import { ActiveBadge, ErpBadge, Kpi, PeriodFilter, PlatformHeader, Section, usePlatformGet } from "@/components/platform/parts";

type Dialog = "edit" | "deactivate" | "activate" | "admin" | null;

/** One campus: details, status, users, operational summary and integration. */
export default function CampusPage() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const [period, setPeriod] = useState<Period>(monthToDate());
  const campus = usePlatformGet<CampusDetail>(`${PLATFORM_API}/campuses/${id}${query({ ...period })}`);
  const users = usePlatformGet<{ items: PlatformUserRow[] }>(`${PLATFORM_API}/campuses/${id}/users`);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [form, setForm] = useState<CampusForm | null>(null);
  const [reason, setReason] = useState("");
  const [admin, setAdmin] = useState({ full_name: "", email: "" });
  const [erp, setErp] = useState<{ is_enabled: boolean; base_url: string; timeout_seconds: number; max_retries: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");

  const c = campus.data;

  function open(kind: Dialog) {
    setDialogError("");
    setReason("");
    if (kind === "edit" && c) setForm({ name: c.name, code: c.code, address: c.address ?? "", contact_name: c.contact_name ?? "", contact_email: c.contact_email ?? "", contact_phone: c.contact_phone ?? "" });
    if (kind === "admin") setAdmin({ full_name: "", email: "" });
    setDialog(kind);
  }

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setDialogError("");
    try {
      await action();
      toast.success(success);
      setDialog(null);
      campus.reload();
      users.reload();
    } catch (err) {
      setDialogError(errorMessage(err, "That did not work."));
    } finally {
      setBusy(false);
    }
  }

  async function saveErp() {
    if (!erp) return;
    setBusy(true);
    try {
      await api.put<ErpStatus>(`${PLATFORM_API}/campuses/${id}/integrations/erp-headcount`, { ...erp, base_url: erp.base_url.trim() || null });
      toast.success("Integration settings saved.");
      setErp(null);
      campus.reload();
    } catch (err) {
      toast.error(errorMessage(err, "The settings could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  async function syncNow() {
    setBusy(true);
    try {
      const r = await api.post<{ status: string; error: string | null }>(`${PLATFORM_API}/campuses/${id}/integrations/erp-headcount/sync`);
      if (r.status === "SUCCEEDED") toast.success("Sync finished.");
      else toast.error(r.error ?? `Sync ${r.status.toLowerCase()}.`);
      campus.reload();
    } catch (err) {
      toast.error(errorMessage(err, "The sync could not run."));
    } finally {
      setBusy(false);
    }
  }

  if (campus.error) return <ErrorState message={campus.error} onRetry={campus.reload} />;
  if (!c) return <TableSkeleton rows={6} />;
  const ops = c.operations;

  return (
    <div className="space-y-6" data-campus={c.code}>
      <Link href="/platform/campuses" className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900"><ArrowLeft size={15} aria-hidden /> Campuses</Link>
      <PlatformHeader eyebrow={`Campus · ${c.code}`} title={c.name}
        description={c.is_active ? "Active: its users can sign in and work." : `Deactivated ${formatDateTime(c.deactivated_at)}: ${c.deactivation_reason ?? ""}. Its users cannot sign in; every record is kept.`}
        actions={<>
          <Button variant="secondary" icon={<Pencil size={15} />} onClick={() => open("edit")}>Edit details</Button>
          {c.is_active
            ? <Button variant="danger" icon={<PowerOff size={15} />} onClick={() => open("deactivate")}>Deactivate</Button>
            : <Button icon={<Power size={15} />} onClick={() => open("activate")}>Activate</Button>}
        </>} />

      <div className="flex flex-wrap items-center gap-2"><ActiveBadge active={c.is_active} /><ErpBadge erp={c.erp} />
        {c.alerts?.map((a, i) => <Badge key={i} tone={a.level === "critical" ? "danger" : a.level === "warning" ? "warning" : "neutral"}>{a.text}</Badge>)}
      </div>

      <PeriodFilter value={period} onChange={setPeriod} />
      {ops && (
        <div className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 xl:grid-cols-4">
          <Kpi label="Purchases in period" value={money(c.purchases.total)} note={`${n(c.purchases.bill_count)} bills`} tone="accent" />
          <Kpi label="Outstanding payables" value={money(ops.outstanding_payables)} note={`${n(ops.open_bills)} open bills`} />
          <Kpi label="Items below minimum" value={n(ops.stock.below_minimum)} tone={ops.stock.below_minimum ? "warning" : "neutral"}
            note={`${n(ops.stock.out_of_stock)} of ${n(ops.stock.items_tracked)} out of stock`} />
          <Kpi label="Waiting for action" value={n(ops.pending_adjustments + ops.meals_awaiting_close + ops.draft_plans)}
            note={`${ops.pending_adjustments} adjustments · ${ops.meals_awaiting_close} old meal records · ${ops.draft_plans} draft plans`} />
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Section title="Campus users" description="Read-only here: the campus's Admin manages its users and permissions."
          action={c.is_active ? <Button size="sm" variant="secondary" icon={<UserPlus size={15} />} onClick={() => open("admin")}>Invite campus Admin</Button> : undefined}>
          {!users.data ? <TableSkeleton rows={3} /> : users.data.items.length === 0 ? <p className="px-5 py-6 text-sm text-slate-500">No users yet. Invite the campus&rsquo;s first Admin.</p> : (
            <Table minWidth="560px">
              <THead><TR><TH>Name</TH><TH>Role</TH><TH>Status</TH><TH>Last sign-in</TH></TR></THead>
              <TBody>{users.data.items.map((u) => (
                <TR key={u.id}><TD><span className="font-medium text-slate-900">{u.full_name}</span><span className="block text-xs text-slate-500">{u.email}</span></TD>
                  <TD>{ROLE_LABELS[u.role] ?? u.role}</TD><TD><Badge tone={u.is_active ? "success" : "neutral"} dot>{u.is_active ? "Active" : "Inactive"}</Badge></TD>
                  <TD className="text-sm text-slate-600">{formatDateTime(u.last_login_at)}</TD></TR>
              ))}</TBody>
            </Table>
          )}
        </Section>

        <div className="space-y-6">
          <Section title="Details">
            <dl className="grid grid-cols-[8rem_minmax(0,1fr)] gap-x-4 gap-y-2.5 px-5 py-4 text-sm">
              <dt className="text-slate-500">Code</dt><dd className="font-medium text-slate-900">{c.code}</dd>
              <dt className="text-slate-500">Organisation</dt><dd>{c.organization_name ?? "Not assigned"}</dd>
              <dt className="text-slate-500">Contact</dt><dd>{[c.contact_name, c.contact_email, c.contact_phone].filter(Boolean).join(" · ") || "—"}</dd>
              <dt className="text-slate-500">Address</dt><dd className="whitespace-pre-line">{c.address ?? "—"}</dd>
              <dt className="text-slate-500">Registered</dt><dd>{formatDateTime(c.created_at)}</dd>
              <dt className="text-slate-500">Last activity</dt><dd>{formatDateTime(c.last_activity_at)}</dd>
            </dl>
          </Section>
          <CampusMediaSection campusId={c.id} campusName={c.name} media={c.media} onChange={campus.reload} />
          <Section title="ERP headcount integration" description="Prepared; the campus ERP API documentation has not been supplied yet."
            action={!erp ? <Button size="sm" variant="secondary" onClick={() => setErp({ is_enabled: c.erp.enabled, base_url: c.erp.base_url ?? "", timeout_seconds: c.erp.timeout_seconds, max_retries: c.erp.max_retries })}>Configure</Button> : undefined}>
            {erp ? (
              <form className="space-y-4 px-5 py-4" onSubmit={(e) => { e.preventDefault(); void saveErp(); }} data-erp-form>
                <Field label="ERP base URL" hint="HTTPS only. The credential is set on the server (ERP_HEADCOUNT_API_TOKEN), never here.">
                  {({ id: fid, describedBy }) => <TextInput id={fid} aria-describedby={describedBy} placeholder="https://erp.campus.example/api" value={erp.base_url} onChange={(e) => setErp({ ...erp, base_url: e.target.value })} />}
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Timeout (seconds)">{({ id: fid }) => <TextInput id={fid} type="number" min={1} max={120} value={erp.timeout_seconds} onChange={(e) => setErp({ ...erp, timeout_seconds: Number(e.target.value) })} />}</Field>
                  <Field label="Retries">{({ id: fid }) => <TextInput id={fid} type="number" min={0} max={5} value={erp.max_retries} onChange={(e) => setErp({ ...erp, max_retries: Number(e.target.value) })} />}</Field>
                </div>
                <Field label="Connection">{({ id: fid }) => (
                  <SelectInput id={fid} value={erp.is_enabled ? "on" : "off"} onChange={(e) => setErp({ ...erp, is_enabled: e.target.value === "on" })}>
                    <option value="off">Switched off</option><option value="on">Switched on</option>
                  </SelectInput>)}</Field>
                <div className="flex gap-2"><Button type="submit" size="sm" loading={busy}>Save</Button><Button type="button" size="sm" variant="secondary" onClick={() => setErp(null)}>Cancel</Button></div>
              </form>
            ) : (
              <div className="space-y-2 px-5 py-4 text-sm">
                <p><span className="text-slate-500">Status:</span> <span className="font-medium text-slate-900" data-erp-state>{c.erp.label}</span></p>
                <p><span className="text-slate-500">Base URL:</span> {c.erp.base_url ?? "not set"} · <span className="text-slate-500">Credential:</span> {c.erp.credential}</p>
                <p><span className="text-slate-500">Last sync:</span> {c.erp.last_sync_at ? `${formatDateTime(c.erp.last_sync_at)} (${c.erp.last_sync_status})` : "never"}</p>
                {c.erp.last_error && <p className="text-xs text-slate-500">{c.erp.last_error}</p>}
                <p className="text-xs text-slate-500">Manual headcount entry on meal records continues to work and remains the fallback.</p>
                <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={busy} onClick={syncNow}>Try a sync now</Button>
              </div>
            )}
          </Section>
        </div>
      </div>

      <Modal open={dialog === "edit"} onClose={() => !busy && setDialog(null)} title="Edit campus details" size="lg" dismissible={!busy}
        footer={<><Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>Cancel</Button>
          <Button loading={busy} disabled={!form || form.name.trim().length < 2} onClick={() => form && run(() => api.patch(`${PLATFORM_API}/campuses/${id}`, formBody(form)), "Campus details saved.")}>Save</Button></>}>
        {dialogError && <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">{dialogError}</p>}
        {form && <CampusFields form={form} setForm={setForm} withCode={false} />}
      </Modal>

      <Modal open={dialog === "deactivate"} onClose={() => !busy && setDialog(null)} title={`Deactivate ${c.name}?`} size="sm" dismissible={!busy}
        description="Its users are signed out and cannot sign in until the campus is activated again. Nothing is deleted: users, records, stock, bills, attachments and history are kept."
        footer={<><Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>Cancel</Button>
          <Button variant="danger" loading={busy} disabled={reason.trim().length < 3} onClick={() => run(() => api.post(`${PLATFORM_API}/campuses/${id}/deactivate`, { reason: reason.trim() }), "Campus deactivated.")}>Deactivate</Button></>}>
        {dialogError && <p className="mb-3 text-sm text-red-700" role="alert">{dialogError}</p>}
        <Field label="Reason" required>{({ id: fid }) => <TextArea id={fid} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} data-autofocus />}</Field>
      </Modal>

      <Modal open={dialog === "activate"} onClose={() => !busy && setDialog(null)} title={`Activate ${c.name}?`} size="sm" dismissible={!busy}
        description="Its users can sign in again and find everything as it was."
        footer={<><Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>Cancel</Button>
          <Button loading={busy} onClick={() => run(() => api.post(`${PLATFORM_API}/campuses/${id}/activate`), "Campus activated.")}>Activate</Button></>}>
        {dialogError ? <p className="text-sm text-red-700" role="alert">{dialogError}</p> : <span />}
      </Modal>

      <Modal open={dialog === "admin"} onClose={() => !busy && setDialog(null)} title="Invite the campus Admin" size="sm" dismissible={!busy}
        description="Creates the Admin account and emails a setup link. You never see or set the password. Nothing is saved if the email cannot be sent."
        footer={<><Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>Cancel</Button>
          <Button loading={busy} disabled={admin.full_name.trim().length < 2 || !admin.email.includes("@")} onClick={() => run(() => api.post(`${PLATFORM_API}/campuses/${id}/admins`, admin), "Setup link emailed.")}>Send setup link</Button></>}>
        {dialogError && <p className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">{dialogError}</p>}
        <div className="space-y-4">
          <Field label="Full name" required>{({ id: fid }) => <TextInput id={fid} value={admin.full_name} onChange={(e) => setAdmin({ ...admin, full_name: e.target.value })} data-autofocus />}</Field>
          <Field label="Email" required>{({ id: fid }) => <TextInput id={fid} type="email" value={admin.email} onChange={(e) => setAdmin({ ...admin, email: e.target.value })} />}</Field>
        </div>
      </Modal>
    </div>
  );
}
