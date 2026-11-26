"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CalendarDays, ChartColumn, Plus, Soup, X } from "lucide-react";

import { api } from "@/lib/api/client";
import { OUTSOURCED_OPTIONS_ENDPOINT, OUTSOURCED_ORDERS_ENDPOINT } from "@/lib/api/endpoints";
import {
  ORDER_STATUSES,
  ORDER_STATUS_LABELS,
  canManageOutsourcedOrders,
  type OutsourcedListResponse,
  type OutsourcedOptions,
  type OutsourcedStatus,
} from "@/lib/outsourced";
import { errorMessage, formatDay, formatRupees } from "@/lib/payments";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import { OutsourcedReceivingBadge, OutsourcedStatusBadge } from "@/components/outsourced/OutsourcedBadges";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SearchSelect from "@/components/ui/SearchSelect";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type Scope = "ALL" | OutsourcedStatus;
type Filters = { scope: Scope; sessionId: string; supplierId: string; itemId: string; dateFrom: string; dateTo: string };

const NO_FILTERS: Filters = { scope: "ALL", sessionId: "", supplierId: "", itemId: "", dateFrom: "", dateTo: "" };
const PAGE_SIZES = [20, 50, 100];

export default function OutsourcedOrdersPage() {
  const router = useRouter();
  const { role, permissions } = useAuthorization();
  const canCreate = canManageOutsourcedOrders(role, permissions);

  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<OutsourcedListResponse | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");
  const [options, setOptions] = useState<OutsourcedOptions | null>(null);

  const filtersInvalid = Boolean(filters.dateFrom && filters.dateTo) && filters.dateFrom > filters.dateTo;
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (filters.scope !== "ALL") params.set("status", filters.scope);
  if (filters.sessionId) params.set("meal_session_id", filters.sessionId);
  if (filters.supplierId) params.set("supplier_id", filters.supplierId);
  if (filters.itemId) params.set("item_id", filters.itemId);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  const url = `${OUTSOURCED_ORDERS_ENDPOINT}?${params}`;
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    if (filtersInvalid) return;
    let active = true;
    const timer = setTimeout(() => {
      api
        .get<OutsourcedListResponse>(url)
        .then((response) => {
          if (!active) return;
          setData(response);
          setError("");
        })
        .catch((err: unknown) => {
          if (active) setError(errorMessage(err, "Unable to load outsourced orders."));
        })
        .finally(() => {
          if (active) setLoadedKey(requestKey);
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [url, requestKey, filtersInvalid]);

  useEffect(() => {
    let active = true;
    api
      .get<OutsourcedOptions>(OUTSOURCED_OPTIONS_ENDPOINT)
      .then((response) => active && setOptions(response))
      .catch(() => {
        // The list still works without the filters' choices.
      });
    return () => {
      active = false;
    };
  }, []);

  function update<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  }

  const filtered = filters.scope !== "ALL" || Boolean(filters.sessionId || filters.supplierId || filters.itemId || filters.dateFrom || filters.dateTo);
  const counts = data?.status_counts;
  const allCount = counts ? ORDER_STATUSES.reduce((sum, status) => sum + counts[status], 0) : undefined;
  const costs = Boolean(data?.costs_visible);
  const newOrder = () => router.push("/dashboard/outsourced-food/new");

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Operations"
        icon={Soup}
        title="Outsourced food"
        description="Ready-made food ordered for a meal: what was ordered, delivered, rejected and accepted. Accepted food is added to the meal record of the same date and meal session; it never enters ingredient stock."
        actions={
          <div className="flex flex-wrap gap-2">
            <Link
              href="/dashboard/outsourced-food/report"
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
            >
              <ChartColumn size={15} aria-hidden />
              Report
            </Link>
            {canCreate && (
              <Button icon={<Plus size={15} aria-hidden />} onClick={newOrder}>New outsourced order</Button>
            )}
          </div>
        }
      />

      <Card>
        <div className="space-y-4 border-b border-slate-100 p-5">
          <div className="overflow-x-auto">
            <SegmentedControl<Scope>
              label="Orders to show"
              value={filters.scope}
              onChange={(value) => update("scope", value)}
              options={[
                { value: "ALL", label: "All", count: allCount },
                ...ORDER_STATUSES.map((status) => ({ value: status, label: ORDER_STATUS_LABELS[status], count: counts?.[status] })),
              ]}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[repeat(2,minmax(0,1fr))_repeat(3,minmax(0,1.4fr))_auto] lg:items-end">
            <Field label="Meal date from">
              {({ id }) => (
                <TextInput id={id} type="date" value={filters.dateFrom} max={filters.dateTo || undefined}
                  onChange={(event) => update("dateFrom", event.target.value)} />
              )}
            </Field>
            <Field label="Meal date to" error={filtersInvalid ? "Must be on or after the From date." : undefined}>
              {({ id, describedBy }) => (
                <TextInput id={id} type="date" aria-describedby={describedBy} aria-invalid={filtersInvalid} value={filters.dateTo}
                  min={filters.dateFrom || undefined} onChange={(event) => update("dateTo", event.target.value)} />
              )}
            </Field>
            <Field label="Meal session">
              {({ id }) => (
                <SelectInput id={id} value={filters.sessionId} onChange={(event) => update("sessionId", event.target.value)}>
                  <option value="">All sessions</option>
                  {options?.meal_sessions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </SelectInput>
              )}
            </Field>
            <Field label="Supplier">
              {({ id }) => (
                <SearchSelect id={id} value={filters.supplierId} noun="suppliers" emptyLabel="All suppliers"
                  options={(options?.suppliers ?? []).map((s) => ({ value: String(s.id), label: s.name }))}
                  onChange={(value) => update("supplierId", value)} />
              )}
            </Field>
            <Field label="Item">
              {({ id }) => (
                <SearchSelect id={id} value={filters.itemId} noun="items" emptyLabel="All items"
                  options={(options?.items ?? []).map((i) => ({ value: String(i.id), label: i.name }))}
                  onChange={(value) => update("itemId", value)} />
              )}
            </Field>
            <Button variant="ghost" disabled={!filtered} icon={<X size={15} aria-hidden />}
              onClick={() => { setFilters(NO_FILTERS); setPage(1); }}>
              Clear
            </Button>
          </div>
        </div>

        {filtersInvalid ? (
          <EmptyState icon={CalendarDays} title="Check the date range" description="The From date must be on or before the To date." />
        ) : error && !loading ? (
          <ErrorState title="Couldn't load outsourced orders" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : !data ? (
          <TableSkeleton rows={6} columns={8} />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={Soup}
            title={filtered ? "No orders match these filters" : "No outsourced orders yet"}
            description={filtered ? "Try another status, date, session, supplier or item."
              : canCreate ? "Record the first order: the meal, the supplier and the food ordered."
                : "Orders appear here once an Admin or Kitchen Manager records them."}
            action={!filtered && canCreate ? (
              <Button icon={<Plus size={15} aria-hidden />} onClick={newOrder}>New outsourced order</Button>
            ) : undefined}
          />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="980px">
              <THead>
                <tr>
                  <TH>Order</TH>
                  <TH>Meal</TH>
                  <TH>Supplier</TH>
                  <TH>Food</TH>
                  <TH>Status</TH>
                  <TH>Received</TH>
                  <TH align="right">Deliveries</TH>
                  {costs && <TH align="right">Planned cost</TH>}
                </tr>
              </THead>
              <TBody>
                {data.items.map((order) => (
                  <TR key={order.id}>
                    <TD className="whitespace-nowrap">
                      <Link href={`/dashboard/outsourced-food/${order.id}`} className="font-medium text-brand-700 hover:underline" data-outsourced-link>
                        {order.order_number}
                      </Link>
                      <div className="text-xs text-slate-500">ordered {formatDay(order.order_date)}</div>
                    </TD>
                    <TD className="whitespace-nowrap">
                      <span className="font-medium text-slate-900">{order.meal_session_name}</span>
                      <div className="text-xs text-slate-500">{formatDay(order.meal_date)}</div>
                    </TD>
                    <TD>{order.supplier_name}</TD>
                    <TD className="max-w-64 text-sm">{order.item_names.filter(Boolean).join(", ")}</TD>
                    <TD><OutsourcedStatusBadge status={order.status} /></TD>
                    <TD className="whitespace-nowrap">
                      {order.receiving_status ? <OutsourcedReceivingBadge status={order.receiving_status} /> : <span className="text-slate-400">—</span>}
                    </TD>
                    <TD align="right" className="tabular-nums">{order.delivery_count}</TD>
                    {costs && <TD align="right" className="whitespace-nowrap tabular-nums">{formatRupees(order.planned_total ?? "0")}</TD>}
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination
              page={data.page}
              pageCount={data.total_pages}
              total={data.total}
              pageSize={data.page_size}
              noun="orders"
              onPageChange={setPage}
              pageSizeOptions={PAGE_SIZES}
              onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
            />
          </div>
        )}
      </Card>
    </div>
  );
}
