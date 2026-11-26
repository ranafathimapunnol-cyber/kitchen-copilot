"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CalendarDays, ClipboardList, Plus, TriangleAlert, X } from "lucide-react";

import { api } from "@/lib/api/client";
import { ENDPOINTS, PURCHASE_ORDERS_ENDPOINT } from "@/lib/api/endpoints";
import { fetchAllRecords } from "@/lib/api/list";
import { errorMessage, formatDay } from "@/lib/payments";
import {
  ORDER_STATUSES,
  ORDER_STATUS_LABELS,
  canCreateOrders,
  type OrderListResponse,
  type OrderStatus,
} from "@/lib/purchaseOrders";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import { OrderStatusBadge, ReceivingBadge } from "@/components/orders/OrderBadges";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import SearchSelect from "@/components/ui/SearchSelect";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SearchInput from "@/components/ui/SearchInput";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type Scope = "ALL" | OrderStatus;
type Filters = { scope: Scope; supplierId: string; search: string; dateFrom: string; dateTo: string };
type Supplier = { id: number; name: string };

const NO_FILTERS: Filters = { scope: "ALL", supplierId: "", search: "", dateFrom: "", dateTo: "" };
const PAGE_SIZES = [20, 50, 100];

export default function PurchaseOrdersPage() {
  const router = useRouter();
  const { role, permissions } = useAuthorization();
  const canCreate = canCreateOrders(role, permissions);

  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<OrderListResponse | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  const filtersInvalid = Boolean(filters.dateFrom && filters.dateTo) && filters.dateFrom > filters.dateTo;
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (filters.scope !== "ALL") params.set("status", filters.scope);
  if (filters.supplierId) params.set("supplier_id", filters.supplierId);
  if (filters.search.trim()) params.set("search", filters.search.trim());
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  const url = `${PURCHASE_ORDERS_ENDPOINT}?${params}`;
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    if (filtersInvalid) return;
    let active = true;
    const timer = setTimeout(() => {
      api
        .get<OrderListResponse>(url)
        .then((response) => {
          if (!active) return;
          setData(response);
          setError("");
        })
        .catch((err: unknown) => {
          if (active) setError(errorMessage(err, "Unable to load purchase orders."));
        })
        .finally(() => {
          if (active) setLoadedKey(requestKey);
        });
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [url, requestKey, filtersInvalid]);

  useEffect(() => {
    let active = true;
    fetchAllRecords<Supplier>(ENDPOINTS.suppliers)
      .then(({ rows }) => {
        if (active) setSuppliers([...rows].sort((a, b) => a.name.localeCompare(b.name)));
      })
      .catch(() => {
        // The list still works without the supplier filter.
      });
    return () => {
      active = false;
    };
  }, []);

  function update<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  }

  const filtered =
    filters.scope !== "ALL" || Boolean(filters.supplierId || filters.search.trim() || filters.dateFrom || filters.dateTo);
  const counts = data?.status_counts;
  const allCount = counts ? ORDER_STATUSES.reduce((sum, status) => sum + counts[status], 0) : undefined;
  const newOrder = () => router.push("/dashboard/purchase-orders/new");

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Purchasing"
        icon={ClipboardList}
        title="Purchase orders"
        description="What was ordered from suppliers: items and quantities. A draft can be edited until it is placed; bills are entered against placed orders, and receipts against those bills show how much has arrived."
        actions={
          canCreate ? (
            <Button icon={<Plus size={15} aria-hidden />} onClick={newOrder}>
              New purchase order
            </Button>
          ) : undefined
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
                ...ORDER_STATUSES.map((status) => ({
                  value: status,
                  label: ORDER_STATUS_LABELS[status],
                  count: counts?.[status],
                })),
              ]}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1.6fr)_repeat(2,minmax(0,1fr))_auto] lg:items-end">
            <div>
              <span className="mb-1.5 block text-sm font-medium text-slate-700">Order or supplier</span>
              <SearchInput
                label="Search purchase orders"
                value={filters.search}
                placeholder="PO number or supplier"
                onChange={(value) => update("search", value)}
              />
            </div>
            <Field label="Supplier">
              {({ id }) => (
                <SearchSelect
                  id={id}
                  value={filters.supplierId}
                  noun="suppliers"
                  emptyLabel="All suppliers"
                  options={suppliers.map((row) => ({ value: String(row.id), label: row.name }))}
                  onChange={(value) => update("supplierId", value)}
                />
              )}
            </Field>
            <Field label="Ordered from">
              {({ id }) => (
                <TextInput
                  id={id}
                  type="date"
                  value={filters.dateFrom}
                  max={filters.dateTo || undefined}
                  onChange={(event) => update("dateFrom", event.target.value)}
                />
              )}
            </Field>
            <Field label="Ordered to" error={filtersInvalid ? "Must be on or after the From date." : undefined}>
              {({ id, describedBy }) => (
                <TextInput
                  id={id}
                  type="date"
                  aria-describedby={describedBy}
                  aria-invalid={filtersInvalid}
                  value={filters.dateTo}
                  min={filters.dateFrom || undefined}
                  onChange={(event) => update("dateTo", event.target.value)}
                />
              )}
            </Field>
            <Button
              variant="ghost"
              disabled={!filtered}
              icon={<X size={15} aria-hidden />}
              onClick={() => {
                setFilters(NO_FILTERS);
                setPage(1);
              }}
            >
              Clear
            </Button>
          </div>
        </div>

        {filtersInvalid ? (
          <EmptyState icon={CalendarDays} title="Check the date range" description="The From date must be on or before the To date." />
        ) : error && !loading ? (
          <ErrorState title="Couldn't load purchase orders" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : !data ? (
          <TableSkeleton rows={6} columns={8} />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={ClipboardList}
            title={filtered ? "No orders match these filters" : "No purchase orders yet"}
            description={
              filtered
                ? "Try another status, supplier, search or date range."
                : canCreate
                  ? "Create the first order: choose a supplier and the items to order."
                  : "Orders will appear here once they are created."
            }
            action={
              !filtered && canCreate ? (
                <Button icon={<Plus size={15} aria-hidden />} onClick={newOrder}>
                  New purchase order
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="960px">
              <THead>
                <tr>
                  <TH>Order</TH>
                  <TH>Ordered</TH>
                  <TH>Supplier</TH>
                  <TH>Expected</TH>
                  <TH align="right">Lines</TH>
                  <TH>Status</TH>
                  <TH>Receiving</TH>
                  <TH align="right">Bills</TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((order) => (
                  <TR key={order.id}>
                    <TD className="whitespace-nowrap">
                      <Link
                        href={`/dashboard/purchase-orders/${order.id}`}
                        className="font-medium text-brand-700 hover:underline"
                        data-order-link
                      >
                        {order.order_number}
                      </Link>
                    </TD>
                    <TD className="whitespace-nowrap">{formatDay(order.order_date)}</TD>
                    <TD className="font-medium text-slate-900">{order.supplier_name ?? `Supplier #${order.supplier_id}`}</TD>
                    <TD className="whitespace-nowrap">
                      {order.expected_date ? formatDay(order.expected_date) : <span className="text-slate-400">—</span>}
                    </TD>
                    <TD align="right" className="tabular-nums">
                      {order.line_count}
                    </TD>
                    <TD>
                      <OrderStatusBadge status={order.status} />
                    </TD>
                    <TD className="whitespace-nowrap">
                      {order.status === "DRAFT" || order.status === "CANCELLED" ? (
                        <span className="text-slate-400">—</span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5">
                          <ReceivingBadge state={order.receiving_state} />
                          {order.over_billed && (
                            <span title="Billed more than ordered" className="text-amber-600" data-over-billed>
                              <TriangleAlert size={14} aria-label="Billed more than ordered" />
                            </span>
                          )}
                        </span>
                      )}
                    </TD>
                    <TD align="right" className="tabular-nums">
                      {order.bill_count}
                    </TD>
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
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
            />
          </div>
        )}
      </Card>
    </div>
  );
}
