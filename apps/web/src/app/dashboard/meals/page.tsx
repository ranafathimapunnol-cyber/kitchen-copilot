"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Plus, UtensilsCrossed, X } from "lucide-react";

import { api } from "@/lib/api/client";
import { MEAL_RECORDS_ENDPOINT } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime, formatDay } from "@/lib/payments";
import {
  MEAL_STATUSES,
  MEAL_STATUS_LABELS,
  MEAL_STATUS_TONES,
  canCreateMeals,
  type MealListResponse,
  type MealStatus,
} from "@/lib/meals";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type StatusFilter = "ALL" | MealStatus;
const PAGE_SIZES = [20, 50, 100];

export default function MealsPage() {
  const { role, permissions } = useAuthorization();
  const [status, setStatus] = useState<StatusFilter>("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<MealListResponse | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");

  const datesInvalid = Boolean(dateFrom && dateTo) && dateFrom > dateTo;
  const url = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status !== "ALL") params.set("status", status);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    return `${MEAL_RECORDS_ENDPOINT}?${params}`;
  }, [page, pageSize, status, dateFrom, dateTo]);
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    if (datesInvalid) return;
    let active = true;
    api
      .get<MealListResponse>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load meal records."));
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
        eyebrow="Operations"
        icon={UtensilsCrossed}
        title="Meals"
        description="One record per meal session and date: expected and actual headcounts, dishes prepared, what was served and what was left over. Prepared food never changes ingredient stock; ingredient usage comes from the kitchen issues of the same date and session."
        actions={
          canCreateMeals(role, permissions) ? (
            <Link href="/dashboard/meals/new"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700">
              <Plus size={16} aria-hidden />
              New meal record
            </Link>
          ) : undefined
        }
      />

      <Card>
        <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 lg:flex-row lg:items-end lg:justify-between">
          <SegmentedControl<StatusFilter>
            label="Meal status"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={[
              { value: "ALL", label: "All" },
              ...MEAL_STATUSES.map((value) => ({ value, label: MEAL_STATUS_LABELS[value], count: data?.status_counts[value] })),
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
          <ErrorState title="Couldn't load meal records" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : !data ? (
          <TableSkeleton rows={6} columns={6} />
        ) : data.items.length === 0 ? (
          <EmptyState icon={UtensilsCrossed}
            title={filtered ? "No meal records match these filters" : "No meal records yet"}
            description={filtered ? "Try another status or date range." : "Record each meal session's headcounts, dishes and leftovers."} />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="860px">
              <THead>
                <tr>
                  <TH>Meal</TH>
                  <TH>Status</TH>
                  <TH align="right">Expected</TH>
                  <TH align="right">Served</TH>
                  <TH align="right">Dishes</TH>
                  <TH>Recorded by</TH>
                  <TH>Closed</TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((meal) => (
                  <TR key={meal.id} muted={meal.status === "CANCELLED"}>
                    <TD className="whitespace-nowrap">
                      <Link href={`/dashboard/meals/${meal.id}`} className="font-semibold text-brand-700 hover:underline">
                        {meal.meal_session_name}
                      </Link>
                      <div className="text-xs text-slate-500">{formatDay(meal.meal_date)}</div>
                    </TD>
                    <TD>
                      <Badge tone={MEAL_STATUS_TONES[meal.status]} dot>{MEAL_STATUS_LABELS[meal.status]}</Badge>
                      {meal.reopen_count > 0 && <div className="text-xs text-slate-500">reopened {meal.reopen_count}×</div>}
                    </TD>
                    <TD align="right">{meal.expected_total}</TD>
                    <TD align="right">{meal.actual_total ?? "—"}</TD>
                    <TD align="right">{meal.dish_count}</TD>
                    <TD className="whitespace-nowrap">{meal.created_by_name ?? "—"}</TD>
                    <TD className="whitespace-nowrap text-slate-500">
                      {meal.closed_at && meal.status === "CLOSED" ? `${meal.closed_by_name} · ${formatDateTime(meal.closed_at)}` : "—"}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination page={data.page} pageCount={data.total_pages} total={data.total} pageSize={data.page_size}
              noun="meal records" onPageChange={setPage} pageSizeOptions={PAGE_SIZES}
              onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />
          </div>
        )}
      </Card>
    </div>
  );
}
