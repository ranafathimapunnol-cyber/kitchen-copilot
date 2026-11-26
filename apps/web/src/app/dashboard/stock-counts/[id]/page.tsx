"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ClipboardCheck, FilePlus2 } from "lucide-react";

import { api } from "@/lib/api/client";
import { stockCountAdjustmentEndpoint, stockCountEndpoint } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime } from "@/lib/payments";
import {
  ADJUSTMENT_LABELS,
  ADJUSTMENT_TONES,
  canRecordCounts,
  signedDifference,
  type CountLine,
  type StockCount,
} from "@/lib/stockCounts";
import { plainQuantity } from "@/lib/stockMath";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import ReasonModal from "@/components/kitchen/ReasonModal";
import Alert from "@/components/ui/Alert";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
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

function differenceClass(value: string): string {
  const number = Number(value);
  return number < 0 ? "text-red-700" : number > 0 ? "text-emerald-700" : "text-slate-500";
}

export default function StockCountDetailPage() {
  const params = useParams<{ id: string }>();
  const { role, permissions } = useAuthorization();
  const toast = useToast();
  const [count, setCount] = useState<StockCount | null>(null);
  const [loadError, setLoadError] = useState("");
  const [raising, setRaising] = useState<CountLine | null>(null);

  const load = useCallback(() => {
    api
      .get<StockCount>(stockCountEndpoint(params.id))
      .then((response) => {
        setCount(response);
        setLoadError("");
      })
      .catch((err: unknown) => setLoadError(errorMessage(err, "Unable to load the count.")));
  }, [params.id]);

  useEffect(() => {
    load();
  }, [load]);

  const back = (
    <Link href="/dashboard/stock-counts" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
      <ArrowLeft size={15} aria-hidden />
      Stock counts
    </Link>
  );

  if (loadError && !count) {
    return (
      <div className="space-y-4 pb-6">
        {back}
        <Card><ErrorState title="Couldn't load the count" message={loadError} onRetry={load} /></Card>
      </div>
    );
  }
  if (!count) {
    return (
      <div className="space-y-4 pb-6">
        {back}
        <Card><TableSkeleton rows={5} columns={5} /></Card>
      </div>
    );
  }

  const mayRaise = canRecordCounts(role, permissions);

  function adjustmentCell(line: CountLine) {
    if (line.adjustment) {
      return (
        <div className="space-y-1">
          <Link href={`/dashboard/stock-adjustments/${line.adjustment.id}`} className="inline-flex">
            <Badge tone={ADJUSTMENT_TONES[line.adjustment.status]} dot>{ADJUSTMENT_LABELS[line.adjustment.status]}</Badge>
          </Link>
          {line.adjustment.status === "REJECTED" && <p className="text-xs text-slate-500">Count this item again to correct it.</p>}
        </div>
      );
    }
    if (Number(line.difference) === 0) return <span className="text-slate-500">Matches the system</span>;
    if (line.other_pending_adjustment) {
      return (
        <span className="text-xs text-amber-800">
          Another adjustment is pending for this item (
          <Link href={`/dashboard/stock-adjustments/${line.other_pending_adjustment.id}`} className="font-medium underline">
            {line.other_pending_adjustment.count_number}
          </Link>
          )
        </span>
      );
    }
    if (line.ledger_changed) {
      return <span className="text-xs text-amber-800">Stock dated before this count was recorded later. Count this item again.</span>;
    }
    if (line.can_raise && mayRaise) {
      return (
        <Button size="sm" variant="secondary" icon={<FilePlus2 size={14} aria-hidden />} onClick={() => setRaising(line)}>
          Raise adjustment
        </Button>
      );
    }
    return <span className="text-slate-500">Not raised</span>;
  }

  return (
    <div className="space-y-6 pb-6">
      {back}
      <PageHeader
        eyebrow="Stock count"
        icon={ClipboardCheck}
        title={count.count_number}
        description={`Counted ${formatDateTime(count.counted_at)} by ${count.counted_by_name ?? "—"}`}
        meta={
          count.difference_count === 0 ? (
            <Badge tone="success">All items match</Badge>
          ) : (
            <Badge tone="warning">{count.difference_count} difference{count.difference_count === 1 ? "" : "s"}</Badge>
          )
        }
      />

      <Card className="p-5">
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Fact label="Counted at">{formatDateTime(count.counted_at)}</Fact>
          <Fact label="Verifier">{count.counted_by_name ?? "—"}</Fact>
          <Fact label="Reason">{count.reason}</Fact>
          <Fact label="Remarks">{count.remarks ?? "—"}</Fact>
        </dl>
      </Card>

      <Alert tone="info">
        The system balance of each item was recorded when this count was saved and is never recalculated. Stock changes
        only when an adjustment is approved by an Admin or Kitchen Manager who did not perform the count; the difference is
        then applied at the count time, and later movements stay as they are.
      </Alert>

      <Card>
        <CardHeader title="Items counted" subtitle={`${count.line_count} item${count.line_count === 1 ? "" : "s"}, in each item's standard unit`} />
        <Table minWidth="860px">
          <THead>
            <tr>
              <TH>Item</TH>
              <TH align="right">Found</TH>
              <TH align="right">System at count time</TH>
              <TH align="right">Difference</TH>
              <TH>Adjustment</TH>
            </tr>
          </THead>
          <TBody>
            {count.lines.map((line) => (
              <TR key={line.id}>
                <TD>
                  <span className="font-medium text-slate-900">{line.item_name}</span>
                  <div className="text-xs text-slate-500">{line.category_name ?? "Uncategorised"}</div>
                  {line.remarks && <div className="text-xs text-slate-500">{line.remarks}</div>}
                </TD>
                <TD align="right" className="whitespace-nowrap">
                  <span className="font-medium text-slate-900">{plainQuantity(line.physical_quantity)} {line.standard_unit_symbol}</span>
                  {line.unit_id !== line.standard_unit_id && (
                    <div className="text-xs text-slate-500">entered as {plainQuantity(line.quantity)} {line.unit_symbol}</div>
                  )}
                </TD>
                <TD align="right" className="whitespace-nowrap">{plainQuantity(line.system_balance)} {line.standard_unit_symbol}</TD>
                <TD align="right" className={`font-semibold whitespace-nowrap ${differenceClass(line.difference)}`}>
                  {signedDifference(line.difference)} {Number(line.difference) !== 0 ? line.standard_unit_symbol : ""}
                </TD>
                <TD>{adjustmentCell(line)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Card>

      {raising && (
        <ReasonModal
          key={raising.id}
          open
          tone="warning"
          title={`Raise an adjustment for ${raising.item_name}?`}
          description={
            <>
              Difference measured at count time: <strong>{signedDifference(raising.difference)} {raising.standard_unit_symbol}</strong>.
              Nothing changes in stock until an Admin or Kitchen Manager who did not perform this count approves it.
            </>
          }
          confirmLabel="Raise adjustment"
          placeholder="e.g. Two bags damaged and thrown away"
          onClose={() => setRaising(null)}
          onSubmit={async (reason) => {
            await api.post(stockCountAdjustmentEndpoint(count.id, raising.id), { reason });
            setRaising(null);
            toast.success(`Adjustment for ${raising.item_name} raised; it waits for approval.`);
            load();
          }}
        />
      )}
    </div>
  );
}
