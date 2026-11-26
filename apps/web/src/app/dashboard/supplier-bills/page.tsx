"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CalendarDays, FilePlus2, FileText, X } from "lucide-react";

import { api } from "@/lib/api/client";
import { ENDPOINTS, POSSIBLE_DUPLICATES_ENDPOINT } from "@/lib/api/endpoints";
import {
  canEnterBills,
  canRecordPayments,
  canReviewDuplicates,
  errorMessage,
  fetchAllPages,
  formatDay,
  formatRupees,
  type BillBalance,
  type Page,
  type PossibleDuplicate,
  type SupplierBalance,
} from "@/lib/payments";
import Badge from "@/components/ui/Badge";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import BillDetailModal from "@/components/payments/BillDetailModal";
import PaymentStatusBadge from "@/components/payments/PaymentStatusBadge";
import RecordPaymentModal from "@/components/payments/RecordPaymentModal";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import SearchSelect from "@/components/ui/SearchSelect";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type Filters = {
  supplierId: string;
  scope: "all" | "open" | "duplicates";
  dateFrom: string;
  dateTo: string;
  search: string;
};

const NO_FILTERS: Filters = {
  supplierId: "",
  scope: "all",
  dateFrom: "",
  dateTo: "",
  search: "",
};

const PAGE_SIZES = [20, 50, 100];

function listUrl(filters: Filters, search: string, page: number, pageSize: number) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (filters.supplierId) params.set("supplier_id", filters.supplierId);
  if (filters.scope === "open") params.set("open_only", "true");
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (search) params.set("search", search);
  return `${ENDPOINTS.supplierBillBalances}?${params}`;
}

const linkButton =
  "inline-flex h-10 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700";

export default function SupplierBillsPage() {
  const { role, permissions } = useAuthorization();
  const canEnter = canEnterBills(role, permissions);
  const canRecord = canRecordPayments(role, permissions);
  const canReview = canReviewDuplicates(role, permissions);

  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  // The invoice search is sent 300 ms after typing stops.
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);

  const [data, setData] = useState<Page<BillBalance> | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");
  const [suppliers, setSuppliers] = useState<SupplierBalance[]>([]);

  const [duplicates, setDuplicates] = useState<PossibleDuplicate[] | null>(null);
  const [duplicatesKey, setDuplicatesKey] = useState(0);
  const [viewing, setViewing] = useState<number | null>(null);
  const [paying, setPaying] = useState<BillBalance | null>(null);

  const filtersInvalid =
    Boolean(filters.dateFrom && filters.dateTo) && filters.dateFrom > filters.dateTo;
  const url = listUrl(filters, search, page, pageSize);
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(filters.search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [filters.search]);

  useEffect(() => {
    if (filtersInvalid) return;
    let active = true;

    api
      .get<Page<BillBalance>>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load supplier bills."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });

    return () => {
      active = false;
    };
  }, [url, requestKey, filtersInvalid]);

  // Bills flagged as possible duplicates: a badge in the list, and the
  // "Possible duplicates" view. Refreshed after a review or a payment.
  useEffect(() => {
    let active = true;
    api
      .get<{ items: PossibleDuplicate[] }>(POSSIBLE_DUPLICATES_ENDPOINT)
      .then((response) => {
        if (active) setDuplicates(response.items);
      })
      .catch(() => {
        if (active) setDuplicates([]);
      });
    return () => {
      active = false;
    };
  }, [duplicatesKey, reloadKey]);

  const flagged = new Set((duplicates ?? []).map((item) => item.purchase_id));
  const duplicateRows = (duplicates ?? []).filter(
    (item) =>
      (!filters.supplierId || String(item.supplier_id) === filters.supplierId) &&
      (!filters.dateFrom || item.purchase_date >= filters.dateFrom) &&
      (!filters.dateTo || item.purchase_date <= filters.dateTo) &&
      (!search || item.invoice_number.toLowerCase().includes(search.toLowerCase()))
  );

  // Suppliers that have bills, for the filter.
  useEffect(() => {
    let active = true;
    fetchAllPages<SupplierBalance>(ENDPOINTS.supplierBalances)
      .then(({ items }) => {
        if (active) {
          setSuppliers(
            [...items].sort((a, b) =>
              (a.supplier_name ?? "").localeCompare(b.supplier_name ?? "")
            )
          );
        }
      })
      .catch(() => {
        // The list still works without the supplier filter.
      });
    return () => {
      active = false;
    };
  }, [reloadKey]);

  function update<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
    if (key !== "search") setPage(1);
  }

  const hasFilters =
    filters.supplierId !== "" ||
    filters.scope !== "all" ||
    filters.dateFrom !== "" ||
    filters.dateTo !== "" ||
    filters.search.trim() !== "";

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Purchasing"
        icon={FileText}
        title="Supplier bills"
        description="Bills received from suppliers, with what has been paid and what is still owed on each."
        actions={
          canEnter ? (
            <Link href="/dashboard/supplier-bills/new" className={linkButton}>
              <FilePlus2 size={15} aria-hidden />
              New bill
            </Link>
          ) : undefined
        }
      />

      <Card>
        <div className="space-y-4 border-b border-slate-100 p-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_minmax(0,2fr)_repeat(2,minmax(0,1fr))_auto] lg:items-end">
            <Field label="Invoice number">
              {({ id }) => (
                <TextInput
                  id={id}
                  type="search"
                  placeholder="Search invoices"
                  value={filters.search}
                  onChange={(event) => update("search", event.target.value)}
                />
              )}
            </Field>

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
                  onChange={(value) => update("supplierId", value)}
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
                  onChange={(event) => update("dateFrom", event.target.value)}
                />
              )}
            </Field>

            <Field
              label="To"
              error={filtersInvalid ? "Must be on or after the From date." : undefined}
            >
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

          <SegmentedControl
            label="Bills to show"
            value={filters.scope}
            onChange={(value) => update("scope", value)}
            options={[
              { value: "all", label: "All bills" },
              { value: "open", label: "Unpaid or part paid" },
              {
                value: "duplicates",
                label: "Possible duplicates",
                count: duplicates?.length,
              },
            ]}
          />
        </div>

        {filtersInvalid ? (
          <EmptyState
            icon={CalendarDays}
            title="Check the date range"
            description="The From date must be on or before the To date."
          />
        ) : filters.scope === "duplicates" ? (
          duplicates === null ? (
            <TableSkeleton rows={3} columns={5} />
          ) : duplicateRows.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No possible duplicates"
              description="No bill shares a supplier and an invoice number (ignoring case, spaces and punctuation) with another, or every match has been reviewed."
            />
          ) : (
            <Table minWidth="760px">
              <THead>
                <tr>
                  <TH>Invoice</TH>
                  <TH>Supplier</TH>
                  <TH>Bill date</TH>
                  <TH align="right">Total</TH>
                  <TH>Similar invoices</TH>
                </tr>
              </THead>
              <TBody>
                {duplicateRows.map((item) => (
                  <TR key={item.purchase_id}>
                    <TD>
                      <button
                        type="button"
                        onClick={() => setViewing(item.purchase_id)}
                        className="rounded font-medium text-brand-600 hover:text-brand-700 hover:underline"
                      >
                        {item.invoice_number}
                      </button>
                    </TD>
                    <TD className="text-slate-900">
                      {item.supplier_name ?? `Supplier #${item.supplier_id}`}
                    </TD>
                    <TD className="whitespace-nowrap">{formatDay(item.purchase_date)}</TD>
                    <TD align="right">{formatRupees(item.grand_total)}</TD>
                    <TD className="text-slate-600">
                      {item.possible_duplicates.map((bill) => bill.invoice_number).join(", ")}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )
        ) : error && !loading ? (
          <ErrorState
            title="Couldn't load supplier bills"
            message={error}
            onRetry={() => setReloadKey((key) => key + 1)}
          />
        ) : !data ? (
          <TableSkeleton rows={6} columns={7} />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={FileText}
            title={hasFilters ? "No bills match these filters" : "No supplier bills yet"}
            description={
              hasFilters
                ? "Try another supplier, invoice number or date range."
                : canEnter
                  ? "Enter the first bill received from a supplier."
                  : "Bills will appear here once they are entered."
            }
            action={
              !hasFilters && canEnter ? (
                <Link href="/dashboard/supplier-bills/new" className={linkButton}>
                  <FilePlus2 size={15} aria-hidden />
                  New bill
                </Link>
              ) : undefined
            }
          />
        ) : (
          <div
            className={loading ? "opacity-60 transition-opacity" : undefined}
            aria-busy={loading}
          >
            <Table minWidth="860px">
              <THead>
                <tr>
                  <TH>Bill date</TH>
                  <TH>Invoice</TH>
                  <TH>Supplier</TH>
                  <TH align="right">Total</TH>
                  <TH align="right">Paid</TH>
                  <TH align="right">Outstanding</TH>
                  <TH>Status</TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((bill) => (
                  <TR key={bill.purchase_id}>
                    <TD className="whitespace-nowrap">{formatDay(bill.purchase_date)}</TD>
                    <TD>
                      <button
                        type="button"
                        onClick={() => setViewing(bill.purchase_id)}
                        className="rounded font-medium text-brand-600 hover:text-brand-700 hover:underline"
                      >
                        {bill.invoice_number}
                      </button>
                      {flagged.has(bill.purchase_id) && (
                        <Badge tone="warning" dot className="ml-2">
                          Possible duplicate
                        </Badge>
                      )}
                    </TD>
                    <TD className="text-slate-900">
                      {bill.supplier_name ?? `Supplier #${bill.supplier_id}`}
                    </TD>
                    <TD align="right">{formatRupees(bill.grand_total)}</TD>
                    <TD align="right">{formatRupees(bill.paid_total)}</TD>
                    <TD align="right" className="font-semibold text-slate-900">
                      {formatRupees(bill.outstanding)}
                    </TD>
                    <TD>
                      <PaymentStatusBadge status={bill.payment_status} />
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
              noun="bills"
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

      {viewing !== null && (
        <BillDetailModal
          purchaseId={viewing}
          canRecord={canRecord}
          canUpload={canEnter}
          canReview={canReview}
          reloadKey={reloadKey}
          onClose={() => setViewing(null)}
          onRecordPayment={(bill) => setPaying(bill)}
          onDuplicateReviewed={() => setDuplicatesKey((key) => key + 1)}
        />
      )}

      {paying && (
        <RecordPaymentModal
          bill={paying}
          onClose={() => setPaying(null)}
          onRecorded={() => {
            setPaying(null);
            setReloadKey((key) => key + 1);
          }}
        />
      )}
    </div>
  );
}
