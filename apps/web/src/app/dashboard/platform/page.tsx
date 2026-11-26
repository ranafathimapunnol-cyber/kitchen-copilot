"use client";

import { useEffect, useState } from "react";
import { Building2, Pencil, Plus, UserPlus } from "lucide-react";

import { api } from "@/lib/api/client";
import { PLATFORM_ENDPOINT } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime } from "@/lib/payments";
import Badge, { humanize } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

type Org = { id: number; name: string; code: string; is_active: boolean; campus_count: number; created_at: string };
type CampusRow = {
  id: number; name: string; code: string; is_active: boolean; organization_id: number | null;
  organization_name: string | null; active_admins: number; active_users: number;
  admins: { id: number; full_name: string; email: string; is_active: boolean }[];
};
type Overview = {
  organizations: Org[]; campuses: CampusRow[];
  activity: { id: number; created_at: string; action: string; entity_type: string; entity_id: number | null; user_name: string }[];
};
type Form =
  | { kind: "org"; id?: number; name: string; code: string; is_active: boolean }
  | { kind: "campus"; id?: number; name: string; code: string; is_active: boolean; organization_id: string }
  | { kind: "admin"; campus: CampusRow; full_name: string; email: string }
  | null;

/** Stage 11: organisations, campuses and each campus's first Admin (SUPER_ADMIN only). */
export default function PlatformPage() {
  const toast = useToast();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [form, setForm] = useState<Form>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    api.get<Overview>(`${PLATFORM_ENDPOINT}/overview`)
      .then((r) => { if (active) { setData(r); setError(""); } })
      .catch((err: unknown) => { if (active) setError(errorMessage(err, "Unable to load the platform overview.")); });
    return () => { active = false; };
  }, [reload]);

  async function save() {
    if (!form) return;
    setSaving(true);
    try {
      if (form.kind === "org") {
        const body = { name: form.name.trim(), code: form.code.trim(), is_active: form.is_active };
        await (form.id ? api.put(`${PLATFORM_ENDPOINT}/organizations/${form.id}`, body) : api.post(`${PLATFORM_ENDPOINT}/organizations`, body));
        toast.success(form.id ? "Organisation updated." : "Organisation created.");
      } else if (form.kind === "campus") {
        const body = { name: form.name.trim(), code: form.code.trim(), is_active: form.is_active,
          organization_id: form.organization_id ? Number(form.organization_id) : null };
        await (form.id ? api.put(`${PLATFORM_ENDPOINT}/campuses/${form.id}`, body) : api.post(`${PLATFORM_ENDPOINT}/campuses`, body));
        toast.success(form.id ? "Campus updated." : "Campus created.");
      } else {
        const r = await api.post<{ message: string }>(`${PLATFORM_ENDPOINT}/campuses/${form.campus.id}/admins`,
          { full_name: form.full_name.trim(), email: form.email.trim() });
        toast.success(r.message);
      }
      setForm(null);
      setReload((n) => n + 1);
    } catch (err) {
      toast.error(errorMessage(err, "The change could not be saved."));
    } finally {
      setSaving(false);
    }
  }

  const valid = form && (form.kind === "admin"
    ? form.full_name.trim().length >= 2 && /.+@.+\..+/.test(form.email)
    : form.name.trim().length >= 2 && /^[A-Za-z0-9_-]+$/.test(form.code));

  return (
    <div className="space-y-6">
      <PageHeader icon={Building2} eyebrow="Platform" title="Organisations & Campuses"
        description="Create organisations and campuses and invite each campus's first Admin. Campus records and campus users are managed by that campus's Admin, not here."
        actions={<>
          <Button variant="secondary" icon={<Plus size={16} />} onClick={() => setForm({ kind: "org", name: "", code: "", is_active: true })}>Organisation</Button>
          <Button icon={<Plus size={16} />} onClick={() => setForm({ kind: "campus", name: "", code: "", is_active: true, organization_id: "" })}>Campus</Button>
        </>} />

      {error ? <ErrorState message={error} onRetry={() => setReload((n) => n + 1)} /> : !data ? <TableSkeleton rows={5} /> : (
        <>
          <Card data-campuses>
            <CardHeader title="Campuses" subtitle={`${data.campuses.length} campus${data.campuses.length === 1 ? "" : "es"}`} />
            {data.campuses.length === 0 ? <EmptyState compact title="No campuses yet" /> : (
              <Table minWidth="760px">
                <THead><TR><TH>Campus</TH><TH>Organisation</TH><TH>Status</TH><TH>Admins</TH><TH align="right">Active users</TH><TH align="right">Actions</TH></TR></THead>
                <TBody>
                  {data.campuses.map((c) => (
                    <TR key={c.id}>
                      <TD><p className="font-medium text-slate-900">{c.name}</p><p className="text-xs text-slate-500">{c.code}</p></TD>
                      <TD className="text-sm">{c.organization_name ?? <span className="text-slate-400">Not assigned</span>}</TD>
                      <TD><Badge tone={c.is_active ? "success" : "neutral"} dot>{c.is_active ? "Active" : "Inactive"}</Badge></TD>
                      <TD className="text-sm">
                        {c.admins.length === 0 ? <Badge tone="warning">No Admin yet</Badge> :
                          c.admins.map((a) => <p key={a.id} className={a.is_active ? "" : "text-slate-400 line-through"}>{a.full_name} <span className="text-xs text-slate-500">{a.email}</span></p>)}
                      </TD>
                      <TD align="right">{c.active_users}</TD>
                      <TD align="right">
                        <div className="flex flex-wrap justify-end gap-1.5">
                          <Button size="sm" variant="ghost" icon={<Pencil size={14} />} onClick={() => setForm({ kind: "campus", id: c.id, name: c.name, code: c.code, is_active: c.is_active, organization_id: c.organization_id ? String(c.organization_id) : "" })}>Edit</Button>
                          {c.is_active && <Button size="sm" variant="ghost" icon={<UserPlus size={14} />} onClick={() => setForm({ kind: "admin", campus: c, full_name: "", email: "" })}>Invite Admin</Button>}
                        </div>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Organisations" />
              {data.organizations.length === 0 ? <EmptyState compact title="No organisations yet" description="Campuses can exist without one." /> : (
                <Table>
                  <THead><TR><TH>Name</TH><TH align="right">Campuses</TH><TH>Status</TH><TH align="right"><span className="sr-only">Actions</span></TH></TR></THead>
                  <TBody>
                    {data.organizations.map((o) => (
                      <TR key={o.id}>
                        <TD><p className="font-medium">{o.name}</p><p className="text-xs text-slate-500">{o.code}</p></TD>
                        <TD align="right">{o.campus_count}</TD>
                        <TD><Badge tone={o.is_active ? "success" : "neutral"} dot>{o.is_active ? "Active" : "Inactive"}</Badge></TD>
                        <TD align="right"><Button size="sm" variant="ghost" icon={<Pencil size={14} />} onClick={() => setForm({ kind: "org", id: o.id, name: o.name, code: o.code, is_active: o.is_active })}>Edit</Button></TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              )}
            </Card>
            <Card>
              <CardHeader title="Recent platform activity" />
              {data.activity.length === 0 ? <EmptyState compact title="Nothing yet" /> : (
                <ul className="divide-y divide-slate-100 px-5 text-sm">
                  {data.activity.map((a) => (
                    <li key={a.id} className="flex flex-wrap justify-between gap-2 py-2">
                      <span>{humanize(a.action)} {humanize(a.entity_type).toLowerCase()} {a.entity_id ? `#${a.entity_id}` : ""} · {a.user_name}</span>
                      <span className="text-xs text-slate-500">{formatDateTime(a.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}

      <Modal open={form !== null} onClose={() => !saving && setForm(null)} size="sm"
        title={form?.kind === "admin" ? `Invite the Admin of ${form.campus.name}` : `${form && "id" in form && form.id ? "Edit" : "New"} ${form?.kind === "org" ? "organisation" : "campus"}`}
        description={form?.kind === "admin" ? "They receive an email with a link to set their own password. Nothing is saved if the email cannot be sent." : undefined}
        footer={<>
          <Button variant="secondary" onClick={() => setForm(null)} disabled={saving}>Cancel</Button>
          <Button loading={saving} disabled={!valid} onClick={save}>{form?.kind === "admin" ? "Send invitation" : "Save"}</Button>
        </>}>
        {form && (form.kind === "admin" ? (
          <div className="space-y-4">
            <Field label="Full name" required>{({ id }) => <TextInput id={id} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} data-autofocus />}</Field>
            <Field label="Email" required>{({ id }) => <TextInput id={id} type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}</Field>
          </div>
        ) : (
          <div className="space-y-4">
            <Field label="Name" required>{({ id }) => <TextInput id={id} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-autofocus />}</Field>
            <Field label="Code" required hint="Letters, digits, - or _. Stored in capitals.">{({ id }) => <TextInput id={id} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />}</Field>
            {form.kind === "campus" && (
              <Field label="Organisation">{({ id }) => (
                <SelectInput id={id} value={form.organization_id} onChange={(e) => setForm({ ...form, organization_id: e.target.value })}>
                  <option value="">Not assigned</option>
                  {data?.organizations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </SelectInput>)}
              </Field>
            )}
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Active
            </label>
          </div>
        ))}
      </Modal>
    </div>
  );
}
