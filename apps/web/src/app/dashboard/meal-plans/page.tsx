"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CalendarRange, Plus, X } from "lucide-react";

import { api } from "@/lib/api/client";
import { MEAL_PLANS_ENDPOINT } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime, formatDay } from "@/lib/payments";
import {
  PLAN_STATUSES,
  PLAN_STATUS_LABELS,
  PLAN_STATUS_TONES,
  type PlanListResponse,
  type PlanStatus,
} from "@/lib/planning";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type StatusFilter = "ALL" | PlanStatus;
const PAGE_SIZES = [20, 50, 100];

export default function MealPlansPage() {
  const [status, setStatus] = useState<StatusFilter>("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<PlanListResponse | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");

  const datesInvalid = Boolean(dateFrom && dateTo) && dateFrom > dateTo;
  const url = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status !== "ALL") params.set("status", status);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    return `${MEAL_PLANS_ENDPOINT}?${params}`;
  }, [page, pageSize, status, dateFrom, dateTo]);
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    if (datesInvalid) return;
    let active = true;
    api
      .get<PlanListResponse>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load meal plans."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });
    return () => {
      active = false;
    };
  }, [url, requestKey, datesInvalid]);

  const filtered = status !== "ALL" || Boolean(dateFrom || dateTo);

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Menu Planning"
        icon={CalendarRange}
        title="Meal Plans"
        description="Plan a meal from its menu and expected headcount: required quantity = headcount × the approved standard per person, with current stock and the quantity still to buy. A plan never changes stock or creates a purchase."
        actions={
          <Link href="/dashboard/meal-plans/new"
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700">
            <Plus size={16} aria-hidden />
            New meal plan
          </Link>
        }
      />

      <Card>
        <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 lg:flex-row lg:items-end lg:justify-between">
          <SegmentedControl<StatusFilter>
            label="Plan status"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={[
              { value: "ALL", label: "All" },
              ...PLAN_STATUSES.map((value) => ({ value, label: PLAN_STATUS_LABELS[value], count: data?.status_counts[value] })),
            ]}
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[repeat(2,minmax(0,10rem))_auto] sm:items-end">
            <Field label="From">
              {({ id }) => (
                <TextInput id={id} type="date" className="h-9" value={dateFrom} max={dateTo || undefined}
                  onChange={(event) => { setDateFrom(event.target.value); setPage(1); }} />
              )}
            </Field>
            <Field label="To" error={datesInvalid ? "Must be on or after From." : undefined}>
              {({ id }) => (
                <TextInput id={id} type="date" className="h-9" value={dateTo} min={dateFrom || undefined}
                  onChange={(event) => { setDateTo(event.target.value); setPage(1); }} />
              )}
            </Field>
            <Button variant="ghost" icon={<X size={15} aria-hidden />} disabled={!filtered}
              onClick={() => { setStatus("ALL"); setDateFrom(""); setDateTo(""); setPage(1); }}>
              Clear
            </Button>
          </div>
        </div>

        {error && !loading ? (
          <ErrorState title="Couldn't load meal plans" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : !data ? (
          <TableSkeleton rows={6} columns={6} />
        ) : data.items.length === 0 ? (
          <EmptyState icon={CalendarRange}
            title={filtered ? "No meal plans match these filters" : "No meal plans yet"}
            description={filtered ? "Try another status or date range." : "Plan a meal from a menu with approved portion standards."} />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="900px">
              <THead>
                <tr>
                  <TH>Plan</TH>
                  <TH>Meal</TH>
                  <TH>Menu</TH>
                  <TH align="right">Headcount</TH>
                  <TH align="right">Items</TH>
                  <TH>Status</TH>
                  <TH>Meal record</TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((plan) => (
                  <TR key={plan.id} muted={plan.status === "CANCELLED"}>
                    <TD className="whitespace-nowrap">
                      <Link href={`/dashboard/meal-plans/${plan.id}`} className="font-semibold text-brand-700 hover:underline">
                        {plan.plan_number}
                      </Link>
                      <div className="text-xs text-slate-500">by {plan.created_by_name ?? "—"}</div>
                    </TD>
                    <TD className="whitespace-nowrap">
                      {plan.meal_session_name}
                      <div className="text-xs text-slate-500">{formatDay(plan.plan_date)}</div>
                    </TD>
                    <TD>{plan.menu_name}</TD>
                    <TD align="right">{plan.expected_headcount}</TD>
                    <TD align="right">{plan.line_count}</TD>
                    <TD className="whitespace-nowrap">
                      <Badge tone={PLAN_STATUS_TONES[plan.status]} dot>{PLAN_STATUS_LABELS[plan.status]}</Badge>
                      {plan.approved_at && <div className="text-xs text-slate-500">{plan.approved_by_name} · {formatDateTime(plan.approved_at)}</div>}
                    </TD>
                    <TD>
                      {plan.meal_record_id ? (
                        <Link href={`/dashboard/meals/${plan.meal_record_id}`} className="text-brand-700 hover:underline">Meal record</Link>
                      ) : <span className="text-slate-400">—</span>}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination page={data.page} pageCount={data.total_pages} total={data.total} pageSize={data.page_size}
              noun="meal plans" onPageChange={setPage} pageSizeOptions={PAGE_SIZES}
              onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />
          </div>
        )}
      </Card>
    </div>
  );
}
