"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeftRight, CalendarDays, PackageCheck, Plus, X } from "lucide-react";

import { api } from "@/lib/api/client";
import { RECEIPTS_ENDPOINT } from "@/lib/api/endpoints";
import { errorMessage, formatDay } from "@/lib/payments";
import {
  RECEIPT_STATUSES,
  RECEIPT_STATUS_LABELS,
  canRecordReceipts,
  type ReceiptListResponse,
  type ReceiptStatus,
} from "@/lib/receipts";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import ReceiptStatusBadge from "@/components/receipts/ReceiptStatusBadge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SearchInput from "@/components/ui/SearchInput";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type Scope = "ALL" | ReceiptStatus;

type Filters = { scope: Scope; search: string; dateFrom: string; dateTo: string };

const NO_FILTERS: Filters = { scope: "ALL", search: "", dateFrom: "", dateTo: "" };
const PAGE_SIZES = [20, 50, 100];

function listUrl(filters: Filters, page: number, pageSize: number, billId: number | null): string {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (billId) params.set("purchase_id", String(billId));
  if (filters.scope !== "ALL") params.set("status", filters.scope);
  if (filters.search.trim()) params.set("search", filters.search.trim());
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  return `${RECEIPTS_ENDPOINT}?${params}`;
}

function Receipts() {
  const router = useRouter();
  const billFilter = Number(useSearchParams().get("bill")) || null;
  const { role, permissions } = useAuthorization();
  const canRecord = canRecordReceipts(role, permissions);

  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<ReceiptListResponse | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");

  const filtersInvalid = Boolean(filters.dateFrom && filters.dateTo) && filters.dateFrom > filters.dateTo;
  const url = listUrl(filters, page, pageSize, billFilter);
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    if (filtersInvalid) return;
    let active = true;
    // Typing in the search box waits a moment before asking the server.
    const timer = setTimeout(() => {
      api
        .get<ReceiptListResponse>(url)
        .then((response) => {
          if (!active) return;
          setData(response);
          setError("");
        })
        .catch((err: unknown) => {
          if (active) setError(errorMessage(err, "Unable to load goods receipts."));
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

  function update<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  }

  const narrowed = filters.search.trim() !== "" || Boolean(filters.dateFrom || filters.dateTo);
  const filtered = narrowed || filters.scope !== "ALL" || Boolean(billFilter);
  const counts = data?.status_counts;
  const allCount = counts ? RECEIPT_STATUSES.reduce((sum, status) => sum + counts[status], 0) : undefined;
  const newReceipt = () => router.push("/dashboard/receipts/new");

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Purchasing"
        icon={PackageCheck}
        title="Goods receipts"
        description="Deliveries checked in against supplier bills. A receipt starts as a draft; only when it is accepted do its accepted quantities enter stock. Rejected quantities never do."
        actions={
          <>
            <Link
              href="/dashboard/stock-movements"
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
            >
              <ArrowLeftRight size={15} aria-hidden />
              Stock movements
            </Link>
            {canRecord && (
              <Button icon={<Plus size={15} aria-hidden />} onClick={newReceipt}>
                New receipt
              </Button>
            )}
          </>
        }
      />

      {billFilter && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-800">
          <span>
            Showing receipts for bill{" "}
            <span className="font-semibold">{data?.items[0]?.invoice_number ?? `#${billFilter}`}</span>.
          </span>
          <Button size="sm" variant="ghost" icon={<X size={14} aria-hidden />} onClick={() => router.replace("/dashboard/receipts")}>
            Show all receipts
          </Button>
        </div>
      )}

      <Card>
        <div className="space-y-4 border-b border-slate-100 p-5">
          <div className="overflow-x-auto">
            <SegmentedControl<Scope>
              label="Receipts to show"
              value={filters.scope}
              onChange={(value) => update("scope", value)}
              options={[
                { value: "ALL", label: "All", count: allCount },
                ...RECEIPT_STATUSES.map((status) => ({
                  value: status,
                  label: RECEIPT_STATUS_LABELS[status],
                  count: counts?.[status],
                })),
              ]}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_repeat(2,minmax(0,1fr))_auto] lg:items-end">
            <div className="sm:col-span-2 lg:col-span-1">
              <span className="mb-1.5 block text-sm font-medium text-slate-700">Invoice number</span>
              <SearchInput
                label="Search receipts by invoice number"
                value={filters.search}
                placeholder="Search by invoice number"
                onChange={(value) => update("search", value)}
              />
            </div>
            <Field label="Received from">
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
            <Field label="Received to" error={filtersInvalid ? "Must be on or after the From date." : undefined}>
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
          <ErrorState title="Couldn't load receipts" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : !data ? (
          <TableSkeleton rows={6} columns={8} />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={PackageCheck}
            title={filtered ? "No receipts match these filters" : "No goods receipts yet"}
            description={
              filtered
                ? "Try another status, invoice number or date range."
                : canRecord
                  ? "Record the first delivery against a supplier bill."
                  : "Receipts will appear here once deliveries are recorded."
            }
            action={
              !filtered && canRecord ? (
                <Button icon={<Plus size={15} aria-hidden />} onClick={newReceipt}>
                  New receipt
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="900px">
              <THead>
                <tr>
                  <TH>Received</TH>
                  <TH>Receipt</TH>
                  <TH>Bill</TH>
                  <TH>Supplier</TH>
                  <TH align="right">Lines</TH>
                  <TH>Status</TH>
                  <TH>Recorded by</TH>
                  <TH>Accepted by</TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((receipt) => (
                  <TR key={receipt.id}>
                    <TD className="whitespace-nowrap">{formatDay(receipt.receipt_date)}</TD>
                    <TD className="whitespace-nowrap">
                      <Link
                        href={`/dashboard/receipts/${receipt.id}`}
                        className="font-medium text-brand-700 hover:underline"
                        data-receipt-link
                      >
                        GR-{receipt.id}
                      </Link>
                    </TD>
                    <TD className="whitespace-nowrap">{receipt.invoice_number}</TD>
                    <TD className="font-medium text-slate-900">
                      {receipt.supplier_name ?? `Supplier #${receipt.supplier_id}`}
                    </TD>
                    <TD align="right" className="tabular-nums">
                      {receipt.line_count}
                    </TD>
                    <TD>
                      <ReceiptStatusBadge status={receipt.status} />
                    </TD>
                    <TD className="whitespace-nowrap">{receipt.created_by_name ?? "—"}</TD>
                    <TD className="whitespace-nowrap">
                      {receipt.accepted_by_name ?? <span className="text-slate-400">—</span>}
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
              noun="receipts"
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

export default function ReceiptsPage() {
  return (
    <Suspense
      fallback={
        <Card>
          <TableSkeleton rows={6} columns={8} />
        </Card>
      }
    >
      <Receipts />
    </Suspense>
  );
}
