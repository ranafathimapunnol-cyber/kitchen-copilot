"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Ban,
  CircleCheckBig,
  ClipboardList,
  FilePlus2,
  History,
  PencilLine,
  Send,
  TriangleAlert,
} from "lucide-react";

import { api } from "@/lib/api/client";
import { purchaseOrderActionEndpoint, purchaseOrderEndpoint } from "@/lib/api/endpoints";
import { orderPayload, trimQuantity, type OrderDraft } from "@/lib/orderForm";
import { canEnterBills, errorMessage, formatDateTime, formatDay } from "@/lib/payments";
import { HISTORY_LABELS, canManageOrders, type OrderDetail } from "@/lib/purchaseOrders";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import { OrderStatusBadge, ReceivingBadge } from "@/components/orders/OrderBadges";
import OrderForm from "@/components/orders/OrderForm";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { Field, TextArea } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

type ReasonAction = "close" | "cancel";

const q = (value: string, unit: string | null) => `${trimQuantity(value)} ${unit ?? ""}`.trim();

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-900">{children}</dd>
    </div>
  );
}

function toDraft(order: OrderDetail): OrderDraft {
  return {
    supplierId: String(order.supplier_id),
    orderDate: order.order_date,
    expectedDate: order.expected_date ?? "",
    remarks: order.remarks ?? "",
    lines: order.items.map((line) => ({
      itemId: String(line.item_id),
      quantity: trimQuantity(line.ordered_quantity),
      unitId: String(line.unit_id),
      remarks: line.remarks ?? "",
    })),
  };
}

export default function PurchaseOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const orderId = Number(params.id);
  const valid = Number.isInteger(orderId) && orderId > 0;
  const toast = useToast();
  const { role, permissions } = useAuthorization();
  const canManage = canManageOrders(role, permissions);
  const canBill = canEnterBills(role, permissions);

  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [confirmPlace, setConfirmPlace] = useState(false);
  const [reasonAction, setReasonAction] = useState<ReasonAction | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState("");

  useEffect(() => {
    if (!valid) return;
    let active = true;
    api
      .get<OrderDetail>(purchaseOrderEndpoint(orderId))
      .then((response) => {
        if (!active) return;
        setOrder(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load this purchase order."));
      });
    return () => {
      active = false;
    };
  }, [orderId, valid, reloadKey]);

  async function saveEdit(draft: OrderDraft) {
    const updated = await api.put<OrderDetail>(purchaseOrderEndpoint(orderId), orderPayload(draft));
    setOrder(updated);
    setEditing(false);
    toast.success(`Draft ${updated.order_number} updated.`);
  }

  function place() {
    setBusy(true);
    setActionError("");
    api
      .post<OrderDetail>(purchaseOrderActionEndpoint(orderId, "place"))
      .then((updated) => {
        setOrder(updated);
        toast.success(`${updated.order_number} placed with ${updated.supplier_name ?? "the supplier"}.`);
      })
      .catch((err: unknown) => setActionError(errorMessage(err, "The order could not be placed.")))
      .finally(() => {
        setBusy(false);
        setConfirmPlace(false);
      });
  }

  function submitReason() {
    if (!reasonAction) return;
    if (!reason.trim()) {
      setReasonError(reasonAction === "close" ? "Say why the order is being closed." : "Say why the order is being cancelled.");
      return;
    }
    setBusy(true);
    setReasonError("");
    api
      .post<OrderDetail>(purchaseOrderActionEndpoint(orderId, reasonAction), { reason: reason.trim() })
      .then((updated) => {
        setOrder(updated);
        toast.success(`${updated.order_number} ${reasonAction === "close" ? "closed" : "cancelled"}.`);
        setReasonAction(null);
        setReason("");
      })
      .catch((err: unknown) => setReasonError(errorMessage(err, "The order could not be updated.")))
      .finally(() => setBusy(false));
  }

  const backLink = (
    <Link
      href="/dashboard/purchase-orders"
      className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
    >
      <ArrowLeft size={15} aria-hidden />
      All orders
    </Link>
  );

  if (error || !valid) {
    return (
      <div className="space-y-6 pb-6">
        <PageHeader eyebrow="Purchasing" icon={ClipboardList} title="Purchase order" actions={backLink} />
        <Card>
          <ErrorState
            title="Couldn't open this order"
            message={error || "This order was not found."}
            onRetry={() => setReloadKey((key) => key + 1)}
          />
        </Card>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="space-y-6 pb-6">
        <PageHeader eyebrow="Purchasing" icon={ClipboardList} title="Purchase order" actions={backLink} />
        <Card>
          <TableSkeleton rows={4} columns={7} />
        </Card>
      </div>
    );
  }

  if (editing) {
    return (
      <div className="space-y-6 pb-6">
        <PageHeader
          eyebrow="Purchasing"
          icon={PencilLine}
          title={`Edit draft ${order.order_number}`}
          description="Only drafts can be edited. The previous values are kept in the order's history."
          actions={
            <Button variant="secondary" onClick={() => setEditing(false)}>
              Discard changes
            </Button>
          }
        />
        <OrderForm
          initial={toDraft(order)}
          submitLabel="Save changes"
          cancelHref={`/dashboard/purchase-orders/${order.id}`}
          onSubmit={saveEdit}
        />
      </div>
    );
  }

  const actions = order.actions;
  const showReceiving = order.status === "PLACED" || order.status === "CLOSED";

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Purchasing"
        icon={ClipboardList}
        title={`Purchase order ${order.order_number}`}
        description={`${order.supplier_name ?? "Supplier"} · ordered ${formatDay(order.order_date)}${order.expected_date ? ` · expected ${formatDay(order.expected_date)}` : ""}`}
        meta={
          <span className="flex flex-wrap items-center gap-2">
            <OrderStatusBadge status={order.status} />
            {showReceiving && <ReceivingBadge state={order.receiving_state} />}
          </span>
        }
        actions={backLink}
      />

      {(canManage && (actions.edit || actions.place || actions.close || actions.cancel)) || (canBill && actions.bill) ? (
        <Card className={order.status === "DRAFT" ? "border-amber-200 bg-amber-50/60" : undefined}>
          <div className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
            <p className="text-sm text-slate-700">
              {order.status === "DRAFT"
                ? "This order is a draft. Edit it as needed, then place it once it has been sent to the supplier."
                : "This order is placed. Enter the supplier's bills against it; receipts against those bills show what has arrived."}
            </p>
            <div className="flex flex-wrap gap-2">
              {canManage && actions.edit && (
                <Button variant="secondary" icon={<PencilLine size={15} aria-hidden />} onClick={() => setEditing(true)} disabled={busy}>
                  Edit draft
                </Button>
              )}
              {canBill && actions.bill && (
                <Link
                  href={`/dashboard/supplier-bills/new?supplier=${order.supplier_id}&order=${order.id}`}
                  className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
                >
                  <FilePlus2 size={15} aria-hidden />
                  Enter bill against this order
                </Link>
              )}
              {canManage && actions.cancel && (
                <Button variant="ghost" icon={<Ban size={15} aria-hidden />} onClick={() => setReasonAction("cancel")} disabled={busy}>
                  Cancel order
                </Button>
              )}
              {canManage && actions.close && (
                <Button variant="secondary" icon={<CircleCheckBig size={15} aria-hidden />} onClick={() => setReasonAction("close")} disabled={busy}>
                  Close order
                </Button>
              )}
              {canManage && actions.place && (
                <Button icon={<Send size={15} aria-hidden />} onClick={() => setConfirmPlace(true)} disabled={busy}>
                  Place order
                </Button>
              )}
            </div>
          </div>
        </Card>
      ) : null}

      {actionError && (
        <Alert tone="error" title="Not done">
          {actionError}
        </Alert>
      )}
      {order.status === "CLOSED" && (
        <Alert tone="success" title="Closed">
          Closed by {order.closed_by_name ?? "a user"} on {formatDateTime(order.closed_at)}
          {order.close_reason ? `: “${order.close_reason}”` : "."}
        </Alert>
      )}
      {order.status === "CANCELLED" && (
        <Alert tone="warning" title="Cancelled">
          Cancelled by {order.cancelled_by_name ?? "a user"} on {formatDateTime(order.cancelled_at)}
          {order.cancel_reason ? `: “${order.cancel_reason}”` : "."}
        </Alert>
      )}
      {order.over_billed && (
        <Alert tone="warning" title="Billed more than ordered">
          At least one line has been billed beyond the ordered quantity. The bills were recorded as the supplier issued them.
        </Alert>
      )}

      <Card>
        <dl className="grid grid-cols-1 gap-5 p-5 sm:grid-cols-2 lg:grid-cols-4">
          <Detail label="Supplier">{order.supplier_name}</Detail>
          <Detail label="Ordered">
            {formatDay(order.order_date)}
            {order.expected_date && <span className="block text-slate-500">expected {formatDay(order.expected_date)}</span>}
          </Detail>
          <Detail label="Created">
            {order.created_by_name ?? "—"}
            <span className="block text-slate-500">{formatDateTime(order.created_at)}</span>
          </Detail>
          <Detail label="Placed">
            {order.placed_at ? (
              <>
                {order.placed_by_name ?? "—"}
                <span className="block text-slate-500">{formatDateTime(order.placed_at)}</span>
              </>
            ) : (
              <span className="text-slate-400">Not yet</span>
            )}
          </Detail>
          {order.remarks && (
            <div className="sm:col-span-2 lg:col-span-4">
              <Detail label="Remarks">{order.remarks}</Detail>
            </div>
          )}
        </dl>
      </Card>

      <Card>
        <CardHeader
          title="Ordered, billed and received"
          subtitle="In each order line's unit. Billed comes from bills entered against this order; received from their accepted goods receipts."
          icon={ClipboardList}
        />
        <Table minWidth="980px">
          <THead>
            <tr>
              <TH>Item</TH>
              <TH align="right">Ordered</TH>
              <TH align="right">Billed</TH>
              <TH align="right">Received</TH>
              <TH align="right">Accepted</TH>
              <TH align="right">Rejected</TH>
              <TH align="right">In drafts</TH>
              <TH align="right">Left to receive</TH>
            </tr>
          </THead>
          <TBody>
            {order.items.map((line) => {
              const over = Number(line.over_billed) > 0;
              return (
                <TR key={line.id}>
                  <TD>
                    <div className="font-medium text-slate-900">{line.item_name}</div>
                    {line.category_name && <div className="text-xs text-slate-500">{line.category_name}</div>}
                    {line.remarks && <div className="text-xs text-slate-500">{line.remarks}</div>}
                    {line.unconvertible && (
                      <div className="text-xs text-amber-700">Some bill lines use a unit that cannot be converted.</div>
                    )}
                  </TD>
                  <TD align="right" className="whitespace-nowrap tabular-nums font-medium text-slate-900">
                    {q(line.ordered_quantity, line.unit_symbol)}
                  </TD>
                  <TD align="right" className="whitespace-nowrap tabular-nums">
                    {q(line.billed_quantity, line.unit_symbol)}
                    {over && (
                      <span className="mt-0.5 flex items-center justify-end gap-1 text-xs font-medium text-amber-700" data-line-over-billed>
                        <TriangleAlert size={12} aria-hidden />
                        {q(line.over_billed, line.unit_symbol)} over
                      </span>
                    )}
                  </TD>
                  <TD align="right" className="whitespace-nowrap tabular-nums">
                    {q(line.received_quantity, line.unit_symbol)}
                  </TD>
                  <TD align="right" className="whitespace-nowrap tabular-nums text-emerald-700">
                    {q(line.accepted_quantity, line.unit_symbol)}
                  </TD>
                  <TD align="right" className="whitespace-nowrap tabular-nums text-red-700">
                    {q(line.rejected_quantity, line.unit_symbol)}
                  </TD>
                  <TD align="right" className="whitespace-nowrap tabular-nums text-slate-500">
                    {q(line.in_draft_quantity, line.unit_symbol)}
                  </TD>
                  <TD align="right" className="whitespace-nowrap tabular-nums font-medium text-slate-900">
                    {q(line.left_to_receive, line.unit_symbol)}
                  </TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Bills against this order" icon={FilePlus2} />
          {order.bills.length === 0 ? (
            <p className="px-5 pb-5 text-sm text-slate-600">
              {order.status === "PLACED" ? "No bill has been entered against this order yet." : "No bills."}
            </p>
          ) : (
            <ul className="divide-y divide-slate-100 border-t border-slate-100" data-order-bills>
              {order.bills.map((bill) => (
                <li key={bill.purchase_id} className="flex items-center justify-between px-5 py-3 text-sm">
                  <span className="font-medium text-slate-900">{bill.invoice_number}</span>
                  <span className="text-slate-500">{formatDay(bill.purchase_date)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <CardHeader title="History" icon={History} />
          <ol className="space-y-3 border-t border-slate-100 px-5 py-4" data-order-history>
            {order.history.map((entry, index) => (
              <li key={index} className="text-sm">
                <span className="font-medium text-slate-900">{HISTORY_LABELS[entry.action] ?? entry.action}</span>
                <span className="text-slate-500">
                  {" "}· {entry.user_name} · {formatDateTime(entry.at)}
                </span>
                {entry.reason && <p className="text-slate-600">“{entry.reason}”</p>}
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <ConfirmDialog
        open={confirmPlace}
        tone="warning"
        title={`Place ${order.order_number}?`}
        description="Placing records that the order was sent to the supplier. It can no longer be edited; bills can then be entered against it."
        confirmLabel="Place order"
        busy={busy}
        onConfirm={place}
        onCancel={() => setConfirmPlace(false)}
      />

      <Modal
        open={reasonAction !== null}
        onClose={() => (busy ? undefined : setReasonAction(null))}
        title={reasonAction === "close" ? `Close ${order.order_number}?` : `Cancel ${order.order_number}?`}
        description={
          reasonAction === "close"
            ? "No more deliveries will be expected against this order. What was still outstanding is recorded with your reason."
            : "The order is kept as cancelled with your reason. Orders with bills against them are closed instead."
        }
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setReasonAction(null)} disabled={busy}>
              Keep order
            </Button>
            <Button variant={reasonAction === "cancel" ? "warning" : "primary"} loading={busy} onClick={submitReason}>
              {reasonAction === "close" ? "Close order" : "Cancel order"}
            </Button>
          </>
        }
      >
        <Field label="Reason" required error={reasonError}>
          {({ id, describedBy }) => (
            <TextArea
              id={id}
              rows={3}
              maxLength={500}
              aria-describedby={describedBy}
              value={reason}
              placeholder={reasonAction === "close" ? "e.g. All delivered, or: supplier cannot supply the rest" : "e.g. Ordered by mistake"}
              onChange={(event) => setReason(event.target.value)}
            />
          )}
        </Field>
      </Modal>
    </div>
  );
}
