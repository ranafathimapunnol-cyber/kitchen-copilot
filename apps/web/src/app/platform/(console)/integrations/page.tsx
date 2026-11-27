"use client";

import Link from "next/link";

import { formatDateTime } from "@/lib/payments";
import { PLATFORM_API, type ErpStatus } from "@/lib/platform";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { ActiveBadge, ErpBadge, PlatformHeader, Section, usePlatformGet } from "@/components/platform/parts";

type Row = ErpStatus & { campus_id: number; campus_name: string; campus_active: boolean; last_run: { status: string; error: string | null; started_at: string } | null };

/** Integration configuration and status per campus (ERP headcount). */
export default function IntegrationsPage() {
  const { data, error, reload } = usePlatformGet<{ credential: string; contract: string; items: Row[] }>(`${PLATFORM_API}/integrations`);
  return (
    <div className="space-y-6">
      <PlatformHeader eyebrow="Organisation" title="Integrations"
        description="The campus ERP headcount feed is prepared but not connected: the ERP API documentation and credentials have not been supplied. Manual headcount entry continues to work." />
      {error ? <ErrorState message={error} onRetry={reload} /> : !data ? <TableSkeleton rows={4} /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-3" data-integration-summary>
            <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs text-slate-500">API contract</p><p className="mt-1 font-semibold text-slate-900">Pending from the campus ERP team</p></div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs text-slate-500">Server credential (ERP_HEADCOUNT_API_TOKEN)</p><p className="mt-1 font-semibold text-slate-900">{data.credential === "set" ? "Set" : "Not set"}</p></div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs text-slate-500">Campuses configured</p><p className="mt-1 font-semibold text-slate-900">{data.items.filter((i) => i.state !== "NOT_CONFIGURED").length} of {data.items.length}</p></div>
          </div>
          <Section title="ERP headcount by campus" description="Configure a campus from its campus page.">
            <Table minWidth="760px">
              <THead><TR><TH>Campus</TH><TH>Status</TH><TH>Base URL</TH><TH>Last sync</TH><TH>Last attempt</TH></TR></THead>
              <TBody>{data.items.map((i) => (
                <TR key={i.campus_id}>
                  <TD><Link href={`/platform/campuses/${i.campus_id}`} className="font-semibold text-slate-900 hover:underline">{i.campus_name}</Link><span className="mt-1 block"><ActiveBadge active={i.campus_active} /></span></TD>
                  <TD><ErpBadge erp={i} /></TD>
                  <TD className="text-sm break-all">{i.base_url ?? "—"}</TD>
                  <TD className="text-sm">{i.last_sync_at ? `${formatDateTime(i.last_sync_at)} · ${i.last_sync_status}` : "Never"}</TD>
                  <TD className="text-xs text-slate-600">{i.last_run ? `${i.last_run.status.toLowerCase().replaceAll("_", " ")}${i.last_run.error ? `: ${i.last_run.error}` : ""}` : "—"}</TD>
                </TR>))}</TBody>
            </Table>
          </Section>
        </>
      )}
    </div>
  );
}
