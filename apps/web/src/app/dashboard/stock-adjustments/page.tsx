"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ClipboardCheck, ListChecks } from "lucide-react";

import { api } from "@/lib/api/client";
import { STOCK_ADJUSTMENTS_ENDPOINT } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime } from "@/lib/payments";
import {
  ADJUSTMENT_LABELS,
  ADJUSTMENT_STATUSES,
  ADJUSTMENT_TONES,
  signedDifference,
  waitingReason,
  type AdjustmentListResponse,
  type AdjustmentStatus,
} from "@/lib/stockCounts";
import { plainQuantity } from "@/lib/stockMath";
import Badge from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

const PAGE_SIZES = [20, 50, 100];

export default function StockAdjustmentsPage() {
  const [status, setStatus] = useState<AdjustmentStatus>("PENDING");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<AdjustmentListResponse | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");

  const url = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), status });
    return `${STOCK_ADJUSTMENTS_ENDPOINT}?${params}`;
  }, [page, pageSize, status]);
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    let active = true;
    api
      .get<AdjustmentListResponse>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load adjustments."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });
    return () => {
      active = false;
    };
  }, [url, requestKey]);

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Inventory"
        icon={ListChecks}
        title="Stock adjustments"
        description="Corrections raised from physical counts. Each is approved or rejected by an Admin or Kitchen Manager who did not perform the count. Approval applies the difference measured at count time; rejection changes nothing."
        actions={
          <Link href="/dashboard/stock-counts"
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm transition-colors hover:bg-slate-50">
            <ClipboardCheck size={16} aria-hidden />
            Stock counts
          </Link>
        }
      />

      <Card>
        <div className="border-b border-slate-100 px-5 py-4">
          <SegmentedControl<AdjustmentStatus>
            label="Adjustment status"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={ADJUSTMENT_STATUSES.map((value) => ({
              value,
              label: ADJUSTMENT_LABELS[value],
              count: data?.status_counts[value],
            }))}
          />
        </div>

        {error && !loading ? (
          <ErrorState title="Couldn't load adjustments" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : !data ? (
          <TableSkeleton rows={5} columns={7} />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={ListChecks}
            title={status === "PENDING" ? "Nothing waiting for approval" : `No ${ADJUSTMENT_LABELS[status].toLowerCase()} adjustments`}
            description="Adjustments are raised from a stock count line that differs from the system."
          />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="980px">
              <THead>
                <tr>
                  <TH>Item</TH>
                  <TH>Count</TH>
                  <TH align="right">System at count time</TH>
                  <TH align="right">Found</TH>
                  <TH align="right">Difference</TH>
                  <TH>Status</TH>
                  <TH>Raised</TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((adjustment) => (
                  <TR key={adjustment.id}>
                    <TD>
                      <Link href={`/dashboard/stock-adjustments/${adjustment.id}`} className="font-semibold text-brand-700 hover:underline">
                        {adjustment.item_name}
                      </Link>
                      {adjustment.status === "PENDING" && (
                        <div className="max-w-60 text-xs text-slate-500">
                          {adjustment.can_decide
                            ? adjustment.ledger_changed
                              ? "Ledger changed since the count: reject and count again"
                              : adjustment.would_go_negative
                                ? "Would take stock below zero: review"
                                : "Ready for your decision"
                            : waitingReason(adjustment)}
                        </div>
                      )}
                    </TD>
                    <TD className="whitespace-nowrap">
                      <Link href={`/dashboard/stock-counts/${adjustment.count_id}`} className="text-brand-700 hover:underline">
                        {adjustment.count_number}
                      </Link>
                      <div className="text-xs text-slate-500">{adjustment.counted_by_name} · {formatDateTime(adjustment.counted_at)}</div>
                    </TD>
                    <TD align="right" className="whitespace-nowrap">{plainQuantity(adjustment.system_balance_at_count)} {adjustment.unit_symbol}</TD>
                    <TD align="right" className="whitespace-nowrap">{plainQuantity(adjustment.physical_quantity)} {adjustment.unit_symbol}</TD>
                    <TD align="right" className={`font-semibold whitespace-nowrap ${Number(adjustment.difference) < 0 ? "text-red-700" : "text-emerald-700"}`}>
                      {signedDifference(adjustment.difference)} {adjustment.unit_symbol}
                    </TD>
                    <TD>
                      <Badge tone={ADJUSTMENT_TONES[adjustment.status]} dot>{ADJUSTMENT_LABELS[adjustment.status]}</Badge>
                    </TD>
                    <TD className="whitespace-nowrap">
                      {adjustment.raised_by_name}
                      <div className="text-xs text-slate-500">{formatDateTime(adjustment.raised_at)}</div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination page={data.page} pageCount={data.total_pages} total={data.total} pageSize={data.page_size}
              noun="adjustments" onPageChange={setPage} pageSizeOptions={PAGE_SIZES}
              onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />
          </div>
        )}
      </Card>
    </div>
  );
}
