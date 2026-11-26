"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowLeftRight,
  Ban,
  CheckCircle2,
  PackageCheck,
  PencilLine,
  Save,
} from "lucide-react";

import { api } from "@/lib/api/client";
import {
  billReceivingEndpoint,
  receiptAcceptEndpoint,
  receiptCancelEndpoint,
  receiptEndpoint,
} from "@/lib/api/endpoints";
import { errorMessage, formatDateTime, formatDay, todayISO } from "@/lib/payments";
import {
  checkReceipt,
  formatQuantity,
  fromMilli,
  toMilli,
  type LineInput,
} from "@/lib/receiptMath";
import { canManageReceipts, type Receipt, type Receiving } from "@/lib/receipts";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import ReceiptLinesEditor, { type EditorLine } from "@/components/receipts/ReceiptLinesEditor";
import ReceiptStatusBadge from "@/components/receipts/ReceiptStatusBadge";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { Field, TextArea, TextInput } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

const exact = (text: string) => fromMilli(toMilli(text) ?? 0);

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-900">{children}</dd>
    </div>
  );
}

export default function ReceiptDetailPage() {
  const params = useParams<{ id: string }>();
  const receiptId = Number(params.id);
  const toast = useToast();
  const { role, permissions } = useAuthorization();
  const canManage = canManageReceipts(role, permissions);

  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [receiving, setReceiving] = useState<Receiving | null>(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const [editing, setEditing] = useState(false);
  const [inputs, setInputs] = useState<LineInput[]>([]);
  const [editDate, setEditDate] = useState("");
  const [editRemarks, setEditRemarks] = useState("");
  const [busy, setBusy] = useState<"" | "save" | "accept" | "cancel">("");
  const [actionError, setActionError] = useState("");
  const [confirmAccept, setConfirmAccept] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelError, setCancelError] = useState("");

  const load = useCallback(async () => {
    const next = await api.get<Receipt>(receiptEndpoint(receiptId));
    const progress =
      next.status === "DRAFT" ? await api.get<Receiving>(billReceivingEndpoint(next.purchase_id)) : null;
    return { next, progress };
  }, [receiptId]);

  useEffect(() => {
    if (!Number.isInteger(receiptId) || receiptId <= 0) return;
    let active = true;
    load()
      .then(({ next, progress }) => {
        if (!active) return;
        setReceipt(next);
        setReceiving(progress);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load this receipt."));
      });
    return () => {
      active = false;
    };
  }, [load, receiptId, reloadKey]);

  // For a draft being corrected: every bill line, with this draft's own
  // quantity given back to "left to receive" and taken out of "other drafts".
  const editorLines: EditorLine[] = useMemo(() => {
    if (!receipt || !receiving) return [];
    return receiving.lines.map((line, index) => {
      const own = receipt.items.find((item) => item.purchase_item_id === line.purchase_item_id);
      const ownMilli = own ? (toMilli(own.quantity_received) ?? 0) : 0;
      return {
        line: {
          ...line,
          in_draft_quantity: fromMilli(Math.max((toMilli(line.in_draft_quantity) ?? 0) - ownMilli, 0)),
        },
        remaining: fromMilli((toMilli(line.remaining_quantity) ?? 0) + ownMilli),
        input: inputs[index] ?? { received: "", accepted: "", rejected: "" },
      };
    });
  }, [receipt, receiving, inputs]);
  const editCheck = checkReceipt(editorLines);
  const today = todayISO();
  const editDateInvalid = !editDate || editDate > today;

  const classified =
    receipt?.items.every(
      (item) =>
        (toMilli(item.quantity_accepted) ?? 0) + (toMilli(item.quantity_rejected) ?? 0) ===
        (toMilli(item.quantity_received) ?? 0),
    ) ?? false;

  function startEditing() {
    if (!receipt || !receiving) return;
    setInputs(
      receiving.lines.map((line) => {
        const own = receipt.items.find((item) => item.purchase_item_id === line.purchase_item_id);
        return own
          ? {
              received: formatQuantity(own.quantity_received),
              accepted: formatQuantity(own.quantity_accepted),
              rejected: formatQuantity(own.quantity_rejected),
            }
          : { received: "", accepted: "", rejected: "" };
      }),
    );
    setEditDate(receipt.receipt_date);
    setEditRemarks(receipt.remarks ?? "");
    setActionError("");
    setEditing(true);
  }

  async function refresh(message: string) {
    const { next, progress } = await load();
    setReceipt(next);
    setReceiving(progress);
    toast.success(message);
  }

  function saveCorrection() {
    if (!receipt || !editCheck.canSave || editDateInvalid) return;
    setBusy("save");
    setActionError("");
    const items = editorLines
      .filter((_line, index) => editCheck.lines[index].included)
      .map(({ line, input }) => ({
        purchase_item_id: line.purchase_item_id,
        quantity_received: exact(input.received),
        quantity_accepted: exact(input.accepted),
        quantity_rejected: exact(input.rejected),
      }));
    api
      .put<Receipt>(receiptEndpoint(receipt.id), {
        receipt_date: editDate,
        remarks: editRemarks.trim() || null,
        items,
      })
      .then(() => refresh("Draft receipt corrected."))
      .then(() => setEditing(false))
      .catch((err: unknown) => setActionError(errorMessage(err, "The correction could not be saved.")))
      .finally(() => setBusy(""));
  }

  function accept() {
    if (!receipt) return;
    setBusy("accept");
    setActionError("");
    api
      .post<Receipt>(receiptAcceptEndpoint(receipt.id))
      .then(() => refresh(`Receipt GR-${receipt.id} accepted; stock updated.`))
      .catch((err: unknown) => setActionError(errorMessage(err, "The receipt could not be accepted.")))
      .finally(() => {
        setBusy("");
        setConfirmAccept(false);
      });
  }

  function cancelDraft() {
    if (!receipt) return;
    if (!cancelReason.trim()) {
      setCancelError("Give a reason for cancelling this draft.");
      return;
    }
    setBusy("cancel");
    setCancelError("");
    api
      .post<Receipt>(receiptCancelEndpoint(receipt.id), { reason: cancelReason.trim() })
      .then(() => refresh(`Draft GR-${receipt.id} cancelled.`))
      .then(() => {
        setCancelOpen(false);
        setCancelReason("");
      })
      .catch((err: unknown) => setCancelError(errorMessage(err, "The draft could not be cancelled.")))
      .finally(() => setBusy(""));
  }

  const backLink = (
    <Link
      href="/dashboard/receipts"
      className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
    >
      <ArrowLeft size={15} aria-hidden />
      All receipts
    </Link>
  );

  if (error || !Number.isInteger(receiptId) || receiptId <= 0) {
    return (
      <div className="space-y-6 pb-6">
        <PageHeader eyebrow="Purchasing" icon={PackageCheck} title="Goods receipt" actions={backLink} />
        <Card>
          <ErrorState
            title="Couldn't open this receipt"
            message={error || "This receipt was not found."}
            onRetry={() => setReloadKey((key) => key + 1)}
          />
        </Card>
      </div>
    );
  }

  if (!receipt) {
    return (
      <div className="space-y-6 pb-6">
        <PageHeader eyebrow="Purchasing" icon={PackageCheck} title={`Goods receipt GR-${receiptId}`} actions={backLink} />
        <Card>
          <TableSkeleton rows={4} columns={6} />
        </Card>
      </div>
    );
  }

  const isDraft = receipt.status === "DRAFT";

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Purchasing"
        icon={PackageCheck}
        title={`Goods receipt GR-${receipt.id}`}
        description={`Delivery against bill ${receipt.invoice_number ?? `#${receipt.purchase_id}`} from ${receipt.supplier_name ?? "the supplier"}.`}
        meta={<ReceiptStatusBadge status={receipt.status} />}
        actions={backLink}
      />

      {isDraft && canManage && !editing && (
        <Card className="border-amber-200 bg-amber-50/60">
          <div className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="text-sm text-amber-900">
              <p className="font-semibold">This receipt is a draft and has not changed stock.</p>
              <p className="mt-0.5">
                {classified
                  ? "Every received quantity is split into accepted and rejected. Accept it to add the accepted quantities to stock."
                  : "Split every received quantity into accepted and rejected (Correct quantities) before accepting."}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" icon={<PencilLine size={15} aria-hidden />} onClick={startEditing} disabled={!receiving || Boolean(busy)}>
                Correct quantities
              </Button>
              <Button variant="ghost" icon={<Ban size={15} aria-hidden />} onClick={() => setCancelOpen(true)} disabled={Boolean(busy)}>
                Cancel draft
              </Button>
              <Button
                icon={<CheckCircle2 size={15} aria-hidden />}
                onClick={() => setConfirmAccept(true)}
                disabled={!classified || Boolean(busy)}
                loading={busy === "accept"}
              >
                Accept receipt
              </Button>
            </div>
          </div>
        </Card>
      )}

      {actionError && (
        <Alert tone="error" title="Not done">
          {actionError}
        </Alert>
      )}

      {receipt.status === "CANCELLED" && receipt.cancellation && (
        <Alert tone="warning" title="Cancelled draft">
          Cancelled by {receipt.cancellation.cancelled_by_name ?? "a user"} on {formatDateTime(receipt.cancellation.cancelled_at)}
          {receipt.cancellation.reason ? `: “${receipt.cancellation.reason}”` : "."} It never affected stock and no longer
          holds any quantity.
        </Alert>
      )}

      <Card>
        <dl className="grid grid-cols-1 gap-5 p-5 sm:grid-cols-2 lg:grid-cols-4">
          <Detail label="Bill">
            <span className="font-medium">{receipt.invoice_number}</span>
            <span className="block text-slate-500">
              {receipt.supplier_name} · {formatDay(receipt.purchase_date)}
            </span>
          </Detail>
          <Detail label="Received on">{formatDay(receipt.receipt_date)}</Detail>
          <Detail label="Recorded">
            {receipt.created_by_name ?? "—"}
            <span className="block text-slate-500">{formatDateTime(receipt.created_at)}</span>
          </Detail>
          <Detail label="Accepted">
            {receipt.accepted_at ? (
              <>
                {receipt.accepted_by_name ?? "—"}
                <span className="block text-slate-500">{formatDateTime(receipt.accepted_at)}</span>
              </>
            ) : (
              <span className="text-slate-400">Not yet</span>
            )}
          </Detail>
          {receipt.remarks && (
            <div className="sm:col-span-2 lg:col-span-4">
              <Detail label="Remarks">{receipt.remarks}</Detail>
            </div>
          )}
        </dl>
      </Card>

      {editing ? (
        <>
          <Card>
            <CardHeader
              title="Correct this draft"
              subtitle="Change what arrived and how it splits into accepted and rejected. The previous values are kept in the audit log."
              icon={PencilLine}
            />
            <div className="grid grid-cols-1 gap-4 border-b border-slate-100 px-5 pb-5 sm:grid-cols-[12rem_minmax(0,1fr)]">
              <Field label="Received on" required error={editDateInvalid ? "Choose a date that is not in the future." : undefined}>
                {({ id, describedBy }) => (
                  <TextInput
                    id={id}
                    type="date"
                    max={today}
                    value={editDate}
                    aria-describedby={describedBy}
                    aria-invalid={editDateInvalid}
                    onChange={(event) => setEditDate(event.target.value)}
                  />
                )}
              </Field>
              <Field label="Remarks">
                {({ id }) => (
                  <TextArea id={id} rows={1} maxLength={1000} value={editRemarks} onChange={(event) => setEditRemarks(event.target.value)} />
                )}
              </Field>
            </div>
            <ReceiptLinesEditor
              lines={editorLines}
              checks={editCheck.lines}
              disabled={busy === "save"}
              onChange={(index, input) => setInputs((current) => current.map((value, i) => (i === index ? input : value)))}
            />
          </Card>
          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Button variant="ghost" onClick={() => setEditing(false)} disabled={busy === "save"}>
              Discard changes
            </Button>
            <Button
              icon={<Save size={15} aria-hidden />}
              loading={busy === "save"}
              disabled={!editCheck.canSave || editDateInvalid}
              onClick={saveCorrection}
            >
              Save correction
            </Button>
          </div>
        </>
      ) : (
        <Card>
          <CardHeader title="Quantities" subtitle="Billed is from the supplier's bill; this receipt records what arrived and what was accepted." icon={PackageCheck} />
          <Table minWidth="720px">
            <THead>
              <tr>
                <TH>Item</TH>
                <TH align="right">Billed</TH>
                <TH align="right">Received</TH>
                <TH align="right">Accepted</TH>
                <TH align="right">Rejected</TH>
              </tr>
            </THead>
            <TBody>
              {receipt.items.map((line) => {
                const unit = line.unit_symbol ?? "";
                return (
                  <TR key={line.id}>
                    <TD className="font-medium text-slate-900">{line.item_name ?? `Line ${line.purchase_item_id}`}</TD>
                    <TD align="right" className="whitespace-nowrap tabular-nums">
                      {formatQuantity(line.billed_quantity)} {unit}
                    </TD>
                    <TD align="right" className="whitespace-nowrap tabular-nums">
                      {formatQuantity(line.quantity_received)} {unit}
                    </TD>
                    <TD align="right" className="whitespace-nowrap tabular-nums font-medium text-emerald-700">
                      {formatQuantity(line.quantity_accepted)} {unit}
                    </TD>
                    <TD align="right" className="whitespace-nowrap tabular-nums text-red-700">
                      {formatQuantity(line.quantity_rejected)} {unit}
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        </Card>
      )}

      {receipt.status === "ACCEPTED" && (
        <Card>
          <CardHeader
            title="Stock posted"
            subtitle="The accepted quantities this receipt added to stock, in each item's standard unit."
            icon={ArrowLeftRight}
            action={
              <Link href={`/dashboard/stock-movements?receipt=${receipt.id}`} className="text-sm font-medium text-brand-700 hover:underline">
                View in stock movements
              </Link>
            }
          />
          {receipt.stock_movements.length === 0 ? (
            <p className="px-5 pb-5 text-sm text-slate-600">Nothing was accepted, so no stock was added.</p>
          ) : (
            <ul className="divide-y divide-slate-100 border-t border-slate-100" data-stock-posted>
              {receipt.stock_movements.map((movement) => (
                <li key={movement.id} className="flex items-center justify-between px-5 py-3 text-sm">
                  <span className="font-medium text-slate-900">{movement.item_name}</span>
                  <span className="tabular-nums text-emerald-700">
                    +{formatQuantity(movement.quantity)} {movement.unit_symbol}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <ConfirmDialog
        open={confirmAccept}
        tone="warning"
        title={`Accept receipt GR-${receipt.id}?`}
        description="The accepted quantities will be added to stock now. An accepted receipt cannot be changed or cancelled afterwards."
        confirmLabel="Accept and update stock"
        busy={busy === "accept"}
        onConfirm={accept}
        onCancel={() => setConfirmAccept(false)}
      />

      <Modal
        open={cancelOpen}
        onClose={() => (busy ? undefined : setCancelOpen(false))}
        title={`Cancel draft GR-${receipt.id}?`}
        description="The draft is kept as cancelled with your reason, frees the quantity it was holding, and never affects stock."
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCancelOpen(false)} disabled={busy === "cancel"}>
              Keep draft
            </Button>
            <Button variant="warning" loading={busy === "cancel"} onClick={cancelDraft}>
              Cancel draft
            </Button>
          </>
        }
      >
        <Field label="Reason" required error={cancelError}>
          {({ id, describedBy }) => (
            <TextArea
              id={id}
              rows={3}
              maxLength={500}
              aria-describedby={describedBy}
              value={cancelReason}
              placeholder="e.g. Entered against the wrong bill"
              onChange={(event) => setCancelReason(event.target.value)}
            />
          )}
        </Field>
      </Modal>
    </div>
  );
}
