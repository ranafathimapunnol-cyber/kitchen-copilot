"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Building2, Plus } from "lucide-react";

import { api } from "@/lib/api/client";
import { errorMessage, formatDateTime } from "@/lib/payments";
import { PLATFORM_API, mediaPath, n, query, type CampusDetail } from "@/lib/platform";
import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import SearchInput from "@/components/ui/SearchInput";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { apiUrl } from "@/lib/api/client";
import { ActiveBadge, ErpBadge, PlatformHeader, usePlatformGet } from "@/components/platform/parts";
import { CampusFields, EMPTY_FORM, formBody, type CampusForm } from "@/components/platform/CampusForm";

/** Campuses of the organisation: register, search, filter by status. */
export default function CampusesPage() {
  const router = useRouter();
  const toast = useToast();
  const [status, setStatus] = useState<"all" | "active" | "inactive">("all");
  const [search, setSearch] = useState("");
  const { data, error, reload } = usePlatformGet<{ items: CampusDetail[] }>(`${PLATFORM_API}/campuses${query({ status, q: search.trim() })}`);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<CampusForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  async function register() {
    setSaving(true);
    setFormError("");
    try {
      const created = await api.post<CampusDetail>(`${PLATFORM_API}/campuses`, { ...formBody(form), code: form.code.trim() });
      toast.success(`${created.name} registered.`);
      setOpen(false);
      router.push(`/platform/campuses/${created.id}`);
    } catch (err) {
      setFormError(errorMessage(err, "The campus could not be registered."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <PlatformHeader eyebrow="Organisation" title="Campuses"
        description="Every campus keeps its own users and records. Deactivating a campus stops its users signing in; nothing is deleted."
        actions={<Button icon={<Plus size={16} />} onClick={() => { setForm(EMPTY_FORM); setFormError(""); setOpen(true); }}>Register campus</Button>} />
      <div className="flex flex-wrap items-center gap-3">
        <SearchInput label="Search campuses" value={search} onChange={setSearch} placeholder="Name or code" className="w-full sm:w-72" />
        <SegmentedControl label="Status" value={status} onChange={setStatus}
          options={[{ value: "all", label: "All" }, { value: "active", label: "Active" }, { value: "inactive", label: "Deactivated" }]} />
      </div>
      {error ? <ErrorState message={error} onRetry={reload} /> : !data ? <TableSkeleton rows={4} /> : data.items.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white"><EmptyState icon={Building2} title="No campuses match" description="Change the filters or register a campus." /></div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white" data-campus-list>
          <Table minWidth="760px">
            <THead><TR><TH>Campus</TH><TH>Status</TH><TH className="text-right">Active users</TH><TH className="text-right">Admins</TH><TH>ERP headcount</TH><TH>Last campus activity</TH></TR></THead>
            <TBody>
              {data.items.map((c) => (
                <TR key={c.id}>
                  <TD>
                    <div className="flex items-center gap-3">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-100">
                        {c.media?.logo
                          ? /* eslint-disable-next-line @next/next/no-img-element -- authenticated API image */
                            <img onError={(e) => { e.currentTarget.hidden = true; }} src={apiUrl(mediaPath(c.id, "logo", c.media.logo))} alt="" className="h-full w-full object-contain p-1" />
                          : <Building2 size={16} aria-hidden className="text-slate-400" />}
                      </span>
                      <span className="min-w-0"><Link href={`/platform/campuses/${c.id}`} className="font-semibold text-slate-900 hover:underline">{c.name}</Link><span className="block text-xs text-slate-500">{c.code}{c.organization_name ? ` · ${c.organization_name}` : ""}</span></span>
                    </div>
                  </TD>
                  <TD><ActiveBadge active={c.is_active} /></TD>
                  <TD className="text-right tabular-nums">{n(c.users.active)}</TD>
                  <TD className="text-right tabular-nums">{c.users.ADMIN === 0 && c.is_active ? <span className="font-semibold text-red-700">0</span> : n(c.users.ADMIN)}</TD>
                  <TD><ErpBadge erp={c.erp} /></TD>
                  <TD className="text-sm text-slate-600">{formatDateTime(c.last_activity_at)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
      )}

      <Modal open={open} onClose={() => !saving && setOpen(false)} title="Register a campus" size="lg" dismissible={!saving}
        description="The campus starts active with no users. Invite its first Admin from the campus page."
        footer={<><Button variant="secondary" onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
          <Button loading={saving} disabled={form.name.trim().length < 2 || !/^[A-Za-z0-9_-]{2,30}$/.test(form.code.trim())} onClick={register}>Register campus</Button></>}>
        {formError && <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">{formError}</p>}
        <CampusFields form={form} setForm={setForm} withCode />
      </Modal>
    </div>
  );
}
