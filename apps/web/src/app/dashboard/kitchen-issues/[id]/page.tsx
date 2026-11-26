"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Ban, CircleCheck, CookingPot, CornerUpLeft, Pencil, Undo2 } from "lucide-react";

import { api } from "@/lib/api/client";
import { kitchenIssueActionEndpoint, kitchenIssueEndpoint, kitchenReturnActionEndpoint } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime, formatDay } from "@/lib/payments";
import {
  STATUS_LABELS,
  STATUS_TONES,
  canManageIssues,
  canRecordIssues,
  canReverseIssues,
  type KitchenIssue,
  type KitchenReturn,
} from "@/lib/kitchen";
import { canViewMeals } from "@/lib/meals";
import { plainQuantity } from "@/lib/stockMath";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import IssueForm from "@/components/kitchen/IssueForm";
import ReasonModal from "@/components/kitchen/ReasonModal";
import ReturnModal from "@/components/kitchen/ReturnModal";
import Alert from "@/components/ui/Alert";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import PageHeader from "@/components/ui/PageHeader";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

type Dialog =
  | { kind: "cancel-issue" }
  | { kind: "reverse-issue" }
  | { kind: "cancel-return"; record: KitchenReturn }
  | { kind: "reverse-return"; record: KitchenReturn }
  | { kind: "confirm-return"; record: KitchenReturn }
  | null;

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-900">{children}</dd>
    </div>
  );
}

function History({ doc }: { doc: KitchenIssue | KitchenReturn }) {
  return (
    <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Fact label="Recorded">{doc.created_by_name ?? "—"} · {formatDateTime(doc.created_at)}</Fact>
      <Fact label="Confirmed">{doc.confirmed_at ? `${doc.confirmed_by_name} · ${formatDateTime(doc.confirmed_at)}` : "—"}</Fact>
      <Fact label="Takes effect">{doc.effective_at ? formatDateTime(doc.effective_at) : "When confirmed"}</Fact>
      {doc.status === "CANCELLED" && (
        <Fact label="Cancelled">{doc.cancelled_by_name} · {formatDateTime(doc.cancelled_at)} · &ldquo;{doc.cancellation_reason}&rdquo;</Fact>
      )}
      {doc.status === "REVERSED" && (
        <Fact label="Reversed">{doc.reversed_by_name} · {formatDateTime(doc.reversed_at)} · &ldquo;{doc.reversal_reason}&rdquo;</Fact>
      )}
    </dl>
  );
}

export default function KitchenIssueDetailPage() {
  const params = useParams<{ id: string }>();
  const { role, permissions } = useAuthorization();
  const toast = useToast();
  const [issue, setIssue] = useState<KitchenIssue | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [editing, setEditing] = useState(false);
  const [confirmIssue, setConfirmIssue] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [returnOpen, setReturnOpen] = useState(false);

  const load = useCallback(() => {
    api
      .get<KitchenIssue>(kitchenIssueEndpoint(params.id))
      .then((response) => {
        setIssue(response);
        setLoadError("");
      })
      .catch((err: unknown) => setLoadError(errorMessage(err, "Unable to load the issue.")));
  }, [params.id]);

  useEffect(() => {
    load();
  }, [load]);

  const back = (
    <Link href="/dashboard/kitchen-issues" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
      <ArrowLeft size={15} aria-hidden />
      Kitchen issues
    </Link>
  );

  if (loadError && !issue) {
    return (
      <div className="space-y-4 pb-6">
        {back}
        <Card><ErrorState title="Couldn't load the issue" message={loadError} onRetry={load} /></Card>
      </div>
    );
  }
  if (!issue) {
    return (
      <div className="space-y-4 pb-6">
        {back}
        <Card><TableSkeleton rows={5} columns={6} /></Card>
      </div>
    );
  }

  const manage = canManageIssues(role, permissions);
  const record = canRecordIssues(role, permissions);
  const reverse = canReverseIssues(role);
  const canReturn = issue.status === "CONFIRMED" && record && issue.lines.some((line) => Number(line.returnable_quantity) > 0);
  const openReturns = issue.returns.filter((entry) => entry.status === "CONFIRMED");

  async function act(run: () => Promise<KitchenIssue>, done: string) {
    setBusy(true);
    setActionError("");
    try {
      const updated = await run();
      setIssue(updated);
      toast.success(done);
      return true;
    } catch (err: unknown) {
      setActionError(errorMessage(err, "The request failed."));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function withReason(reason: string) {
    if (!issue || !dialog) return;
    const run = {
      "cancel-issue": () => api.post<KitchenIssue>(kitchenIssueActionEndpoint(issue.id, "cancel"), { reason }),
      "reverse-issue": () => api.post<KitchenIssue>(kitchenIssueActionEndpoint(issue.id, "reverse"), { reason }),
      "cancel-return": () => api.post<KitchenIssue>(kitchenReturnActionEndpoint((dialog as { record: KitchenReturn }).record.id, "cancel"), { reason }),
      "reverse-return": () => api.post<KitchenIssue>(kitchenReturnActionEndpoint((dialog as { record: KitchenReturn }).record.id, "reverse"), { reason }),
    }[dialog.kind as "cancel-issue" | "reverse-issue" | "cancel-return" | "reverse-return"];
    // The dialog shows the API's refusal (for example a shortfall) itself.
    const updated = await run();
    setIssue(updated);
    setDialog(null);
    toast.success({
      "cancel-issue": `${issue.issue_number} cancelled.`,
      "reverse-issue": `${issue.issue_number} reversed; the stock is back.`,
      "cancel-return": "Draft return cancelled.",
      "reverse-return": "Return reversed; the stock went back to the kitchen.",
    }[dialog.kind as "cancel-issue" | "reverse-issue" | "cancel-return" | "reverse-return"]);
  }

  return (
    <div className="space-y-6 pb-6">
      {back}
      <PageHeader
        eyebrow="Kitchen issue"
        icon={CookingPot}
        title={issue.issue_number}
        description={`${issue.menu_name} · ${issue.meal_session_name} · ${formatDay(issue.issue_date)}`}
        meta={<Badge tone={STATUS_TONES[issue.status]} dot>{STATUS_LABELS[issue.status]}</Badge>}
        actions={
          editing ? undefined : (
            <>
              {issue.status === "DRAFT" && manage && (
                <>
                  <Button variant="secondary" icon={<Pencil size={15} aria-hidden />} onClick={() => setEditing(true)}>Edit</Button>
                  <Button variant="secondary" icon={<Ban size={15} aria-hidden />} onClick={() => setDialog({ kind: "cancel-issue" })}>Cancel draft</Button>
                  <Button icon={<CircleCheck size={16} aria-hidden />} onClick={() => setConfirmIssue(true)}>Confirm issue</Button>
                </>
              )}
              {canReturn && (
                <Button variant="secondary" icon={<CornerUpLeft size={15} aria-hidden />} onClick={() => setReturnOpen(true)}>Record return</Button>
              )}
              {issue.status === "CONFIRMED" && reverse && (
                <Button variant="warning" icon={<Undo2 size={15} aria-hidden />} onClick={() => setDialog({ kind: "reverse-issue" })}>Reverse issue</Button>
              )}
            </>
          )
        }
      />

      {actionError && (
        <Alert tone="error" title="Not done" onDismiss={() => setActionError("")}>{actionError}</Alert>
      )}
      {issue.status === "DRAFT" && (
        <Alert tone="info">This draft has not changed stock. Confirming it takes the quantities out of stock; it is refused if any item would go below zero.</Alert>
      )}

      {editing ? (
        <IssueForm
          initial={issue}
          onCancel={() => setEditing(false)}
          onSaved={(saved) => {
            setIssue(saved);
            setEditing(false);
            toast.success(`${saved.issue_number} updated.`);
          }}
        />
      ) : (
        <>
          <Card className="p-5"><History doc={issue} /></Card>
          {issue.remarks && <Card className="p-5 text-sm text-slate-700"><span className="font-medium">Remarks:</span> {issue.remarks}</Card>}
          {issue.meal_record && canViewMeals(role, permissions) && (
            <Card className="p-5 text-sm text-slate-700">
              <span className="font-medium">Meal record:</span>{" "}
              <Link href={`/dashboard/meals/${issue.meal_record.id}`} className="text-brand-700 hover:underline">
                {issue.meal_session_name} · {formatDay(issue.issue_date)}
              </Link>{" "}
              <span className="text-slate-500">({issue.meal_record.status.toLowerCase()})</span>
            </Card>
          )}

          <Card>
            <CardHeader title="Items" subtitle="Issued and returned stay separate; net usage is issued minus returned (in the item's standard unit)." />
            <Table minWidth="860px">
              <THead>
                <tr>
                  <TH>Item</TH>
                  <TH align="right">Issued</TH>
                  <TH align="right">Returned</TH>
                  <TH align="right">Net usage</TH>
                  <TH align="right">Can still return</TH>
                  <TH>Remarks</TH>
                </tr>
              </THead>
              <TBody>
                {issue.lines.map((line) => (
                  <TR key={line.id}>
                    <TD>
                      <Link href={`/dashboard/stock/${line.item_id}`} className="font-medium text-slate-900 hover:text-brand-700 hover:underline">{line.item_name}</Link>
                    </TD>
                    <TD align="right" className="whitespace-nowrap">
                      <span className="font-medium text-slate-900">{plainQuantity(line.standard_quantity)} {line.standard_unit_symbol}</span>
                      {line.unit_id !== line.standard_unit_id && (
                        <div className="text-xs text-slate-500">entered as {plainQuantity(line.quantity)} {line.unit_symbol}</div>
                      )}
                    </TD>
                    <TD align="right" className="whitespace-nowrap">
                      {plainQuantity(line.returned_quantity)} {line.standard_unit_symbol}
                      {Number(line.in_draft_return_quantity) > 0 && (
                        <div className="text-xs text-amber-800">+{plainQuantity(line.in_draft_return_quantity)} in draft</div>
                      )}
                    </TD>
                    <TD align="right" className="font-semibold whitespace-nowrap text-slate-900">
                      {line.net_quantity === null ? "—" : `${plainQuantity(line.net_quantity)} ${line.standard_unit_symbol}`}
                    </TD>
                    <TD align="right" className="whitespace-nowrap">
                      {issue.status === "CONFIRMED" ? `${plainQuantity(line.returnable_quantity)} ${line.standard_unit_symbol}` : "—"}
                    </TD>
                    <TD className="max-w-56 truncate" title={line.remarks ?? undefined}>{line.remarks ?? <span className="text-slate-400">—</span>}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Card>

          <Card>
            <CardHeader
              title="Unused returns"
              subtitle={issue.returns.length ? `${issue.returns.length} recorded against this issue` : "Nothing returned yet"}
              icon={CornerUpLeft}
            />
            {issue.returns.length === 0 ? (
              <p className="px-5 pb-5 text-sm text-slate-600">
                {issue.status === "CONFIRMED" ? "Unused stock brought back from the kitchen is recorded here." : "Returns can be recorded once the issue is confirmed."}
              </p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {issue.returns.map((entry) => (
                  <li key={entry.id} className="space-y-3 px-5 py-4" data-return={entry.return_number}>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-slate-900">{entry.return_number}</span>
                        <Badge tone={STATUS_TONES[entry.status]} dot>{STATUS_LABELS[entry.status]}</Badge>
                        <span className="text-sm text-slate-500">{formatDay(entry.return_date)}</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {entry.status === "DRAFT" && manage && (
                          <>
                            <Button size="sm" variant="secondary" icon={<Ban size={14} aria-hidden />} onClick={() => setDialog({ kind: "cancel-return", record: entry })}>Cancel</Button>
                            <Button size="sm" icon={<CircleCheck size={14} aria-hidden />} onClick={() => setDialog({ kind: "confirm-return", record: entry })}>Confirm return</Button>
                          </>
                        )}
                        {entry.status === "CONFIRMED" && reverse && (
                          <Button size="sm" variant="warning" icon={<Undo2 size={14} aria-hidden />} onClick={() => setDialog({ kind: "reverse-return", record: entry })}>Reverse return</Button>
                        )}
                      </div>
                    </div>
                    <ul className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-700">
                      {entry.lines.map((line) => (
                        <li key={line.id}>
                          {line.item_name}: <span className="font-medium">{plainQuantity(line.standard_quantity)} {line.standard_unit_symbol}</span>
                          {line.unit_id !== undefined && line.unit_symbol !== line.standard_unit_symbol && (
                            <span className="text-slate-500"> ({plainQuantity(line.quantity)} {line.unit_symbol})</span>
                          )}
                        </li>
                      ))}
                    </ul>
                    <History doc={entry} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}

      <ConfirmDialog
        open={confirmIssue}
        tone="warning"
        title={`Confirm ${issue.issue_number}?`}
        description="The issued quantities leave stock now. It is refused if any item would go below zero. A confirmed issue cannot be edited; an Admin or Kitchen Manager can reverse it."
        confirmLabel="Confirm and take out stock"
        busy={busy}
        onCancel={() => setConfirmIssue(false)}
        onConfirm={async () => {
          await act(() => api.post<KitchenIssue>(kitchenIssueActionEndpoint(issue.id, "confirm")), `${issue.issue_number} confirmed; stock updated.`);
          setConfirmIssue(false);
        }}
      />

      <ConfirmDialog
        open={dialog?.kind === "confirm-return"}
        tone="warning"
        title={dialog?.kind === "confirm-return" ? `Confirm ${dialog.record.return_number}?` : "Confirm return"}
        description="The returned quantities go back into stock now. A confirmed return cannot be edited; an Admin or Kitchen Manager can reverse it."
        confirmLabel="Confirm and add back to stock"
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={async () => {
          if (dialog?.kind !== "confirm-return") return;
          await act(() => api.post<KitchenIssue>(kitchenReturnActionEndpoint(dialog.record.id, "confirm")), `${dialog.record.return_number} confirmed; stock updated.`);
          setDialog(null);
        }}
      />

      {dialog && dialog.kind !== "confirm-return" && (
        <ReasonModal
          key={`${dialog.kind}-${"record" in dialog ? dialog.record.id : issue.id}`}
          open
          tone={dialog.kind.startsWith("reverse") ? "danger" : "warning"}
          title={{
            "cancel-issue": `Cancel draft ${issue.issue_number}?`,
            "reverse-issue": `Reverse ${issue.issue_number}?`,
            "cancel-return": `Cancel draft ${"record" in dialog ? dialog.record.return_number : ""}?`,
            "reverse-return": `Reverse ${"record" in dialog ? dialog.record.return_number : ""}?`,
          }[dialog.kind]}
          description={{
            "cancel-issue": "The draft is kept as cancelled with your reason. It never changed stock.",
            "reverse-issue": openReturns.length
              ? `Its confirmed return${openReturns.length > 1 ? "s" : ""} (${openReturns.map((r) => r.return_number).join(", ")}) must be reversed first.`
              : "Reversal movements, effective now, put the issued stock back. The issue and its movements stay unchanged as history; record a corrected issue afterwards.",
            "cancel-return": "The draft is kept as cancelled with your reason. It never changed stock.",
            "reverse-return": "Reversal movements, effective now, take the returned stock out again. Refused if a balance would go below zero.",
          }[dialog.kind]}
          confirmLabel={dialog.kind.startsWith("reverse") ? "Reverse" : "Cancel draft"}
          placeholder={dialog.kind.startsWith("reverse") ? "e.g. Recorded against the wrong menu" : "e.g. Entered twice"}
          onSubmit={withReason}
          onClose={() => setDialog(null)}
        />
      )}

      {returnOpen && (
        <ReturnModal
          key={issue.id}
          issue={issue}
          onClose={() => setReturnOpen(false)}
          onSaved={(updated) => {
            setIssue(updated);
            setReturnOpen(false);
            toast.success("Draft return saved. Confirm it to add the stock back.");
          }}
        />
      )}
    </div>
  );
}
