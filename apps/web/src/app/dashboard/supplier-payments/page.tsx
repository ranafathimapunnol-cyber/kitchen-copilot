"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Banknote,
  CalendarDays,
  Plus,
  Receipt,
  Wallet,
  X,
} from "lucide-react";

import { api } from "@/lib/api/client";
import { ENDPOINTS } from "@/lib/api/endpoints";
import {
  PAYMENT_METHODS,
  canRecordPayments,
  errorMessage,
  fetchAllPages,
  formatDay,
  formatRupees,
  methodLabel,
  type PaymentListResponse,
  type SupplierBalance,
  type SupplierBalanceResponse,
} from "@/lib/payments";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import RecordPaymentModal from "@/components/payments/RecordPaymentModal";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import SearchSelect from "@/components/ui/SearchSelect";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import StatCard from "@/components/ui/StatCard";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type Filters = {
  supplierId: string;
  dateFrom: string;
  dateTo: string;
  method: string;
};

const NO_FILTERS: Filters = {
  supplierId: "",
  dateFrom: "",
  dateTo: "",
  method: "",
};

const PAGE_SIZES = [20, 50, 100];

function listUrl(filters: Filters, page: number, pageSize: number): string {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (filters.supplierId) params.set("supplier_id", filters.supplierId);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.method) params.set("payment_method", filters.method);
  return `${ENDPOINTS.supplierPayments}?${params}`;
}

export default function SupplierPaymentsPage() {
  const { role, permissions } = useAuthorization();
  const canRecord = canRecordPayments(role, permissions);

  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);

  const [data, setData] = useState<PaymentListResponse | null>(null);
  const [error, setError] = useState("");
  // The request whose result is on screen; loading is derived from it, so
  // no state is set synchronously inside the effect.
  const [loadedUrl, setLoadedUrl] = useState("");

  const [balances, setBalances] = useState<SupplierBalanceResponse | null>(
    null
  );
  const [recording, setRecording] = useState(false);

  const filtersInvalid =
    Boolean(filters.dateFrom && filters.dateTo) &&
    filters.dateFrom > filters.dateTo;

  const url = listUrl(filters, page, pageSize);
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedUrl !== requestKey;

  useEffect(() => {
    if (filtersInvalid) return;
    let active = true;

    api
      .get<PaymentListResponse>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(errorMessage(err, "Unable to load supplier payments."));
      })
      .finally(() => {
        if (active) setLoadedUrl(requestKey);
      });

    return () => {
      active = false;
    };
  }, [url, requestKey, filtersInvalid]);

  // Supplier list for the filter, plus the campus-wide outstanding figure.
  useEffect(() => {
    let active = true;

    fetchAllPages<SupplierBalance, SupplierBalanceResponse>(
      ENDPOINTS.supplierBalances
    )
      .then(({ items, first }) => {
        if (active) setBalances({ ...first, items });
      })
      .catch(() => {
        // The list still works without the supplier filter.
      });

    return () => {
      active = false;
    };
  }, [reloadKey]);

  function updateFilter(key: keyof Filters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  }

  const hasFilters = Object.values(filters).some(Boolean);
  const suppliers = [...(balances?.items ?? [])].sort((a, b) =>
    (a.supplier_name ?? "").localeCompare(b.supplier_name ?? "")
  );

  const firstLoad = loading && !data;

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Purchasing"
        icon={Banknote}
        title="Supplier payments"
        description="Every payment made to suppliers against their bills. A payment counts towards the bill's balance as soon as it is recorded, and each one is written to the audit log."
        actions={
          <>
            <Link
              href="/dashboard/supplier-balances"
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
            >
              <Wallet size={15} aria-hidden />
              Supplier balances
            </Link>
            {canRecord && (
              <Button
                icon={<Plus size={15} aria-hidden />}
                onClick={() => setRecording(true)}
              >
                Record payment
              </Button>
            )}
          </>
        }
      />

      <section
        aria-label="Payment figures"
        className="grid grid-cols-1 gap-4 sm:grid-cols-3"
      >
        <StatCard
          label={hasFilters ? "Paid (filtered)" : "Total paid"}
          // A reversed date range is never sent, so the last result would
          // not match the filters on screen: show no figure instead.
          value={data && !filtersInvalid ? formatRupees(data.total_paid) : "—"}
          description={
            data && !filtersInvalid
              ? `${data.total} payment${data.total === 1 ? "" : "s"}`
              : undefined
          }
          icon={Banknote}
        />
        <StatCard
          label="Outstanding payables"
          value={balances ? formatRupees(balances.totals.outstanding) : "—"}
          description={
            balances
              ? `${balances.totals.open_bill_count} open bill${balances.totals.open_bill_count === 1 ? "" : "s"}`
              : undefined
          }
          icon={Wallet}
        />
        <StatCard
          label="Suppliers billed"
          value={balances ? String(balances.totals.supplier_count) : "—"}
          description="Suppliers with at least one bill"
          icon={Receipt}
        />
      </section>

      <Card>
        <div className="grid grid-cols-1 gap-4 border-b border-slate-100 p-5 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))_auto] lg:items-end">
          <Field label="Supplier">
            {({ id }) => (
              <SearchSelect
                id={id}
                value={filters.supplierId}
                noun="suppliers"
                emptyLabel="All suppliers"
                options={suppliers.map((row) => ({
                  value: String(row.supplier_id),
                  label: row.supplier_name ?? `Supplier #${row.supplier_id}`,
                }))}
                onChange={(value) => updateFilter("supplierId", value)}
              />
            )}
          </Field>

          <Field label="From">
            {({ id }) => (
              <TextInput
                id={id}
                type="date"
                value={filters.dateFrom}
                max={filters.dateTo || undefined}
                onChange={(event) =>
                  updateFilter("dateFrom", event.target.value)
                }
              />
            )}
          </Field>

          <Field
            label="To"
            error={
              filtersInvalid ? "Must be on or after the From date." : undefined
            }
          >
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                type="date"
                aria-describedby={describedBy}
                aria-invalid={filtersInvalid}
                value={filters.dateTo}
                min={filters.dateFrom || undefined}
                onChange={(event) => updateFilter("dateTo", event.target.value)}
              />
            )}
          </Field>

          <Field label="Method">
            {({ id }) => (
              <SelectInput
                id={id}
                value={filters.method}
                onChange={(event) => updateFilter("method", event.target.value)}
              >
                <option value="">All methods</option>
                {PAYMENT_METHODS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </SelectInput>
            )}
          </Field>

          <Button
            variant="ghost"
            disabled={!hasFilters}
            icon={<X size={15} aria-hidden />}
            onClick={() => {
              setFilters(NO_FILTERS);
              setPage(1);
            }}
          >
            Clear
          </Button>
        </div>

        {filtersInvalid ? (
          <EmptyState
            icon={CalendarDays}
            title="Check the date range"
            description="The From date must be on or before the To date."
          />
        ) : error && !loading ? (
          <ErrorState
            title="Couldn't load payments"
            message={error}
            onRetry={() => setReloadKey((key) => key + 1)}
          />
        ) : firstLoad ? (
          <TableSkeleton rows={6} columns={7} />
        ) : data && data.items.length === 0 ? (
          <EmptyState
            icon={Banknote}
            title={hasFilters ? "No payments match these filters" : "No supplier payments yet"}
            description={
              hasFilters
                ? "Try a wider date range or another supplier."
                : canRecord
                  ? "Record the first payment against an open supplier bill."
                  : "Payments will appear here once they are recorded."
            }
            action={
              !hasFilters && canRecord ? (
                <Button
                  icon={<Plus size={15} aria-hidden />}
                  onClick={() => setRecording(true)}
                >
                  Record payment
                </Button>
              ) : undefined
            }
          />
        ) : data ? (
          <div
            className={loading ? "opacity-60 transition-opacity" : undefined}
            aria-busy={loading}
          >
            <Table minWidth="860px">
              <THead>
                <tr>
                  <TH>Date</TH>
                  <TH>Supplier</TH>
                  <TH>Bill</TH>
                  <TH>Method</TH>
                  <TH>Reference</TH>
                  <TH>Recorded by</TH>
                  <TH align="right">Amount</TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((payment) => (
                  <TR key={payment.id}>
                    <TD className="whitespace-nowrap">
                      {formatDay(payment.payment_date)}
                    </TD>
                    <TD className="font-medium text-slate-900">
                      {payment.supplier_name ??
                        `Supplier #${payment.supplier_id}`}
                    </TD>
                    <TD className="whitespace-nowrap">
                      {payment.invoice_number}
                    </TD>
                    <TD>
                      <Badge>{methodLabel(payment.payment_method)}</Badge>
                    </TD>
                    <TD className="max-w-48 truncate" title={payment.remarks ?? undefined}>
                      {payment.reference_number ?? (
                        <span className="text-slate-400">—</span>
                      )}
                    </TD>
                    <TD className="whitespace-nowrap">
                      {payment.created_by_name ?? "—"}
                    </TD>
                    <TD align="right" className="font-semibold text-slate-900">
                      {formatRupees(payment.amount)}
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
              noun="payments"
              onPageChange={setPage}
              pageSizeOptions={PAGE_SIZES}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
            />
          </div>
        ) : null}
      </Card>

      {recording && (
        <RecordPaymentModal
          onClose={() => setRecording(false)}
          onRecorded={() => {
            setRecording(false);
            setPage(1);
            setReloadKey((key) => key + 1);
          }}
        />
      )}
    </div>
  );
}
