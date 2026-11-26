"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import {
  Banknote,
  ChevronDown,
  ChevronRight,
  FileText,
  HandCoins,
  Plus,
  Receipt,
  Wallet,
} from "lucide-react";

import { api } from "@/lib/api/client";
import { ENDPOINTS, billPaymentsEndpoint } from "@/lib/api/endpoints";
import {
  canRecordPayments,
  errorMessage,
  formatDay,
  formatRupees,
  methodLabel,
  toAmount,
  type BillBalance,
  type Page,
  type SupplierBalance,
  type SupplierBalanceResponse,
  type SupplierPayment,
} from "@/lib/payments";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import PaymentStatusBadge from "@/components/payments/PaymentStatusBadge";
import RecordPaymentModal from "@/components/payments/RecordPaymentModal";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SegmentedControl from "@/components/ui/SegmentedControl";
import StatCard from "@/components/ui/StatCard";
import {
  EmptyState,
  ErrorState,
  Spinner,
  TableSkeleton,
} from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

const PAGE_SIZE = 50;
const BILL_PAGE_SIZE = 20;

type PaymentRecording = { bill?: BillBalance } | null;

function supplierLabel(row: { supplier_id: number; supplier_name: string | null }) {
  return row.supplier_name ?? `Supplier #${row.supplier_id}`;
}

/** A supplier's position in words, so it never rests on colour alone. */
function SupplierPosition({ row }: { row: SupplierBalance }) {
  if (toAmount(row.overpaid) > 0) {
    return (
      <Badge tone="brand" dot>
        {formatRupees(row.overpaid)} overpaid
      </Badge>
    );
  }
  if (toAmount(row.outstanding) > 0) {
    return (
      <Badge tone="warning" dot>
        {row.open_bill_count} open
      </Badge>
    );
  }
  return (
    <Badge tone="success" dot>
      Settled
    </Badge>
  );
}

// ------------------------------------------------------------------
// One bill's payment history, loaded when its row is expanded.
// ------------------------------------------------------------------

function BillPaymentHistory({ purchaseId }: { purchaseId: number }) {
  const [payments, setPayments] = useState<SupplierPayment[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    api
      .get<{ payments: SupplierPayment[] }>(billPaymentsEndpoint(purchaseId))
      .then((response) => {
        if (active) setPayments(response.payments);
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load payments."));
      });

    return () => {
      active = false;
    };
  }, [purchaseId]);

  if (error) {
    return <p className="text-sm text-red-700">{error}</p>;
  }

  if (!payments) {
    return <Spinner label="Loading payments" />;
  }

  if (!payments.length) {
    return <p className="text-sm text-slate-500">No payments recorded for this bill.</p>;
  }

  return (
    <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
      {payments.map((payment) => (
        <li
          key={payment.id}
          className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-2.5 text-sm"
        >
          <span className="min-w-0 text-slate-700">
            <span className="font-medium text-slate-900">
              {formatDay(payment.payment_date)}
            </span>{" "}
            · {methodLabel(payment.payment_method)}
            {payment.reference_number && ` · ${payment.reference_number}`}
            {payment.created_by_name && (
              <span className="text-slate-500"> · by {payment.created_by_name}</span>
            )}
          </span>
          <span className="font-semibold text-slate-900 tabular-nums">
            {formatRupees(payment.amount)}
          </span>
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------
// A supplier's bills with their balances.
// ------------------------------------------------------------------

function SupplierBillsModal({
  supplier,
  canRecord,
  reloadKey,
  onClose,
  onRecordPayment,
}: {
  supplier: SupplierBalance;
  canRecord: boolean;
  reloadKey: number;
  onClose: () => void;
  onRecordPayment: (bill: BillBalance) => void;
}) {
  const [scope, setScope] = useState<"open" | "all">(
    toAmount(supplier.outstanding) > 0 ? "open" : "all"
  );
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<BillBalance> | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  const url = `${ENDPOINTS.supplierBillBalances}?supplier_id=${supplier.supplier_id}&open_only=${scope === "open"}&page=${page}&page_size=${BILL_PAGE_SIZE}`;
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    let active = true;

    api
      .get<Page<BillBalance>>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load bills."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });

    return () => {
      active = false;
    };
  }, [url, requestKey]);

  return (
    <Modal
      open
      onClose={onClose}
      size="xl"
      title={`Bills · ${supplierLabel(supplier)}`}
      description={`${formatRupees(supplier.outstanding)} outstanding across ${supplier.open_bill_count} open bill${supplier.open_bill_count === 1 ? "" : "s"} · ${formatRupees(supplier.total_billed)} billed · ${formatRupees(supplier.total_paid)} paid`}
    >
      <div className="space-y-4">
        <SegmentedControl
          label="Bills to show"
          value={scope}
          onChange={(value) => {
            setScope(value);
            setPage(1);
            setExpanded(null);
          }}
          options={[
            { value: "open", label: "Open bills" },
            { value: "all", label: "All bills" },
          ]}
        />

        {error && !loading ? (
          <ErrorState title="Couldn't load bills" message={error} />
        ) : !data ? (
          <TableSkeleton rows={4} columns={6} />
        ) : data.items.length === 0 ? (
          <EmptyState
            compact
            icon={FileText}
            title={scope === "open" ? "No open bills" : "No bills"}
            description={
              scope === "open"
                ? "Every bill from this supplier is fully paid."
                : undefined
            }
          />
        ) : (
          <div
            className="overflow-hidden rounded-lg border border-slate-200"
            aria-busy={loading}
          >
            <Table minWidth="720px">
              <THead>
                <tr>
                  <TH>Bill</TH>
                  <TH align="right">Total</TH>
                  <TH align="right">Paid</TH>
                  <TH align="right">Outstanding</TH>
                  <TH>Status</TH>
                  <TH align="right">
                    <span className="sr-only">Actions</span>
                  </TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((bill) => {
                  const open = expanded === bill.purchase_id;
                  const payable = toAmount(bill.outstanding) > 0;

                  return (
                    <Fragment key={bill.purchase_id}>
                      <TR>
                        <TD>
                          <button
                            type="button"
                            onClick={() =>
                              setExpanded(open ? null : bill.purchase_id)
                            }
                            aria-expanded={open}
                            className="flex items-center gap-2 rounded text-left"
                          >
                            {open ? (
                              <ChevronDown size={15} aria-hidden className="text-slate-400" />
                            ) : (
                              <ChevronRight size={15} aria-hidden className="text-slate-400" />
                            )}
                            <span>
                              <span className="block font-medium text-slate-900">
                                {bill.invoice_number}
                              </span>
                              <span className="block text-xs text-slate-500">
                                {formatDay(bill.purchase_date)}
                              </span>
                            </span>
                          </button>
                        </TD>
                        <TD align="right">{formatRupees(bill.grand_total)}</TD>
                        <TD align="right">{formatRupees(bill.paid_total)}</TD>
                        <TD align="right" className="font-semibold text-slate-900">
                          {formatRupees(bill.outstanding)}
                          {toAmount(bill.overpaid) > 0 && (
                            <span className="block text-xs font-normal text-slate-500">
                              {formatRupees(bill.overpaid)} overpaid
                            </span>
                          )}
                        </TD>
                        <TD>
                          <PaymentStatusBadge status={bill.payment_status} />
                        </TD>
                        <TD align="right">
                          {canRecord && payable && (
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => onRecordPayment(bill)}
                            >
                              Record payment
                            </Button>
                          )}
                        </TD>
                      </TR>
                      {open && (
                        <tr className="bg-slate-50/70">
                          <td colSpan={6} className="px-5 py-3">
                            <BillPaymentHistory
                              key={`${bill.purchase_id}-${reloadKey}`}
                              purchaseId={bill.purchase_id}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </TBody>
            </Table>

            <Pagination
              page={data.page}
              pageCount={data.total_pages}
              total={data.total}
              pageSize={data.page_size}
              noun="bills"
              onPageChange={(next) => {
                setPage(next);
                setExpanded(null);
              }}
            />
          </div>
        )}
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------
// Page
// ------------------------------------------------------------------

export default function SupplierBalancesPage() {
  const { role, permissions } = useAuthorization();
  const canRecord = canRecordPayments(role, permissions);

  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<SupplierBalanceResponse | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");

  const [viewing, setViewing] = useState<SupplierBalance | null>(null);
  const [recording, setRecording] = useState<PaymentRecording>(null);

  const url = `${ENDPOINTS.supplierBalances}?page=${page}&page_size=${PAGE_SIZE}`;
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    let active = true;

    api
      .get<SupplierBalanceResponse>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
        // Keep an open bills panel in step with the refreshed figures.
        setViewing((current) =>
          current
            ? (response.items.find(
                (row) => row.supplier_id === current.supplier_id
              ) ?? current)
            : current
        );
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load supplier balances."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });

    return () => {
      active = false;
    };
  }, [url, requestKey]);

  const totals = data?.totals;
  const hasOverpaid = toAmount(totals?.overpaid) > 0;

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Purchasing"
        icon={Wallet}
        title="Supplier balances"
        description="What the campus owes each supplier, worked out from supplier bills and the payments recorded against them."
        actions={
          <>
            <Link
              href="/dashboard/supplier-payments"
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
            >
              <Banknote size={15} aria-hidden />
              Payment history
            </Link>
            {canRecord && (
              <Button
                icon={<Plus size={15} aria-hidden />}
                onClick={() => setRecording({})}
              >
                Record payment
              </Button>
            )}
          </>
        }
      />

      <section
        aria-label="Balance totals"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <StatCard
          label="Outstanding"
          value={totals ? formatRupees(totals.outstanding) : "—"}
          description={
            totals
              ? `${totals.open_bill_count} open bill${totals.open_bill_count === 1 ? "" : "s"}`
              : undefined
          }
          icon={Wallet}
        />
        <StatCard
          label="Total billed"
          value={totals ? formatRupees(totals.total_billed) : "—"}
          description={
            totals
              ? `${totals.supplier_count} supplier${totals.supplier_count === 1 ? "" : "s"}`
              : undefined
          }
          icon={Receipt}
        />
        <StatCard
          label="Total paid"
          value={totals ? formatRupees(totals.total_paid) : "—"}
          description="All recorded payments"
          icon={Banknote}
        />
        <StatCard
          label="Overpaid"
          value={totals ? formatRupees(totals.overpaid) : "—"}
          description={
            hasOverpaid ? "Paid beyond bill totals" : "No bill is overpaid"
          }
          icon={HandCoins}
        />
      </section>

      <Card>
        {error && !loading ? (
          <ErrorState
            title="Couldn't load supplier balances"
            message={error}
            onRetry={() => setReloadKey((key) => key + 1)}
          />
        ) : !data ? (
          <TableSkeleton rows={5} columns={6} />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={Wallet}
            title="No supplier bills yet"
            description="Balances appear here once supplier bills are recorded."
          />
        ) : (
          <div
            className={loading ? "opacity-60 transition-opacity" : undefined}
            aria-busy={loading}
          >
            <Table minWidth="820px">
              <THead>
                <tr>
                  <TH>Supplier</TH>
                  <TH align="right">Bills</TH>
                  <TH align="right">Billed</TH>
                  <TH align="right">Paid</TH>
                  <TH align="right">Outstanding</TH>
                  <TH>Position</TH>
                  <TH align="right">
                    <span className="sr-only">Actions</span>
                  </TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((row) => (
                  <TR key={row.supplier_id}>
                    <TD className="font-medium text-slate-900">
                      {supplierLabel(row)}
                    </TD>
                    <TD align="right">
                      {row.open_bill_count} / {row.bill_count}
                    </TD>
                    <TD align="right">{formatRupees(row.total_billed)}</TD>
                    <TD align="right">{formatRupees(row.total_paid)}</TD>
                    <TD align="right" className="font-semibold text-slate-900">
                      {formatRupees(row.outstanding)}
                    </TD>
                    <TD>
                      <SupplierPosition row={row} />
                    </TD>
                    <TD align="right">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setViewing(row)}
                      >
                        View bills
                      </Button>
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
              noun="suppliers"
              onPageChange={setPage}
            />
          </div>
        )}
      </Card>

      <p className="text-xs text-slate-500">
        Open bills / total bills. Supplier-return credits are not deducted
        from these balances yet.
      </p>

      {viewing && (
        <SupplierBillsModal
          supplier={viewing}
          canRecord={canRecord}
          reloadKey={reloadKey}
          onClose={() => setViewing(null)}
          onRecordPayment={(bill) => setRecording({ bill })}
        />
      )}

      {recording && (
        <RecordPaymentModal
          bill={recording.bill}
          onClose={() => setRecording(null)}
          onRecorded={() => {
            setRecording(null);
            setReloadKey((key) => key + 1);
          }}
        />
      )}
    </div>
  );
}
