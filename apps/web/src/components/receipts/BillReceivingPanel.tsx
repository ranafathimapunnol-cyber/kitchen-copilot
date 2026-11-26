"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PackagePlus } from "lucide-react";

import { api } from "@/lib/api/client";
import { billReceivingEndpoint } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/payments";
import { formatQuantity, toMilli } from "@/lib/receiptMath";
import { canViewOrders } from "@/lib/purchaseOrders";
import {
  RECEIPT_STATUS_LABELS,
  RECEIPT_STATUSES,
  canRecordReceipts,
  canViewReceipts,
  type Receiving,
} from "@/lib/receipts";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import { Spinner } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

/**
 * A bill's receiving progress (PUR03), shown inside the bill detail to users
 * who may view receipts (inventory.read). Renders nothing for others.
 */
export default function BillReceivingPanel({ purchaseId }: { purchaseId: number }) {
  const { role, permissions } = useAuthorization();
  const canView = canViewReceipts(role, permissions);
  const canRecord = canRecordReceipts(role, permissions);

  const [data, setData] = useState<Receiving | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!canView) return;
    let active = true;
    api
      .get<Receiving>(billReceivingEndpoint(purchaseId))
      .then((response) => {
        if (active) setData(response);
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load receiving progress."));
      });
    return () => {
      active = false;
    };
  }, [purchaseId, canView]);

  // Nothing to receive on a bill without item lines.
  if (!canView || data?.lines.length === 0) return null;

  const counts = data?.receipt_counts;
  // Purchase-order information only for users with order access (never STAFF).
  const canSeeOrders = canViewOrders(role, permissions);
  const showOrdered = canSeeOrders && (data?.lines.some((line) => line.ordered_quantity) ?? false);
  const receiptCount = counts ? RECEIPT_STATUSES.reduce((sum, status) => sum + counts[status], 0) : 0;
  const leftToReceive = data?.lines.some((line) => (toMilli(line.remaining_quantity) ?? 0) > 0) ?? false;

  return (
    <section aria-labelledby="bill-receiving-heading" className="space-y-2" data-bill-receiving>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="bill-receiving-heading" className="text-sm font-semibold text-slate-900">
          Receiving
          {canSeeOrders && data?.purchase_order_number && (
            <span className="ml-2 font-normal text-slate-500">against {data.purchase_order_number}</span>
          )}
        </h3>
        <div className="flex items-center gap-3 text-sm">
          {receiptCount > 0 && (
            <Link href={`/dashboard/receipts?bill=${purchaseId}`} className="font-medium text-brand-700 hover:underline">
              {receiptCount} receipt{receiptCount === 1 ? "" : "s"}
            </Link>
          )}
          {canRecord && leftToReceive && (
            <Link
              href={`/dashboard/receipts/new?bill=${purchaseId}`}
              className="inline-flex items-center gap-1.5 font-medium text-brand-700 hover:underline"
            >
              <PackagePlus size={14} aria-hidden />
              Record receipt
            </Link>
          )}
        </div>
      </div>

      {error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : !data ? (
        <div className="flex justify-center py-3">
          <Spinner />
        </div>
      ) : (
        <>
          <Table minWidth={showOrdered ? "640px" : "560px"}>
            <THead>
              <tr>
                <TH>Item</TH>
                {showOrdered && <TH align="right">Ordered</TH>}
                <TH align="right">Billed</TH>
                <TH align="right">Received</TH>
                <TH align="right">Accepted</TH>
                <TH align="right">Rejected</TH>
                <TH align="right">In drafts</TH>
                <TH align="right">Left</TH>
              </tr>
            </THead>
            <TBody>
              {data.lines.map((line) => {
                const unit = line.unit_symbol ?? "";
                return (
                  <TR key={line.purchase_item_id}>
                    <TD className="font-medium text-slate-900">{line.item_name}</TD>
                    {showOrdered && (
                      <TD align="right" className="whitespace-nowrap tabular-nums text-slate-500">
                        {line.ordered_quantity ? `${formatQuantity(line.ordered_quantity)} ${unit}` : "—"}
                      </TD>
                    )}
                    <TD align="right" className="whitespace-nowrap tabular-nums">
                      {formatQuantity(line.billed_quantity)} {unit}
                    </TD>
                    <TD align="right" className="whitespace-nowrap tabular-nums">
                      {formatQuantity(line.received_quantity)} {unit}
                    </TD>
                    <TD align="right" className="whitespace-nowrap tabular-nums text-emerald-700">
                      {formatQuantity(line.accepted_quantity)} {unit}
                    </TD>
                    <TD align="right" className="whitespace-nowrap tabular-nums text-red-700">
                      {formatQuantity(line.rejected_quantity)} {unit}
                    </TD>
                    <TD align="right" className="whitespace-nowrap tabular-nums text-slate-500">
                      {formatQuantity(line.in_draft_quantity)} {unit}
                    </TD>
                    <TD align="right" className="whitespace-nowrap tabular-nums font-medium text-slate-900">
                      {formatQuantity(line.remaining_quantity)} {unit}
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
          {(data.outsourced_lines?.length ?? 0) > 0 && (
            <p className="text-xs text-slate-600" data-outsourced-note>
              Outsourced food on this bill ({data.outsourced_lines!.map((line) => line.item_name).join(", ")}) is received
              as outsourced deliveries, never into stock.
            </p>
          )}
          <p className="text-xs text-slate-500">
            {data.fully_received
              ? "Everything billed has been received."
              : counts && counts.DRAFT > 0
                ? `${counts.DRAFT} draft receipt${counts.DRAFT === 1 ? "" : "s"} waiting for acceptance. Drafts do not change stock.`
                : `${RECEIPT_STATUS_LABELS.ACCEPTED} receipts add their accepted quantities to stock.`}
          </p>
        </>
      )}
    </section>
  );
}
