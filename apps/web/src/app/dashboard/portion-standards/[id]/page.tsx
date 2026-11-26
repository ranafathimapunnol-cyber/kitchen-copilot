"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Ban, CircleCheck, History, Pencil, Weight } from "lucide-react";

import { api } from "@/lib/api/client";
import { PORTION_STANDARD_OPTIONS_ENDPOINT, portionStandardActionEndpoint, portionStandardEndpoint } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime, formatDay } from "@/lib/payments";
import {
  KIND_LABELS,
  SOURCE_LABELS,
  STANDARD_HISTORY_LABELS,
  STANDARD_STATE_LABELS,
  STANDARD_STATE_TONES,
  canApprovePlanning,
  type StandardDetail,
  type StandardOptions,
} from "@/lib/planning";
import { plainQuantity } from "@/lib/stockMath";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import ReasonModal from "@/components/kitchen/ReasonModal";
import { StandardModal } from "@/components/planning/StandardModals";
import Alert from "@/components/ui/Alert";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import PageHeader from "@/components/ui/PageHeader";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm break-words text-slate-900">{children}</dd>
    </div>
  );
}

export default function PortionStandardPage() {
  const params = useParams<{ id: string }>();
  const { role } = useAuthorization();
  const toast = useToast();
  const [standard, setStandard] = useState<StandardDetail | null>(null);
  const [options, setOptions] = useState<StandardOptions | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [dialog, setDialog] = useState<"edit" | "approve" | "cancel" | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .get<StandardDetail>(portionStandardEndpoint(params.id))
      .then((response) => {
        setStandard(response);
        setLoadError("");
      })
      .catch((err: unknown) => setLoadError(errorMessage(err, "Unable to load the standard.")));
  }, [params.id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.get<StandardOptions>(PORTION_STANDARD_OPTIONS_ENDPOINT).then(setOptions).catch(() => setOptions(null));
  }, []);

  const back = (
    <Link href="/dashboard/portion-standards" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
      <ArrowLeft size={15} aria-hidden />
      Portion Standards
    </Link>
  );

  if (loadError && !standard) {
    return <div className="space-y-4 pb-6">{back}<Card><ErrorState title="Couldn't load the standard" message={loadError} onRetry={load} /></Card></div>;
  }
  if (!standard) {
    return <div className="space-y-4 pb-6">{back}<Card><TableSkeleton rows={4} columns={4} /></Card></div>;
  }

  const draft = standard.status === "DRAFT";
  const approver = canApprovePlanning(role);

  return (
    <div className="space-y-6 pb-6">
      {back}
      <PageHeader
        eyebrow="Portion standard"
        icon={Weight}
        title={`${standard.item_name} · ${standard.menu_name}`}
        description={`${plainQuantity(standard.quantity_per_person)} ${standard.unit_symbol} per person from ${formatDay(standard.effective_from)}`}
        meta={<Badge tone={STANDARD_STATE_TONES[standard.state]} dot>{STANDARD_STATE_LABELS[standard.state]}</Badge>}
        actions={draft ? (
          <>
            <Button variant="secondary" icon={<Pencil size={15} aria-hidden />} disabled={!options} onClick={() => setDialog("edit")}>Edit draft</Button>
            <Button variant="secondary" icon={<Ban size={15} aria-hidden />} onClick={() => setDialog("cancel")}>Cancel draft</Button>
            {approver && <Button icon={<CircleCheck size={16} aria-hidden />} onClick={() => setDialog("approve")}>Approve</Button>}
          </>
        ) : undefined}
      />

      {actionError && <Alert tone="error" title="Not done" onDismiss={() => setActionError("")}>{actionError}</Alert>}
      {standard.status === "APPROVED" && (
        <Alert tone="success" title={`Version ${standard.version_no}, approved by ${standard.approved_by_name} · ${formatDateTime(standard.approved_at)}`}>
          An approved standard never changes. To change the quantity, create and approve a new version: it applies to plans dated on or after its date, and the higher version wins on the same date.
        </Alert>
      )}
      {standard.status === "CANCELLED" && (
        <Alert tone="info" title={`Cancelled by ${standard.cancelled_by_name} · ${formatDateTime(standard.cancelled_at)}`}>&ldquo;{standard.cancellation_reason}&rdquo;</Alert>
      )}
      {draft && (
        standard.approval_problems.length > 0 ? (
          <Alert tone="info" title="Before this draft can be approved">
            <ul className="list-disc pl-5">{standard.approval_problems.map((p) => <li key={p}>{p}</li>)}</ul>
          </Alert>
        ) : (
          <Alert tone="warning" title="Draft — not used by any plan until approved">
            {approver ? "Approve it to make it available to plans dated on or after its effective date." : "An Admin or Kitchen Manager approves it."}
          </Alert>
        )
      )}

      <Card className="p-5">
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Fact label="Menu">{standard.menu_name} ({standard.meal_session_name})</Fact>
          <Fact label="Item">{standard.item_name} · {standard.item_kind ? KIND_LABELS[standard.item_kind] : "not classified"}</Fact>
          <Fact label="Per person">{plainQuantity(standard.quantity_per_person)} {standard.unit_symbol} (stock in {standard.base_unit_symbol})</Fact>
          <Fact label="Effective from">{formatDay(standard.effective_from)}</Fact>
          <Fact label="Source">{SOURCE_LABELS[standard.source] ?? standard.source}{standard.copied_from_menu_main_item_id ? ` (#${standard.copied_from_menu_main_item_id})` : ""}</Fact>
          <Fact label="Created">{standard.created_by_name} · {formatDateTime(standard.created_at)}</Fact>
          {standard.notes && <Fact label="Notes">{standard.notes}</Fact>}
        </dl>
      </Card>

      {standard.basis.length > 0 && standard.basis_totals && (
        <Card>
          <CardHeader title="Suggested from these meals"
            subtitle={`Total used ÷ people served = ${plainQuantity(standard.basis_totals.quantity_used)} ${standard.basis_totals.unit_symbol} ÷ ${standard.basis_totals.people_served} = ${standard.basis_totals.per_person} ${standard.basis_totals.unit_symbol} per person`} />
          <Table minWidth="560px">
            <THead><tr><TH>Meal</TH><TH align="right">Net usage at closing</TH><TH align="right">People served</TH></tr></THead>
            <TBody>
              {standard.basis.map((b) => (
                <TR key={b.meal_record_id}>
                  <TD><Link href={`/dashboard/meals/${b.meal_record_id}`} className="text-brand-700 hover:underline">{b.meal_session_name} · {formatDay(b.meal_date)}</Link></TD>
                  <TD align="right">{plainQuantity(b.quantity_used)} {b.unit_symbol}</TD>
                  <TD align="right">{b.people_served}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      )}

      <Card>
        <CardHeader title="Versions for this menu and item" subtitle="Drafts first, then approved versions, newest first." />
        <Table minWidth="760px">
          <THead><tr><TH>Version</TH><TH align="right">Per person</TH><TH>Effective from</TH><TH>State</TH><TH>Approved</TH></tr></THead>
          <TBody>
            {standard.versions.map((v) => (
              <TR key={v.id} muted={v.state === "CANCELLED" || v.state === "SUPERSEDED"}>
                <TD>
                  {v.id === standard.id ? <span className="font-semibold">{v.version_no ? `v${v.version_no}` : `Draft #${v.id}`}</span> : (
                    <Link href={`/dashboard/portion-standards/${v.id}`} className="text-brand-700 hover:underline">{v.version_no ? `v${v.version_no}` : `Draft #${v.id}`}</Link>
                  )}
                </TD>
                <TD align="right">{plainQuantity(v.quantity_per_person)} {v.unit_symbol}</TD>
                <TD>{formatDay(v.effective_from)}</TD>
                <TD><Badge tone={STANDARD_STATE_TONES[v.state]} dot>{STANDARD_STATE_LABELS[v.state]}</Badge></TD>
                <TD className="text-slate-600">{v.approved_at ? `${v.approved_by_name} · ${formatDateTime(v.approved_at)}` : "—"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Card>

      <Card>
        <CardHeader title="History" subtitle="Every change, approval and cancellation, oldest first." icon={History} />
        <ol className="space-y-2 px-5 pb-5 text-sm" aria-label="History">
          {standard.history.map((entry) => (
            <li key={entry.id} className="flex flex-wrap gap-x-2">
              <span className="font-medium text-slate-900">{STANDARD_HISTORY_LABELS[entry.action] ?? entry.action}</span>
              <span className="text-slate-500">{entry.user_name} · {formatDateTime(entry.created_at)}</span>
              {typeof entry.details.reason === "string" && <span className="text-slate-700">&ldquo;{entry.details.reason}&rdquo;</span>}
            </li>
          ))}
        </ol>
      </Card>

      {dialog === "edit" && options && (
        <StandardModal options={options} standard={standard} onClose={() => setDialog(null)}
          onSaved={(saved) => { setStandard(saved); setDialog(null); toast.success("Draft saved."); }} />
      )}
      <ConfirmDialog
        open={dialog === "approve"}
        tone="warning"
        title={`Approve ${standard.item_name} for ${standard.menu_name}?`}
        description={standard.approval_problems.length
          ? `It cannot be approved yet: ${standard.approval_problems.join(" ")}`
          : `${plainQuantity(standard.quantity_per_person)} ${standard.unit_symbol} per person from ${formatDay(standard.effective_from)}. It becomes the next version and can never be changed; plans dated on or after this date use it.`}
        confirmLabel="Approve"
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={async () => {
          setBusy(true);
          setActionError("");
          try {
            setStandard(await api.post<StandardDetail>(portionStandardActionEndpoint(standard.id, "approve")));
            toast.success("Standard approved.");
          } catch (err: unknown) {
            setActionError(errorMessage(err, "Unable to approve the standard."));
          } finally {
            setBusy(false);
            setDialog(null);
          }
        }}
      />
      {dialog === "cancel" && (
        <ReasonModal
          open
          tone="danger"
          title="Cancel this draft?"
          description="The draft is kept as cancelled with your reason and is never used by a plan."
          confirmLabel="Cancel draft"
          placeholder="e.g. Entered for the wrong menu"
          onClose={() => setDialog(null)}
          onSubmit={async (reason) => {
            setStandard(await api.post<StandardDetail>(portionStandardActionEndpoint(standard.id, "cancel"), { reason }));
            setDialog(null);
            toast.success("Draft cancelled.");
          }}
        />
      )}
    </div>
  );
}
