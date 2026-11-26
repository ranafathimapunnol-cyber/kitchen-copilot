"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Ban,
  CircleCheck,
  FileText,
  History,
  Link2,
  Link2Off,
  PencilLine,
  Send,
  Soup,
  Truck,
  UtensilsCrossed,
} from "lucide-react";

import { api } from "@/lib/api/client";
import {
  OUTSOURCED_OPTIONS_ENDPOINT,
  outsourcedDeliveryActionEndpoint,
  outsourcedLineBillEndpoint,
  outsourcedOrderActionEndpoint,
  outsourcedOrderEndpoint,
} from "@/lib/api/endpoints";
import {
  HISTORY_LABELS,
  Q6_NOTE,
  type OutsourcedDelivery,
  type OutsourcedHistoryEntry,
  type OutsourcedOptions,
  type OutsourcedOrderDetail,
  type OutsourcedOrderLine,
} from "@/lib/outsourced";
import { orderPayload, type OrderDraft } from "@/lib/outsourcedMath";
import { errorMessage, formatDateTime, formatDay, formatRupees } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import ReasonModal from "@/components/kitchen/ReasonModal";
import BillLinkModal from "@/components/outsourced/BillLinkModal";
import DeliveryModal from "@/components/outsourced/DeliveryModal";
import {
  DeliveryStatusBadge,
  MealLinkBadge,
  OutsourcedReceivingBadge,
  OutsourcedStatusBadge,
} from "@/components/outsourced/OutsourcedBadges";
import OutsourcedOrderForm from "@/components/outsourced/OutsourcedOrderForm";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import PageHeader from "@/components/ui/PageHeader";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

type Dialog =
  | { kind: "place" }
  | { kind: "cancel-order" }
  | { kind: "delivery"; delivery?: OutsourcedDelivery }
  | { kind: "confirm-delivery"; delivery: OutsourcedDelivery }
  | { kind: "cancel-delivery"; delivery: OutsourcedDelivery }
  | { kind: "link"; line: OutsourcedOrderLine }
  | { kind: "unlink"; line: OutsourcedOrderLine }
  | null;

const q = (value: string | null | undefined, unit: string | null) => `${plainQuantity(value)} ${unit ?? ""}`.trim();

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm break-words text-slate-900">{children}</dd>
    </div>
  );
}

function toDraft(order: OutsourcedOrderDetail): OrderDraft {
  return {
    orderDate: order.order_date,
    mealDate: order.meal_date,
    sessionId: String(order.meal_session_id),
    supplierId: String(order.supplier_id),
    notes: order.notes ?? "",
    lines: order.lines.map((line) => ({
      itemId: String(line.item_id),
      quantity: plainQuantity(line.ordered_quantity),
      unitId: String(line.unit_id),
      rate: line.unit_rate ? String(Number(line.unit_rate)) : "",
      remarks: line.remarks ?? "",
    })),
  };
}

export default function OutsourcedOrderPage() {
  const params = useParams<{ id: string }>();
  const orderId = Number(params.id);
  const valid = Number.isInteger(orderId) && orderId > 0;
  const toast = useToast();
  const [order, setOrder] = useState<OutsourcedOrderDetail | null>(null);
  const [options, setOptions] = useState<OutsourcedOptions | null>(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [editing, setEditing] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [history, setHistory] = useState<OutsourcedHistoryEntry[] | null>(null);

  useEffect(() => {
    if (!valid) return;
    let active = true;
    api
      .get<OutsourcedOrderDetail>(outsourcedOrderEndpoint(orderId))
      .then((response) => {
        if (!active) return;
        setOrder(response);
        setError("");
      })
      .catch((err: unknown) => active && setError(errorMessage(err, "Unable to load this outsourced order.")));
    return () => {
      active = false;
    };
  }, [orderId, valid, reloadKey]);

  useEffect(() => {
    api.get<OutsourcedOptions>(OUTSOURCED_OPTIONS_ENDPOINT).then(setOptions).catch(() => setOptions(null));
  }, []);

  const adopt = useCallback((updated: OutsourcedOrderDetail) => {
    setOrder(updated);
    setHistory(null);
  }, []);

  async function run(call: () => Promise<OutsourcedOrderDetail>, done: string) {
    setBusy(true);
    setActionError("");
    try {
      adopt(await call());
      toast.success(done);
    } catch (err: unknown) {
      setActionError(errorMessage(err, "The request failed."));
    } finally {
      setBusy(false);
      setDialog(null);
    }
  }

  async function loadHistory() {
    try {
      setHistory((await api.get<{ items: OutsourcedHistoryEntry[] }>(outsourcedOrderActionEndpoint(orderId, "history"))).items);
    } catch (err: unknown) {
      setActionError(errorMessage(err, "Unable to load the history."));
    }
  }

  const backLink = (
    <Link
      href="/dashboard/outsourced-food"
      className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
    >
      <ArrowLeft size={15} aria-hidden />
      All orders
    </Link>
  );

  if (error || !valid) {
    return (
      <div className="space-y-6 pb-6">
        <PageHeader eyebrow="Operations" icon={Soup} title="Outsourced order" actions={backLink} />
        <Card>
          <ErrorState title="Couldn't open this order" message={error || "This order was not found."}
            onRetry={() => setReloadKey((key) => key + 1)} />
        </Card>
      </div>
    );
  }
  if (!order) {
    return (
      <div className="space-y-6 pb-6">
        <PageHeader eyebrow="Operations" icon={Soup} title="Outsourced order" actions={backLink} />
        <Card><TableSkeleton rows={4} columns={7} /></Card>
      </div>
    );
  }

  if (editing) {
    return (
      <div className="space-y-6 pb-6">
        <PageHeader eyebrow="Operations" icon={PencilLine} title={`Edit draft ${order.order_number}`}
          description="Only drafts can be edited. The previous values are kept in the order's history."
          actions={<Button variant="secondary" onClick={() => setEditing(false)}>Discard changes</Button>} />
        <OutsourcedOrderForm
          initial={toDraft(order)}
          submitLabel="Save changes"
          cancelHref={`/dashboard/outsourced-food/${order.id}`}
          onSubmit={async (draft) => {
            adopt(await api.put<OutsourcedOrderDetail>(outsourcedOrderEndpoint(order.id), orderPayload(draft)));
            setEditing(false);
            toast.success("Draft updated.");
          }}
        />
      </div>
    );
  }

  const perms = order.permissions;
  const costs = order.costs_visible;
  const showActions = perms.can_edit || perms.can_place || perms.can_cancel || perms.can_record_delivery;
  const confirmedCount = order.deliveries.filter((d) => d.status === "CONFIRMED").length;
  const draftCount = order.deliveries.filter((d) => d.status === "DRAFT").length;
  const pendingClosed = order.meal_link_state === "PENDING_CLOSED";
  const pendingNoRecord = order.meal_link_state === "PENDING_NO_RECORD";

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Operations"
        icon={Soup}
        title={`Outsourced order ${order.order_number}`}
        description={`${order.supplier_name ?? "Supplier"} · ${order.meal_session_name} on ${formatDay(order.meal_date)} · ordered ${formatDay(order.order_date)}`}
        meta={
          <span className="flex flex-wrap items-center gap-2">
            <OutsourcedStatusBadge status={order.status} />
            {order.receiving_status && <OutsourcedReceivingBadge status={order.receiving_status} />}
            {order.meal_link_state && <MealLinkBadge state={order.meal_link_state} />}
          </span>
        }
        actions={backLink}
      />

      {showActions && (
        <Card className={order.status === "DRAFT" ? "border-amber-200 bg-amber-50/60" : undefined}>
          <div className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
            <p className="text-sm text-slate-700">
              {order.status === "DRAFT"
                ? "This order is a draft. Edit it as needed, then mark it ordered once it has been sent to the supplier."
                : "Record each delivery with what was received and rejected, then confirm it. Confirmed food is added to the meal record automatically."}
            </p>
            <div className="flex flex-wrap gap-2">
              {perms.can_edit && (
                <Button variant="secondary" icon={<PencilLine size={15} aria-hidden />} disabled={busy} onClick={() => setEditing(true)}>
                  Edit draft
                </Button>
              )}
              {perms.can_cancel && (
                <Button variant="ghost" icon={<Ban size={15} aria-hidden />} disabled={busy} onClick={() => setDialog({ kind: "cancel-order" })}>
                  Cancel order
                </Button>
              )}
              {perms.can_place && (
                <Button icon={<Send size={15} aria-hidden />} disabled={busy} onClick={() => setDialog({ kind: "place" })}>
                  Mark as ordered
                </Button>
              )}
              {perms.can_record_delivery && (
                <Button icon={<Truck size={15} aria-hidden />} disabled={busy} onClick={() => setDialog({ kind: "delivery" })}>
                  Record delivery
                </Button>
              )}
            </div>
          </div>
        </Card>
      )}

      {actionError && <Alert tone="error" title="Not done" onDismiss={() => setActionError("")}>{actionError}</Alert>}
      {order.status === "CANCELLED" && (
        <Alert tone="warning" title="Cancelled">
          Cancelled by {order.cancelled_by_name ?? "a user"} on {formatDateTime(order.cancelled_at)}
          {order.cancellation_reason ? `: “${order.cancellation_reason}”` : "."}
        </Alert>
      )}
      {pendingClosed && order.meal_record && (
        <Alert tone="warning" title="Reconciliation pending">
          The meal record of {order.meal_session_name} on {formatDay(order.meal_date)} is closed, so confirmed food from this
          order was not added to it; a closed record is never changed.{" "}
          <Link href={`/dashboard/meals/${order.meal_record.id}`} className="font-medium underline">Open the meal record</Link>
          {" "}— an Admin or Kitchen Manager can reopen it with a reason, and the food is then added automatically.
        </Alert>
      )}
      {pendingNoRecord && (
        <Alert tone="info" title="Waiting for the meal record">
          No meal record exists yet for {order.meal_session_name} on {formatDay(order.meal_date)}. The confirmed food is added
          to it as soon as it is recorded under Meals.
        </Alert>
      )}
      {order.session_warnings.map((warning) => (
        <Alert key={warning} tone="warning" title="Not linked">{warning}</Alert>
      ))}
      {order.rejection_note && (
        <Alert tone="warning" title="Rejected food recorded">{Q6_NOTE}</Alert>
      )}

      <Card>
        <dl className="grid grid-cols-1 gap-5 p-5 sm:grid-cols-2 lg:grid-cols-4">
          <Fact label="Meal">
            {order.meal_session_name}
            <span className="block text-slate-500">{formatDay(order.meal_date)}</span>
          </Fact>
          <Fact label="Meal record">
            {order.meal_record ? (
              <Link href={`/dashboard/meals/${order.meal_record.id}`} className="inline-flex items-center gap-1 font-medium text-brand-700 hover:underline" data-meal-record-link>
                <UtensilsCrossed size={14} aria-hidden />
                #{order.meal_record.id} · {order.meal_record.status.toLowerCase()}
              </Link>
            ) : (
              <span className="text-slate-500">Not recorded yet</span>
            )}
          </Fact>
          <Fact label="Created">
            {order.created_by_name ?? "—"}
            <span className="block text-slate-500">{formatDateTime(order.created_at)}</span>
          </Fact>
          <Fact label="Ordered">
            {order.ordered_at ? (
              <>
                {order.ordered_by_name ?? "—"}
                <span className="block text-slate-500">{formatDateTime(order.ordered_at)}</span>
              </>
            ) : <span className="text-slate-400">Not yet</span>}
          </Fact>
          {costs && (
            <>
              <Fact label="Planned cost (order)">{formatRupees(order.planned_total ?? "0")}</Fact>
              <Fact label="Billed (linked bill lines)">{formatRupees(order.billed_total ?? "0")}</Fact>
            </>
          )}
          <Fact label="Deliveries">
            {confirmedCount} confirmed{draftCount ? ` · ${draftCount} draft` : ""}
          </Fact>
          {order.notes && (
            <div className="sm:col-span-2 lg:col-span-4"><Fact label="Notes">{order.notes}</Fact></div>
          )}
        </dl>
      </Card>

      <Card>
        <CardHeader
          title="Ordered, received and accepted"
          subtitle="In each line's unit. Received, rejected and accepted come from confirmed deliveries; drafts hold their quantity until confirmed or cancelled."
          icon={Soup}
        />
        <Table minWidth={costs ? "1180px" : "900px"}>
          <THead>
            <tr>
              <TH>Food</TH>
              <TH align="right">Ordered</TH>
              <TH align="right">Received</TH>
              <TH align="right">Rejected</TH>
              <TH align="right">Accepted</TH>
              <TH align="right">In drafts</TH>
              <TH align="right">Still to receive</TH>
              {costs && <TH align="right">Rate · planned</TH>}
              {costs && <TH>Supplier bill</TH>}
            </tr>
          </THead>
          <TBody>
            {order.lines.map((line) => (
              <TR key={line.id}>
                <TD>
                  <div className="font-medium text-slate-900">{line.item_name}</div>
                  {line.remarks && <div className="text-xs text-slate-500">{line.remarks}</div>}
                </TD>
                <TD align="right" className="whitespace-nowrap tabular-nums font-medium">{q(line.ordered_quantity, line.unit_symbol)}</TD>
                <TD align="right" className="whitespace-nowrap tabular-nums">{q(line.received_quantity, line.unit_symbol)}</TD>
                <TD align="right" className="whitespace-nowrap tabular-nums text-red-700">{q(line.rejected_quantity, line.unit_symbol)}</TD>
                <TD align="right" className="whitespace-nowrap tabular-nums text-emerald-700">{q(line.accepted_quantity, line.unit_symbol)}</TD>
                <TD align="right" className="whitespace-nowrap tabular-nums text-slate-500">{q(line.in_draft_quantity, line.unit_symbol)}</TD>
                <TD align="right" className="whitespace-nowrap tabular-nums font-medium">{q(line.remaining_quantity, line.unit_symbol)}</TD>
                {costs && (
                  <TD align="right" className="whitespace-nowrap tabular-nums">
                    {formatRupees(line.unit_rate ?? "0")}
                    <div className="text-xs text-slate-500">{formatRupees(line.line_total ?? "0")}</div>
                  </TD>
                )}
                {costs && (
                  <TD className="whitespace-nowrap">
                    {line.bill_line ? (
                      <div className="text-sm" data-bill-link>
                        <span className="font-medium text-slate-900">{line.bill_line.invoice_number}</span>
                        <span className="text-slate-500"> · {formatRupees(line.bill_line.line_total)}</span>
                        {perms.can_link_bill && (
                          <Button size="sm" variant="ghost" icon={<Link2Off size={14} aria-hidden />} disabled={busy}
                            onClick={() => setDialog({ kind: "unlink", line })}>Unlink</Button>
                        )}
                      </div>
                    ) : perms.can_link_bill ? (
                      <Button size="sm" variant="secondary" icon={<Link2 size={14} aria-hidden />} disabled={busy}
                        onClick={() => setDialog({ kind: "link", line })}>Link bill line</Button>
                    ) : (
                      <span className="text-slate-400">Not linked</span>
                    )}
                  </TD>
                )}
              </TR>
            ))}
          </TBody>
        </Table>
      </Card>

      <Card>
        <CardHeader title="Deliveries" subtitle="Newest first. Rejected food is recorded with its reason; no credit or return is recorded (client question Q6)." icon={Truck} />
        {order.deliveries.length === 0 ? (
          <p className="px-5 pb-5 text-sm text-slate-600">
            {order.status === "ORDERED" ? "No delivery recorded yet." : order.status === "DRAFT" ? "Deliveries are recorded once the order is marked ordered." : "No deliveries."}
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 border-t border-slate-100" data-deliveries>
            {order.deliveries.map((delivery) => {
              const canChange = delivery.status === "DRAFT" && perms.can_update_delivery;
              const canCancel = (delivery.status === "DRAFT" && perms.can_update_delivery)
                || (delivery.status === "CONFIRMED" && perms.can_cancel_confirmed_delivery);
              return (
                <li key={delivery.id} className="space-y-3 px-5 py-4" data-delivery={delivery.delivery_number}>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-slate-900">{delivery.delivery_number}</span>
                      <DeliveryStatusBadge status={delivery.status} />
                      <span className="text-sm text-slate-500">
                        delivered {formatDay(delivery.delivery_date)} · recorded by {delivery.created_by_name ?? "—"}
                        {delivery.confirmed_at && ` · confirmed by ${delivery.confirmed_by_name ?? "—"} ${formatDateTime(delivery.confirmed_at)}`}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {canChange && (
                        <Button size="sm" variant="secondary" icon={<PencilLine size={14} aria-hidden />} disabled={busy}
                          onClick={() => setDialog({ kind: "delivery", delivery })}>Edit draft</Button>
                      )}
                      {canCancel && (
                        <Button size="sm" variant="ghost" icon={<Ban size={14} aria-hidden />} disabled={busy}
                          onClick={() => setDialog({ kind: "cancel-delivery", delivery })}>Cancel</Button>
                      )}
                      {canChange && (
                        <Button size="sm" icon={<CircleCheck size={14} aria-hidden />} disabled={busy}
                          onClick={() => setDialog({ kind: "confirm-delivery", delivery })}>Confirm delivery</Button>
                      )}
                    </div>
                  </div>
                  {delivery.status === "CANCELLED" && (
                    <p className="text-sm text-slate-600">
                      Cancelled by {delivery.cancelled_by_name ?? "—"} · {formatDateTime(delivery.cancelled_at)} · &ldquo;{delivery.cancellation_reason}&rdquo;
                    </p>
                  )}
                  {delivery.remarks && <p className="text-sm text-slate-600">{delivery.remarks}</p>}
                  <Table minWidth="820px">
                    <THead>
                      <tr>
                        <TH>Food</TH>
                        <TH align="right">Received</TH>
                        <TH align="right">Rejected</TH>
                        <TH align="right">Accepted</TH>
                        <TH>Reason for rejecting</TH>
                        <TH>Meal record</TH>
                      </tr>
                    </THead>
                    <TBody>
                      {delivery.lines.map((line) => (
                        <TR key={line.id}>
                          <TD className="font-medium text-slate-900">{line.item_name}</TD>
                          <TD align="right" className="whitespace-nowrap tabular-nums">{q(line.received_quantity, line.unit_symbol)}</TD>
                          <TD align="right" className="whitespace-nowrap tabular-nums text-red-700">{q(line.rejected_quantity, line.unit_symbol)}</TD>
                          <TD align="right" className="whitespace-nowrap tabular-nums text-emerald-700">{q(line.accepted_quantity, line.unit_symbol)}</TD>
                          <TD className="max-w-56 text-sm text-slate-600">{line.rejection_reason ?? "—"}</TD>
                          <TD className="max-w-72">
                            {line.meal_link ? (
                              <div className="space-y-1" data-meal-link={line.meal_link.state}>
                                <MealLinkBadge state={line.meal_link.state} />
                                {line.meal_link.meal_record && line.meal_link.state !== "PENDING_NO_RECORD" && (
                                  <Link href={`/dashboard/meals/${line.meal_link.meal_record.id}`} className="block text-xs text-brand-700 hover:underline">
                                    Meal record #{line.meal_link.meal_record.id}
                                  </Link>
                                )}
                                {line.meal_link.state.startsWith("PENDING") && (
                                  <p className="text-xs text-slate-600">{line.meal_link.message}</p>
                                )}
                              </div>
                            ) : <span className="text-slate-400">—</span>}
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader title="History" subtitle="Every change to the order and its deliveries, oldest first." icon={History} />
        <div className="px-5 pb-5">
          {history === null ? (
            <Button size="sm" variant="secondary" icon={<History size={14} aria-hidden />} onClick={loadHistory}>Show history</Button>
          ) : (
            <ol className="space-y-2 text-sm" aria-label="History" data-outsourced-history>
              {history.map((entry) => (
                <li key={entry.id} className="flex flex-wrap gap-x-2">
                  <span className="font-medium text-slate-900">
                    {entry.entity === "delivery" ? `${entry.delivery_number}: ` : ""}{HISTORY_LABELS[entry.action] ?? entry.action}
                  </span>
                  <span className="text-slate-500">{entry.user_name} · {formatDateTime(entry.created_at)}</span>
                  {typeof entry.details?.reason === "string" && <span className="text-slate-700">&ldquo;{entry.details.reason}&rdquo;</span>}
                </li>
              ))}
            </ol>
          )}
        </div>
      </Card>

      {costs && (
        <p className="flex items-center gap-1.5 text-xs text-slate-500">
          <FileText size={13} aria-hidden />
          The supplier&rsquo;s bill is the only payable: the planned cost is never added to expenditure.
        </p>
      )}

      {dialog?.kind === "delivery" && (
        <DeliveryModal key={dialog.delivery?.id ?? "new"} order={order} delivery={dialog.delivery} today={options?.today}
          onClose={() => setDialog(null)}
          onSaved={(updated) => {
            adopt(updated);
            setDialog(null);
            toast.success(dialog.delivery ? "Draft delivery updated." : "Delivery saved as a draft. Confirm it to add the food to the meal record.");
          }} />
      )}
      {dialog?.kind === "link" && (
        <BillLinkModal order={order} line={dialog.line} onClose={() => setDialog(null)}
          onSaved={(updated) => { adopt(updated); setDialog(null); toast.success("Bill line linked."); }} />
      )}
      <ConfirmDialog
        open={dialog?.kind === "place"}
        tone="warning"
        title={`Mark ${order.order_number} as ordered?`}
        description="Records that the order was sent to the supplier. It can no longer be edited; deliveries can then be recorded against it."
        confirmLabel="Mark as ordered"
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={() => run(() => api.post<OutsourcedOrderDetail>(outsourcedOrderActionEndpoint(order.id, "place")), `${order.order_number} marked as ordered.`)}
      />
      <ConfirmDialog
        open={dialog?.kind === "confirm-delivery"}
        tone="warning"
        title={dialog?.kind === "confirm-delivery" ? `Confirm ${dialog.delivery.delivery_number}?` : "Confirm delivery"}
        description={order.meal_record?.status === "OPEN"
          ? `The accepted food is added to the open meal record of ${order.meal_session_name} on ${formatDay(order.meal_date)}. The quantities can no longer be edited.`
          : order.meal_record?.status === "CLOSED"
            ? "The meal record of this date and session is closed, so the food will wait (reconciliation pending) until an Admin or Kitchen Manager reopens it. The quantities can no longer be edited."
            : "No meal record exists yet for this date and session; the food is added when it is recorded. The quantities can no longer be edited."}
        confirmLabel="Confirm delivery"
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={() => {
          if (dialog?.kind !== "confirm-delivery") return;
          run(() => api.post<OutsourcedOrderDetail>(outsourcedDeliveryActionEndpoint(dialog.delivery.id, "confirm")),
            `${dialog.delivery.delivery_number} confirmed.`);
        }}
      />
      <ConfirmDialog
        open={dialog?.kind === "unlink"}
        tone="danger"
        title="Unlink this bill line?"
        description="The bill itself is unchanged; this order line will show no billed cost until another bill line is linked."
        confirmLabel="Unlink"
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={() => {
          if (dialog?.kind !== "unlink") return;
          run(() => api.delete<OutsourcedOrderDetail>(outsourcedLineBillEndpoint(dialog.line.id, "bill-line")), "Bill line unlinked.");
        }}
      />
      {dialog?.kind === "cancel-order" && (
        <ReasonModal
          key="cancel-order"
          open
          title={`Cancel ${order.order_number}?`}
          description="The order is kept as cancelled with your reason. An order with deliveries or a linked bill line cannot be cancelled until those are cancelled or unlinked."
          confirmLabel="Cancel order"
          tone="danger"
          placeholder="e.g. Ordered by mistake"
          onClose={() => setDialog(null)}
          onSubmit={async (reason) => {
            adopt(await api.post<OutsourcedOrderDetail>(outsourcedOrderActionEndpoint(order.id, "cancel"), { reason }));
            setDialog(null);
            toast.success(`${order.order_number} cancelled.`);
          }}
        />
      )}
      {dialog?.kind === "cancel-delivery" && (
        <ReasonModal
          key={`cancel-${dialog.delivery.id}`}
          open
          title={`Cancel ${dialog.delivery.delivery_number}?`}
          description={dialog.delivery.status === "CONFIRMED"
            ? "Its food is removed from the open meal record. This is refused once any of it has been distributed, or while the meal record is closed: food that has been served cannot be un-delivered."
            : "The draft is kept as cancelled with your reason; its quantities are released."}
          confirmLabel="Cancel delivery"
          tone="danger"
          placeholder="e.g. Recorded against the wrong order"
          onClose={() => setDialog(null)}
          onSubmit={async (reason) => {
            const number = dialog.delivery.delivery_number;
            adopt(await api.post<OutsourcedOrderDetail>(outsourcedDeliveryActionEndpoint(dialog.delivery.id, "cancel"), { reason }));
            setDialog(null);
            toast.success(`${number} cancelled.`);
          }}
        />
      )}
    </div>
  );
}
