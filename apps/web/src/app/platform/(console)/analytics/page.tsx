"use client";

import { useState } from "react";

import { PLATFORM_API, money, monthToDate, n, query, type Period } from "@/lib/platform";
import BarList from "@/components/charts/BarList";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { Kpi, PeriodFilter, PlatformHeader, Section, usePlatformGet } from "@/components/platform/parts";

type Analytics = {
  period: Period;
  campuses: { id: number; name: string; code: string; is_active: boolean; bill_count: number; total: string }[];
  monthly: { campus_id: number; month: string; bill_count: number; total: string }[];
};

/** Purchases across campuses for a period, from supplier bills. */
export default function AnalyticsPage() {
  const [period, setPeriod] = useState<Period>(() => {
    const p = monthToDate();
    const d = new Date();
    d.setMonth(d.getMonth() - 5, 1);
    return { ...p, date_from: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01` };
  });
  const [campusId, setCampusId] = useState("");
  const { data, error, reload } = usePlatformGet<Analytics>(`${PLATFORM_API}/analytics${query({ ...period, campus_id: campusId })}`);
  const { data: all } = usePlatformGet<{ items: { id: number; name: string }[] }>(`${PLATFORM_API}/campuses`);

  const total = data ? data.campuses.reduce((s, c) => s + Number(c.total), 0) : 0;
  const bills = data ? data.campuses.reduce((s, c) => s + c.bill_count, 0) : 0;
  const months = data ? [...new Set(data.monthly.map((m) => m.month))] : [];
  const names = Object.fromEntries((data?.campuses ?? []).map((c) => [c.id, c.name]));

  return (
    <div className="space-y-6">
      <PlatformHeader eyebrow="Organisation" title="Organisation analytics"
        description="Purchase spending by campus and month, from supplier bills (grand totals, by bill date)." />
      <PeriodFilter value={period} onChange={setPeriod} campuses={all?.items} campusId={campusId} onCampusChange={setCampusId} />
      {error ? <ErrorState message={error} onRetry={reload} /> : !data ? <TableSkeleton rows={5} /> : (
        <>
          <div className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-3">
            <Kpi label="Purchases in period" value={money(total)} tone="accent" />
            <Kpi label="Supplier bills" value={n(bills)} />
            <Kpi label="Average per bill" value={bills ? money(total / bills) : "—"} />
          </div>
          <div className="grid gap-6 xl:grid-cols-2">
            <Section title="By campus" description={`${data.period.date_from} to ${data.period.date_to}`}>
              {total === 0 ? <EmptyState compact title="No purchases in this period" /> : (
                <div className="px-5 py-4" data-analytics-bars>
                  <BarList color="var(--color-chart-1)" measureLabel="Purchases"
                    rows={[...data.campuses].sort((a, b) => Number(b.total) - Number(a.total)).map((c) => ({
                      id: c.id, label: c.name, meta: `${n(c.bill_count)} bills${c.is_active ? "" : " · deactivated"}`,
                      value: Number(c.total), display: money(c.total) }))} />
                </div>
              )}
            </Section>
            <Section title="By month">
              {months.length === 0 ? <EmptyState compact title="No purchases in this period" /> : (
                <Table minWidth="480px">
                  <THead><TR><TH>Month</TH><TH>Campus</TH><TH className="text-right">Bills</TH><TH className="text-right">Purchases</TH></TR></THead>
                  <TBody>{data.monthly.map((m) => (
                    <TR key={`${m.month}-${m.campus_id}`}><TD>{m.month}</TD><TD>{names[m.campus_id]}</TD>
                      <TD className="text-right tabular-nums">{n(m.bill_count)}</TD><TD className="text-right tabular-nums">{money(m.total)}</TD></TR>
                  ))}</TBody>
                </Table>
              )}
            </Section>
          </div>
        </>
      )}
    </div>
  );
}
