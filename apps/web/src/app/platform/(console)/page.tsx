"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, Building2, IndianRupee, PackageX, PlugZap, Users } from "lucide-react";

import { PLATFORM_API, auditSentence, money, monthToDate, n, query, type Overview, type Period } from "@/lib/platform";
import { formatDateTime } from "@/lib/payments";
import Badge from "@/components/ui/Badge";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { ActiveBadge, ErpBadge, Kpi, PeriodFilter, PlatformHeader, Section, usePlatformGet } from "@/components/platform/parts";

const ALERT_TONE = { critical: "danger", warning: "warning", info: "neutral" } as const;

/** Organisation overview: every figure is read from the database for the chosen period. */
export default function PlatformOverviewPage() {
  const [period, setPeriod] = useState<Period>(monthToDate());
  const [campusId, setCampusId] = useState("");
  const { data, error, loading, reload } = usePlatformGet<Overview>(
    `${PLATFORM_API}/overview${query({ ...period, campus_id: campusId })}`);
  const { data: all } = usePlatformGet<{ items: { id: number; name: string }[] }>(`${PLATFORM_API}/campuses`);
  const names = Object.fromEntries((all?.items ?? []).map((c) => [c.id, c.name]));

  return (
    <div className="space-y-6">
      <PlatformHeader eyebrow="Organisation" title="Organisation overview"
        description="Campus totals, purchases, stock and the things that need a platform administrator's attention. Figures are campus aggregates; campus records stay with each campus." />
      <PeriodFilter value={period} onChange={setPeriod} campuses={all?.items} campusId={campusId} onCampusChange={setCampusId} />

      {error ? <ErrorState message={error} onRetry={reload} /> : !data ? <TableSkeleton rows={5} /> : (
        <div className={loading ? "space-y-6 opacity-60 transition-opacity" : "space-y-6"} data-overview>
          <div className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 xl:grid-cols-4">
            <Kpi label="Campuses" value={n(data.totals.campuses)} icon={Building2}
              note={`${n(data.totals.active_campuses)} active · ${n(data.totals.inactive_campuses)} deactivated`} />
            <Kpi label="Campus users" value={n(data.totals.users)} icon={Users}
              note={`${n(data.totals.active_users)} active · ${n(data.totals.admins)} Admins`} />
            <Kpi label="Purchases in period" value={money(data.totals.purchases_total)} icon={IndianRupee} tone="accent"
              note={`${n(data.totals.bills)} bills · ${money(data.totals.outstanding_payables)} outstanding now`} />
            <Kpi label="Items below minimum" value={n(data.totals.items_below_minimum)} icon={PackageX}
              tone={data.totals.items_below_minimum ? "warning" : "neutral"} note={`${n(data.totals.items_out_of_stock)} out of stock`} />
          </div>

          <Section title="Campuses" description={`Purchases ${data.period.date_from} to ${data.period.date_to}; stock and payables as of now.`}
              action={<Link href="/platform/campuses" className="text-sm font-medium text-slate-900 underline">Manage campuses</Link>}>
              {data.campuses.length === 0 ? <EmptyState compact icon={Building2} title="No campuses" description="Register the first campus on the Campuses screen." /> : (
                <Table minWidth="860px">
                  <THead><TR><TH>Campus</TH><TH>Status</TH><TH className="text-right">Users</TH><TH className="text-right">Purchases</TH><TH className="text-right">Below min.</TH><TH className="text-right">Payables</TH><TH>ERP</TH></TR></THead>
                  <TBody>
                    {data.campuses.map((c) => (
                      <TR key={c.id}>
                        <TD><Link href={`/platform/campuses/${c.id}`} className="font-semibold text-slate-900 hover:underline">{c.name}</Link><span className="block text-xs text-slate-500">{c.code}{c.organization_name ? ` · ${c.organization_name}` : ""}</span></TD>
                        <TD><ActiveBadge active={c.is_active} /></TD>
                        <TD className="text-right tabular-nums">{n(c.users.active)}</TD>
                        <TD className="text-right tabular-nums">{money(c.purchases.total)}<span className="block text-xs text-slate-500">{n(c.purchases.bill_count)} bills</span></TD>
                        <TD className="text-right tabular-nums">{n(c.operations.stock.below_minimum)}</TD>
                        <TD className="text-right tabular-nums">{money(c.operations.outstanding_payables)}</TD>
                        <TD><ErpBadge erp={c.erp} /></TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              )}
            </Section>

          <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
              <Section title="Alerts and unresolved issues" description="Worst first.">
                {data.alerts.length === 0 ? <p className="px-5 py-6 text-sm text-slate-500">Nothing needs attention.</p> : (
                  <ul className="divide-y divide-slate-100" data-alerts>
                    {data.alerts.map((a, i) => (
                      <li key={i} className="flex items-start gap-3 px-5 py-3 text-sm">
                        <AlertTriangle size={15} aria-hidden className={a.level === "critical" ? "mt-0.5 text-red-600" : a.level === "warning" ? "mt-0.5 text-amber-600" : "mt-0.5 text-slate-400"} />
                        <span className="min-w-0 flex-1"><Link href={`/platform/campuses/${a.campus_id}`} className="font-medium text-slate-900 hover:underline">{a.campus_name}</Link> — {a.text}</span>
                        <Badge tone={ALERT_TONE[a.level]}>{a.level}</Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
              <Section title="Integrations" action={<Link href="/platform/integrations" className="text-sm font-medium text-slate-900 underline">Open</Link>}>
                <p className="flex items-center gap-2 px-5 py-4 text-sm text-slate-600"><PlugZap size={15} aria-hidden className="text-slate-400" />
                  ERP headcount: {data.totals.erp_configured ? `${data.totals.erp_configured} campus(es) configured; API contract pending.` : "ERP connection not configured."}</p>
              </Section>
              <Section title="Recent platform activity" action={<Link href="/platform/audit" className="text-sm font-medium text-slate-900 underline">Audit log</Link>}>
                {data.activity.length === 0 ? <p className="px-5 py-6 text-sm text-slate-500">No platform activity yet.</p> : (
                  <ul className="divide-y divide-slate-100 text-sm">
                    {data.activity.map((a) => (
                      <li key={a.id} className="px-5 py-2.5">
                        <p className="text-slate-800">{auditSentence(a, names)}</p>
                        <p className="text-xs text-slate-500">{a.actor_email ?? "unknown"} · {formatDateTime(a.occurred_at)}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
          </div>
          <p className="text-xs text-slate-500">Generated {formatDateTime(data.generated_at)} from the live database.</p>
        </div>
      )}
    </div>
  );
}
