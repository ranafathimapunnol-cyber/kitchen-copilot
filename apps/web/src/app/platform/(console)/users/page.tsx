"use client";

import { useState } from "react";
import Link from "next/link";

import { formatDateTime } from "@/lib/payments";
import { PLATFORM_API, ROLE_LABELS, query, type PlatformUserRow } from "@/lib/platform";
import Badge from "@/components/ui/Badge";
import { Field, SelectInput } from "@/components/ui/Field";
import SearchInput from "@/components/ui/SearchInput";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { PlatformHeader, usePlatformGet } from "@/components/platform/parts";

/** Accounts across the organisation (read-only) and the platform accounts. */
export default function PlatformUsersPage() {
  const [scope, setScope] = useState<"campus" | "platform">("campus");
  const [campusId, setCampusId] = useState("");
  const [role, setRole] = useState("");
  const [search, setSearch] = useState("");
  const { data, error, reload } = usePlatformGet<{ items: PlatformUserRow[] }>(
    `${PLATFORM_API}/users${query(scope === "platform" ? { scope } : { scope, campus_id: campusId, role, q: search.trim() })}`);
  const { data: campuses } = usePlatformGet<{ items: { id: number; name: string }[] }>(`${PLATFORM_API}/campuses`);

  return (
    <div className="space-y-6">
      <PlatformHeader eyebrow="Organisation" title="Platform users"
        description="Campus accounts are managed by each campus's Admin; here they are read-only. Invite a campus's Admin from its campus page. Platform accounts are created by the operator, never by self-registration." />
      <div className="flex flex-wrap items-end gap-3">
        <SegmentedControl label="Accounts" value={scope} onChange={setScope} options={[{ value: "campus", label: "Campus accounts" }, { value: "platform", label: "Platform accounts" }]} />
        {scope === "campus" && <>
          <SearchInput label="Search users" value={search} onChange={setSearch} placeholder="Name or email" className="w-full sm:w-64" />
          <Field label="Campus" className="w-52">{({ id }) => (
            <SelectInput id={id} value={campusId} onChange={(e) => setCampusId(e.target.value)}>
              <option value="">All campuses</option>{campuses?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </SelectInput>)}</Field>
          <Field label="Role" className="w-44">{({ id }) => (
            <SelectInput id={id} value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="">All roles</option><option value="ADMIN">Admin</option><option value="KITCHEN_MANAGER">Kitchen Manager</option><option value="STAFF">Staff</option>
            </SelectInput>)}</Field>
        </>}
      </div>
      {error ? <ErrorState message={error} onRetry={reload} /> : !data ? <TableSkeleton rows={6} /> : data.items.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white"><EmptyState title="No accounts match" /></div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white" data-user-list>
          <Table minWidth="680px">
            <THead><TR><TH>Name</TH><TH>Role</TH><TH>Campus</TH><TH>Status</TH><TH>Last sign-in</TH></TR></THead>
            <TBody>{data.items.map((u) => (
              <TR key={u.id}>
                <TD><span className="font-medium text-slate-900">{u.full_name}</span><span className="block text-xs text-slate-500">{u.email}</span></TD>
                <TD>{ROLE_LABELS[u.role] ?? u.role}</TD>
                <TD>{u.campus_id ? <Link href={`/platform/campuses/${u.campus_id}`} className="hover:underline">{u.campus_name}</Link> : "Organisation"}</TD>
                <TD><Badge tone={u.is_active ? "success" : "neutral"} dot>{u.is_active ? "Active" : "Inactive"}</Badge></TD>
                <TD className="text-sm text-slate-600">{formatDateTime(u.last_login_at)}</TD>
              </TR>))}</TBody>
          </Table>
        </div>
      )}
    </div>
  );
}
