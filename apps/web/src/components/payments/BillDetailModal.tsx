"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";

import { api } from "@/lib/api/client";
import { billOutsourcedLinksEndpoint, billPaymentsEndpoint, supplierBillEndpoint } from "@/lib/api/endpoints";
import {
  errorMessage,
  formatDay,
  formatRupees,
  methodLabel,
  toAmount,
  type BillBalance,
  type SupplierBill,
  type SupplierPayment,
} from "@/lib/payments";
import BillAttachments from "@/components/payments/BillAttachments";
import DuplicateNotice from "@/components/payments/DuplicateNotice";
import PaymentStatusBadge from "@/components/payments/PaymentStatusBadge";
import BillReceivingPanel from "@/components/receipts/BillReceivingPanel";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import { canViewOrders } from "@/lib/purchaseOrders";
import { canViewOutsourced } from "@/lib/outsourced";
import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import { ErrorState, Spinner } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type Loaded = {
  bill: SupplierBill;
  balance: BillBalance;
  payments: SupplierPayment[];
};

/**
 * One supplier bill: its lines exactly as recorded, its totals, its
 * balance and its payments. Mount it only while open.
 */
export default function BillDetailModal({
  purchaseId,
  canRecord,
  canUpload = false,
  canReview = false,
  reloadKey,
  onClose,
  onRecordPayment,
  onDuplicateReviewed,
}: {
  purchaseId: number;
  canRecord: boolean;
  /** May attach files (purchase_bill.create). */
  canUpload?: boolean;
  /** May mark a possible duplicate "not a duplicate" (purchase_bill.update). */
  canReview?: boolean;
  /** Changes after a payment, so the balance and history refresh. */
  reloadKey: number;
  onClose: () => void;
  onRecordPayment: (bill: BillBalance) => void;
  onDuplicateReviewed?: () => void;
}) {
  const { role, permissions } = useAuthorization();
  // Purchase orders are Admin and Kitchen Manager only.
  const canOpenOrders = canViewOrders(role, permissions);
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState("");
  // Stage 8a: bill lines that bill an outsourced order line (shown to users
  // who may open outsourced orders).
  const canOpenOutsourced = canViewOutsourced(role, permissions);
  const [outsourcedLinks, setOutsourcedLinks] = useState<Record<number, { order_id: number; order_number: string }>>({});

  useEffect(() => {
    if (!canOpenOutsourced) return;
    let active = true;
    api
      .get<{ items: { purchase_item_id: number; order_id: number; order_number: string }[] }>(billOutsourcedLinksEndpoint(purchaseId))
      .then((response) => {
        if (active) setOutsourcedLinks(Object.fromEntries(response.items.map((link) => [link.purchase_item_id, link])));
      })
      .catch(() => {
        // The bill still shows without its outsourced links.
      });
    return () => {
      active = false;
    };
  }, [purchaseId, canOpenOutsourced]);

  useEffect(() => {
    let active = true;

    Promise.all([
      api.get<SupplierBill>(supplierBillEndpoint(purchaseId)),
      api.get<{ bill: BillBalance; payments: SupplierPayment[] }>(
        billPaymentsEndpoint(purchaseId)
      ),
    ])
      .then(([bill, history]) => {
        if (active) {
          setData({ bill, balance: history.bill, payments: history.payments });
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load this bill."));
      });

    return () => {
      active = false;
    };
  }, [purchaseId, reloadKey]);

  const bill = data?.bill;
  const balance = data?.balance;
  const payable = balance ? toAmount(balance.outstanding) > 0 : false;

  return (
    <Modal
      open
      onClose={onClose}
      size="xl"
      title={bill ? `Bill ${bill.invoice_number}` : "Supplier bill"}
      description={
        bill
          ? `${bill.supplier_name ?? `Supplier #${bill.supplier_id}`} · ${formatDay(bill.purchase_date)}`
          : undefined
      }
      footer={
        canRecord && payable && balance ? (
          <Button
            icon={<Plus size={15} aria-hidden />}
            onClick={() => onRecordPayment(balance)}
          >
            Record payment
          </Button>
        ) : undefined
      }
    >
      {error ? (
        <ErrorState title="Couldn't load the bill" message={error} />
      ) : !bill || !balance || !data ? (
        <Spinner label="Loading bill" />
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <PaymentStatusBadge status={balance.payment_status} />
            <span className="text-sm text-slate-500">
              {formatRupees(balance.paid_total)} paid ·{" "}
              <span className="font-semibold text-slate-900">
                {formatRupees(balance.outstanding)} outstanding
              </span>
              {toAmount(balance.overpaid) > 0 &&
                ` · ${formatRupees(balance.overpaid)} overpaid`}
            </span>
            {bill.purchase_order_id && bill.purchase_order_number && canOpenOrders && (
              <Link
                href={`/dashboard/purchase-orders/${bill.purchase_order_id}`}
                className="text-sm font-medium text-brand-700 hover:underline"
                data-bill-order-link
              >
                Against {bill.purchase_order_number}
              </Link>
            )}
          </div>

          <DuplicateNotice
            purchaseId={bill.id}
            status={{
              possible_duplicates: bill.possible_duplicates ?? [],
              duplicate_review: bill.duplicate_review ?? null,
              flagged_as_possible_duplicate: bill.flagged_as_possible_duplicate ?? false,
            }}
            canReview={canReview}
            onReviewed={(next) => {
              setData((current) =>
                current ? { ...current, bill: { ...current.bill, ...next } } : current
              );
              onDuplicateReviewed?.();
            }}
          />

          <div className="overflow-hidden rounded-lg border border-slate-200">
            <Table minWidth="640px">
              <THead>
                <tr>
                  <TH>Item</TH>
                  <TH align="right">Quantity</TH>
                  <TH align="right">Unit rate</TH>
                  <TH align="right">Line total</TH>
                </tr>
              </THead>
              <TBody>
                {bill.items.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-5 py-4 text-sm text-slate-500">
                      No item lines were recorded with this bill.
                    </td>
                  </tr>
                )}
                {bill.items.map((line) => (
                  <TR key={line.id}>
                    <TD>
                      <span className="block font-medium text-slate-900">
                        {line.item_name ?? `Item #${line.item_id}`}
                      </span>
                      <span className="block text-xs text-slate-500">
                        {[line.category_name, line.remarks].filter(Boolean).join(" · ")}
                      </span>
                      {outsourcedLinks[line.id] && (
                        <Link
                          href={`/dashboard/outsourced-food/${outsourcedLinks[line.id].order_id}`}
                          className="block text-xs font-medium text-brand-700 hover:underline"
                          data-bill-outsourced-link
                        >
                          Outsourced order {outsourcedLinks[line.id].order_number}
                        </Link>
                      )}
                    </TD>
                    <TD align="right">
                      {String(line.quantity)} {line.unit_symbol ?? ""}
                    </TD>
                    <TD align="right">
                      {formatRupees(line.unit_rate)}
                      {line.unit_symbol ? ` / ${line.unit_symbol}` : ""}
                    </TD>
                    <TD align="right" className="font-medium text-slate-900">
                      {formatRupees(line.line_total)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>

          <dl className="ml-auto grid max-w-sm grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
            <dt className="text-slate-500">Subtotal</dt>
            <dd className="text-right tabular-nums">{formatRupees(bill.subtotal)}</dd>
            <dt className="text-slate-500">Discount</dt>
            <dd className="text-right tabular-nums">− {formatRupees(bill.discount)}</dd>
            <dt className="text-slate-500">Extra charges</dt>
            <dd className="text-right tabular-nums">+ {formatRupees(bill.extra_charges)}</dd>
            <div aria-hidden className="col-span-2 my-1 border-t border-slate-200" />
            <dt className="font-semibold text-slate-900">Bill total</dt>
            <dd className="text-right font-semibold text-slate-900 tabular-nums">
              {formatRupees(bill.grand_total)}
            </dd>
          </dl>

          {bill.remarks && (
            <p className="rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">
              {bill.remarks}
            </p>
          )}

          <section aria-labelledby="bill-payments-heading" className="space-y-2">
            <h3 id="bill-payments-heading" className="text-sm font-semibold text-slate-900">
              Payments
            </h3>
            {data.payments.length ? (
              <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                {data.payments.map((payment) => (
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
            ) : (
              <p className="text-sm text-slate-500">No payments recorded for this bill.</p>
            )}
          </section>

          <BillReceivingPanel purchaseId={bill.id} />

          <BillAttachments purchaseId={bill.id} canUpload={canUpload} />
        </div>
      )}
    </Modal>
  );
}
