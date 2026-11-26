"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Copy, History, KeyRound, LogOut, Pencil, Power, UserCog, UserPlus } from "lucide-react";

import { api } from "@/lib/api/client";
import { ADMIN_USERS_ENDPOINT } from "@/lib/api/endpoints";
import { formatRole } from "@/lib/navigation";
import { errorMessage, formatDateTime } from "@/lib/payments";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { Field, SelectInput, TextArea, TextInput } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import SearchInput from "@/components/ui/SearchInput";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

type Account = {
  id: number; full_name: string; email: string; role: string; is_active: boolean;
  last_login_at: string | null; sessions_revoked_at: string | null; failed_sign_ins_24h: number; active_grants: number;
};
type SignIn = { id: number; succeeded: boolean; ip_address: string | null; created_at: string };
type Dialog =
  | { kind: "edit"; account: Account }
  | { kind: "status"; account: Account }
  | { kind: "revoke"; account: Account }
  | { kind: "link"; account: Account; link?: string; minutes?: number }
  | { kind: "history"; account: Account; rows?: SignIn[]; error?: string }
  | null;

/** Stage 10: campus user accounts (ADMIN only). STAFF permissions stay on Staff Management. */
export default function UsersPage() {
  const toast = useToast();
  const [items, setItems] = useState<Account[] | null>(null);
  const [selfId, setSelfId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [reload, setReload] = useState(0);
  const [loadedKey, setLoadedKey] = useState("");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [newRole, setNewRole] = useState("");
  const [reason, setReason] = useState("");

  const params = new URLSearchParams();
  if (search.trim()) params.set("search", search.trim());
  if (role) params.set("role", role);
  if (status) params.set("status", status);
  const url = `${ADMIN_USERS_ENDPOINT}?${params}`;
  const key = `${url}#${reload}`;
  const loading = loadedKey !== key;

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      api.get<{ items: Account[]; self_id: number }>(url)
        .then((r) => { if (active) { setItems(r.items); setSelfId(r.self_id); setError(""); } })
        .catch((err: unknown) => { if (active) setError(errorMessage(err, "Unable to load the accounts.")); })
        .finally(() => active && setLoadedKey(key));
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [url, key]);

  function open(next: Dialog) {
    setDialog(next);
    if (next?.kind === "edit") { setName(next.account.full_name); setNewRole(next.account.role); }
    if (next?.kind === "status") setReason("");
    if (next?.kind === "history") {
      api.get<{ items: SignIn[] }>(`${ADMIN_USERS_ENDPOINT}/${next.account.id}/sign-ins`)
        .then((r) => setDialog({ ...next, rows: r.items }))
        .catch((err: unknown) => setDialog({ ...next, rows: [], error: errorMessage(err, "Unable to load the history.") }));
    }
  }

  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true);
    try {
      await action();
      toast.success(done);
      setDialog(null);
      setReload((n) => n + 1);
    } catch (err) {
      toast.error(errorMessage(err, "The change could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  async function makeLink(account: Account) {
    setBusy(true);
    try {
      const r = await api.post<{ link: string; expires_in_minutes: number }>(`${ADMIN_USERS_ENDPOINT}/${account.id}/reset-link`);
      setDialog({ kind: "link", account, link: r.link, minutes: r.expires_in_minutes });
    } catch (err) {
      toast.error(errorMessage(err, "The reset link could not be created."));
    } finally {
      setBusy(false);
    }
  }

  const isSelf = (a: Account) => a.id === selfId;
  const editable = dialog?.kind === "edit" && !isSelf(dialog.account) && dialog.account.role !== "ADMIN";

  return (
    <div className="space-y-6">
      <PageHeader
        icon={UserCog}
        eyebrow="Administration"
        title="User Accounts"
        description="Accounts on your campus: names, roles, access status and sign-in security. Permissions for Staff are set on Staff Management."
        actions={<Link href="/dashboard/staff"><Button variant="secondary" icon={<UserPlus size={16} />}>Create or assign access</Button></Link>}
      />

      <Card className="p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_180px_180px]">
          <SearchInput label="Search accounts" value={search} onChange={setSearch} placeholder="Search name or email" />
          <SelectInput aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">All roles</option>
            <option value="ADMIN">Admin</option>
            <option value="KITCHEN_MANAGER">Kitchen Manager</option>
            <option value="STAFF">Staff</option>
          </SelectInput>
          <SelectInput aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Active and inactive</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </SelectInput>
        </div>
      </Card>

      {error ? (
        <ErrorState message={error} onRetry={() => setReload((n) => n + 1)} />
      ) : items === null ? (
        <TableSkeleton rows={5} />
      ) : items.length === 0 ? (
        <EmptyState title="No accounts match" description="Change the search or filters." />
      ) : (
        <Card className={loading ? "opacity-60" : undefined} data-users>
          <Table>
            <THead>
              <TR>
                <TH>Person</TH><TH>Role</TH><TH>Status</TH><TH>Last sign-in</TH><TH>Security</TH><TH className="text-right">Actions</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((a) => (
                <TR key={a.id}>
                  <TD>
                    <p className="font-medium text-slate-900">{a.full_name}{isSelf(a) && <span className="ml-2 text-xs text-slate-500">(you)</span>}</p>
                    <p className="text-xs text-slate-500">{a.email}</p>
                  </TD>
                  <TD><Badge tone={a.role === "ADMIN" ? "brand" : "neutral"}>{formatRole(a.role)}</Badge>
                    {a.role === "STAFF" && <p className="mt-1 text-xs text-slate-500">{a.active_grants} permission{a.active_grants === 1 ? "" : "s"}</p>}
                  </TD>
                  <TD><Badge tone={a.is_active ? "success" : "danger"} dot>{a.is_active ? "Active" : "Inactive"}</Badge></TD>
                  <TD className="whitespace-nowrap text-sm text-slate-600">{a.last_login_at ? formatDateTime(a.last_login_at) : "Never"}</TD>
                  <TD className="text-sm">
                    {a.failed_sign_ins_24h > 0
                      ? <Badge tone={a.failed_sign_ins_24h >= 5 ? "danger" : "warning"}>{a.failed_sign_ins_24h} failed in 24 h</Badge>
                      : <span className="text-slate-500">No failed sign-ins</span>}
                  </TD>
                  <TD>
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <Button size="sm" variant="ghost" icon={<Pencil size={14} />} onClick={() => open({ kind: "edit", account: a })}>Edit</Button>
                      <Button size="sm" variant="ghost" icon={<History size={14} />} onClick={() => open({ kind: "history", account: a })}>Sign-ins</Button>
                      {a.is_active && <Button size="sm" variant="ghost" icon={<KeyRound size={14} />} loading={busy && dialog === null} onClick={() => makeLink(a)}>Reset link</Button>}
                      {a.is_active && <Button size="sm" variant="ghost" icon={<LogOut size={14} />} onClick={() => open({ kind: "revoke", account: a })}>Sign out</Button>}
                      {!isSelf(a) && (
                        <Button size="sm" variant={a.is_active ? "danger" : "secondary"} icon={<Power size={14} />} onClick={() => open({ kind: "status", account: a })}>
                          {a.is_active ? "Deactivate" : "Reactivate"}
                        </Button>
                      )}
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      )}

      <Modal
        open={dialog?.kind === "edit"}
        onClose={() => setDialog(null)}
        title="Edit account"
        description={dialog?.kind === "edit" ? dialog.account.email : undefined}
        footer={<>
          <Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>Cancel</Button>
          <Button loading={busy} disabled={name.trim().length < 2} onClick={() => dialog?.kind === "edit" && run(
            () => api.patch(`${ADMIN_USERS_ENDPOINT}/${dialog.account.id}`, { full_name: name.trim(), ...(editable && newRole !== dialog.account.role ? { role: newRole } : {}) }),
            "Account updated.")}>Save</Button>
        </>}
      >
        <div className="space-y-4">
          <Field label="Full name" required>{({ id }) => <TextInput id={id} value={name} onChange={(e) => setName(e.target.value)} data-autofocus />}</Field>
          <Field label="Role" hint={editable ? "Changing the role signs the person out of every device." : "Your own role and Admin roles are not changed here."}>
            {({ id }) => (
              <SelectInput id={id} value={newRole} disabled={!editable} onChange={(e) => setNewRole(e.target.value)}>
                {dialog?.kind === "edit" && dialog.account.role === "ADMIN" && <option value="ADMIN">Admin</option>}
                <option value="KITCHEN_MANAGER">Kitchen Manager</option>
                <option value="STAFF">Staff</option>
              </SelectInput>
            )}
          </Field>
        </div>
      </Modal>

      <Modal
        open={dialog?.kind === "status"}
        onClose={() => setDialog(null)}
        size="sm"
        title={dialog?.kind === "status" && dialog.account.is_active ? "Deactivate account" : "Reactivate account"}
        description={dialog?.kind === "status" ? `${dialog.account.full_name} · ${dialog.account.email}` : undefined}
        footer={<>
          <Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>Cancel</Button>
          <Button variant={dialog?.kind === "status" && dialog.account.is_active ? "danger" : "primary"} loading={busy}
            disabled={reason.trim().length < 3}
            onClick={() => dialog?.kind === "status" && run(
              () => api.post(`${ADMIN_USERS_ENDPOINT}/${dialog.account.id}/${dialog.account.is_active ? "deactivate" : "reactivate"}`, { reason: reason.trim() }),
              dialog.account.is_active ? "Account deactivated and signed out." : "Account reactivated.")}>
            {dialog?.kind === "status" && dialog.account.is_active ? "Deactivate" : "Reactivate"}
          </Button>
        </>}
      >
        <Field label="Reason" required hint="Kept in the audit log.">
          {({ id }) => <TextArea id={id} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} data-autofocus />}
        </Field>
      </Modal>

      <ConfirmDialog
        open={dialog?.kind === "revoke"}
        tone="warning"
        title="Sign out of every device?"
        description={dialog?.kind === "revoke" ? `${dialog.account.full_name} will need to sign in again everywhere.` : ""}
        confirmLabel="Sign out everywhere"
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={() => dialog?.kind === "revoke" && run(() => api.post(`${ADMIN_USERS_ENDPOINT}/${dialog.account.id}/revoke-sessions`), "Signed out of every device.")}
      />

      <Modal open={dialog?.kind === "link"} onClose={() => setDialog(null)} size="sm" title="Password reset link"
        description={dialog?.kind === "link" ? `For ${dialog.account.full_name}` : undefined}
        footer={<Button onClick={() => setDialog(null)}>Done</Button>}>
        {dialog?.kind === "link" && dialog.link && (
          <div className="space-y-3 text-sm">
            <p className="text-slate-600">Give this link to the person directly. It works once and expires in {dialog.minutes} minutes. Their password is never shown to anyone.</p>
            <p className="break-all rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs select-all" data-reset-link>{dialog.link}</p>
            <Button variant="secondary" size="sm" icon={<Copy size={14} />} onClick={() => {
              navigator.clipboard.writeText(dialog.link ?? "").then(() => toast.success("Link copied."), () => toast.error("Copy failed; select the link instead."));
            }}>Copy link</Button>
          </div>
        )}
      </Modal>

      <Modal open={dialog?.kind === "history"} onClose={() => setDialog(null)} title="Recent sign-ins"
        description={dialog?.kind === "history" ? dialog.account.email : undefined}
        footer={<Button variant="secondary" onClick={() => setDialog(null)}>Close</Button>}>
        {dialog?.kind === "history" && (
          dialog.rows === undefined ? <TableSkeleton rows={3} /> :
          dialog.error ? <p className="text-sm text-red-600">{dialog.error}</p> :
          dialog.rows.length === 0 ? <p className="text-sm text-slate-500">No sign-in attempts recorded yet.</p> : (
            <ul className="divide-y divide-slate-100 text-sm">
              {dialog.rows.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-3 py-2">
                  <span>{formatDateTime(r.created_at)}</span>
                  <span className="text-xs text-slate-500">{r.ip_address ?? "—"}</span>
                  <Badge tone={r.succeeded ? "success" : "danger"}>{r.succeeded ? "Signed in" : "Failed"}</Badge>
                </li>
              ))}
            </ul>
          )
        )}
      </Modal>
    </div>
  );
}
