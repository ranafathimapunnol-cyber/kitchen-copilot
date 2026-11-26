"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, CircleCheck, ListChecks, XCircle } from "lucide-react";

import { api } from "@/lib/api/client";
import { stockAdjustmentActionEndpoint, stockAdjustmentEndpoint } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime } from "@/lib/payments";
import { movementLabel } from "@/lib/stock";
import {
  ADJUSTMENT_LABELS,
  ADJUSTMENT_TONES,
  canDecideAdjustments,
  signedDifference,
  waitingReason,
  type Adjustment,
} from "@/lib/stockCounts";
import { plainQuantity } from "@/lib/stockMath";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import ReasonModal from "@/components/kitchen/ReasonModal";
import Alert from "@/components/ui/Alert";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Field, TextArea } from "@/components/ui/Field";
import Modal from "@/components/ui/Modal";
import PageHeader from "@/components/ui/PageHeader";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

function Figure({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-card">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className={`mt-1 text-xl font-bold tracking-tight ${tone ?? "text-slate-900"}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm break-words text-slate-900">{children}</dd>
    </div>
  );
}

function ApproveModal({ adjustment, onClose, onDone }: {
  adjustment: Adjustment;
  onClose: () => void;
  onDone: (updated: Adjustment) => void;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const unit = adjustment.unit_symbol ?? "";

  async function submit() {
    setBusy(true);
    setError("");
    try {
      onDone(await api.post<Adjustment>(stockAdjustmentActionEndpoint(adjustment.id, "approve"), { note: note.trim() || null }));
    } catch (err: unknown) {
      setError(errorMessage(err, "The adjustment was not approved."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      size="sm"
      onClose={() => (busy ? undefined : onClose())}
      dismissible={!busy}
      title={`Approve the adjustment for ${adjustment.item_name}?`}
      description={
        <>
          Posts <strong>{signedDifference(adjustment.difference)} {unit}</strong> as an adjustment movement effective at the
          count time ({formatDateTime(adjustment.counted_at)}). Movements recorded since the count stay as they are.
          {adjustment.balance_after_approval !== null && (
            <> Today&apos;s balance becomes <strong>{plainQuantity(adjustment.balance_after_approval)} {unit}</strong>.</>
          )}
        </>
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>Keep it pending</Button>
          <Button loading={busy} icon={<CircleCheck size={16} aria-hidden />} onClick={submit}>Approve and post</Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Note (optional)">
          {({ id }) => (
            <TextArea id={id} rows={2} maxLength={500} data-autofocus value={note} placeholder="e.g. Checked the shelf myself"
              onChange={(event) => setNote(event.target.value)} />
          )}
        </Field>
      </div>
    </Modal>
  );
}

export default function StockAdjustmentDetailPage() {
  const params = useParams<{ id: string }>();
  const { role } = useAuthorization();
  const toast = useToast();
  const [adjustment, setAdjustment] = useState<Adjustment | null>(null);
  const [loadError, setLoadError] = useState("");
  const [dialog, setDialog] = useState<"approve" | "reject" | null>(null);

  const load = useCallback(() => {
    api
      .get<Adjustment>(stockAdjustmentEndpoint(params.id))
      .then((response) => {
        setAdjustment(response);
        setLoadError("");
      })
      .catch((err: unknown) => setLoadError(errorMessage(err, "Unable to load the adjustment.")));
  }, [params.id]);

  useEffect(() => {
    load();
  }, [load]);

  const back = (
    <Link href="/dashboard/stock-adjustments" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
      <ArrowLeft size={15} aria-hidden />
      Stock adjustments
    </Link>
  );

  if (loadError && !adjustment) {
    return (
      <div className="space-y-4 pb-6">
        {back}
        <Card><ErrorState title="Couldn't load the adjustment" message={loadError} onRetry={load} /></Card>
      </div>
    );
  }
  if (!adjustment) {
    return (
      <div className="space-y-4 pb-6">
        {back}
        <Card><TableSkeleton rows={4} columns={4} /></Card>
      </div>
    );
  }

  const unit = adjustment.unit_symbol ?? "";
  const pending = adjustment.status === "PENDING";
  const decide = pending && adjustment.can_decide && canDecideAdjustments(role);
  const blocked = adjustment.ledger_changed || adjustment.would_go_negative;
  const since = adjustment.movements_since_count ?? null;

  return (
    <div className="space-y-6 pb-6">
      {back}
      <PageHeader
        eyebrow="Stock adjustment"
        icon={ListChecks}
        title={`${adjustment.item_name}: ${signedDifference(adjustment.difference)} ${unit}`}
        description={`From ${adjustment.count_number}, counted ${formatDateTime(adjustment.counted_at)} by ${adjustment.counted_by_name ?? "—"}`}
        meta={<Badge tone={ADJUSTMENT_TONES[adjustment.status]} dot>{ADJUSTMENT_LABELS[adjustment.status]}</Badge>}
        actions={
          decide ? (
            <>
              <Button variant="secondary" icon={<XCircle size={15} aria-hidden />} onClick={() => setDialog("reject")}>Reject</Button>
              <Button icon={<CircleCheck size={16} aria-hidden />} disabled={blocked} onClick={() => setDialog("approve")}>Approve</Button>
            </>
          ) : undefined
        }
      />

      {pending && !adjustment.can_decide && (
        <Alert tone="info" title="Waiting for an independent approver">{waitingReason(adjustment)}</Alert>
      )}
      {pending && adjustment.ledger_changed && (
        <Alert tone="warning" title="The ledger at the count time has changed">
          A movement dated on or before the count was recorded after the count was saved, so the difference measured then
          would no longer give the counted quantity. It cannot be approved: reject it and count {adjustment.item_name} again.
        </Alert>
      )}
      {pending && adjustment.would_go_negative && (
        <Alert tone="warning" title="Approving would take stock below zero">
          {adjustment.shortfall
            ? `The balance would reach ${plainQuantity(adjustment.shortfall.balance)} ${unit} on ${formatDateTime(adjustment.shortfall.at)}. `
            : ""}
          No balance may go below zero. A record is probably missing: reject this adjustment, then record the missing movement
          or count again.
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <Figure label="System at count time" value={`${plainQuantity(adjustment.system_balance_at_count)} ${unit}`} hint="Recorded when the count was saved" />
        <Figure label="Found" value={`${plainQuantity(adjustment.physical_quantity)} ${unit}`}
          hint={adjustment.entered_unit_symbol !== unit ? `entered as ${plainQuantity(adjustment.entered_quantity)} ${adjustment.entered_unit_symbol}` : undefined} />
        <Figure label="Difference" value={`${signedDifference(adjustment.difference)} ${unit}`}
          tone={Number(adjustment.difference) < 0 ? "text-red-700" : "text-emerald-700"} />
        {adjustment.stock_visible && (
          <>
            <Figure label="Ledger at count time now" value={`${plainQuantity(adjustment.count_time_balance_now ?? "0")} ${unit}`}
              tone={adjustment.ledger_changed ? "text-amber-700" : undefined}
              hint={adjustment.ledger_changed ? "Changed since the count" : "Unchanged since the count"} />
            <Figure label="Balance now" value={`${plainQuantity(adjustment.balance_now ?? "0")} ${unit}`} />
            {pending && adjustment.balance_after_approval !== null && (
              <Figure label="After approval" value={`${plainQuantity(adjustment.balance_after_approval)} ${unit}`} />
            )}
          </>
        )}
      </div>

      <Card className="p-5">
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Fact label="Raised">{adjustment.raised_by_name} · {formatDateTime(adjustment.raised_at)}</Fact>
          <Fact label="Reason">{adjustment.reason}</Fact>
          <Fact label="Count">
            <Link href={`/dashboard/stock-counts/${adjustment.count_id}`} className="text-brand-700 hover:underline">{adjustment.count_number}</Link>
          </Fact>
          {!pending && (
            <>
              <Fact label={adjustment.status === "APPROVED" ? "Approved" : "Rejected"}>
                {adjustment.decided_by_name} · {adjustment.decided_at ? formatDateTime(adjustment.decided_at) : "—"}
              </Fact>
              <Fact label={adjustment.status === "APPROVED" ? "Note" : "Rejection reason"}>{adjustment.decision_reason ?? "—"}</Fact>
              <Fact label="Stock">
                {adjustment.movement_id ? (
                  <Link href={`/dashboard/stock/${adjustment.item_id}`} className="text-brand-700 hover:underline">
                    Movement #{adjustment.movement_id} in the item ledger
                  </Link>
                ) : (
                  "Nothing was posted"
                )}
              </Fact>
            </>
          )}
        </dl>
      </Card>

      {since !== null && (
        <Card>
          <CardHeader title="Movements since the count"
            subtitle={since.length ? "Recorded after the count was saved. Those dated after the count follow the adjustment in the ledger." : "Nothing was recorded for this item after the count."} />
          {since.length > 0 && (
            <Table minWidth="760px">
              <THead>
                <tr>
                  <TH>Movement</TH>
                  <TH align="right">Change</TH>
                  <TH>Effective</TH>
                  <TH>Recorded</TH>
                  <TH>Document</TH>
                </tr>
              </THead>
              <TBody>
                {since.map((movement) => (
                  <TR key={movement.id}>
                    <TD className="whitespace-nowrap">
                      {movementLabel(movement.movement_type)}
                      {movement.dated_before_count && (
                        <div><Badge tone="warning">Dated before the count</Badge></div>
                      )}
                    </TD>
                    <TD align="right" className="whitespace-nowrap">{signedDifference(movement.signed_quantity)} {unit}</TD>
                    <TD className="whitespace-nowrap">{formatDateTime(movement.effective_at)}</TD>
                    <TD className="whitespace-nowrap">{movement.created_by_name} · {formatDateTime(movement.created_at)}</TD>
                    <TD className="whitespace-nowrap">{movement.document_number ?? `#${movement.id}`}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </Card>
      )}

      {dialog === "approve" && (
        <ApproveModal
          adjustment={adjustment}
          onClose={() => setDialog(null)}
          onDone={(updated) => {
            setAdjustment(updated);
            setDialog(null);
            toast.success(`Approved: ${updated.item_name} adjusted by ${signedDifference(updated.difference)} ${unit}.`);
          }}
        />
      )}
      {dialog === "reject" && (
        <ReasonModal
          key={adjustment.id}
          open
          tone="danger"
          title={`Reject the adjustment for ${adjustment.item_name}?`}
          description="Nothing is posted and stock stays as it is. Your reason is kept; the item must be counted again to raise a new adjustment."
          confirmLabel="Reject"
          placeholder="e.g. The cold room was not counted"
          onClose={() => setDialog(null)}
          onSubmit={async (reason) => {
            const updated = await api.post<Adjustment>(stockAdjustmentActionEndpoint(adjustment.id, "reject"), { reason });
            setAdjustment(updated);
            setDialog(null);
            toast.success("Adjustment rejected; nothing was posted.");
          }}
        />
      )}
    </div>
  );
}
