"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, History, Undo2 } from "lucide-react";

import { api } from "@/lib/api/client";
import { itemLedgerEndpoint } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime } from "@/lib/payments";
import { movementLabel, movementTone, type ItemLedgerResponse, type LedgerMovement } from "@/lib/stock";
import { plainQuantity, signedQuantity, stockState } from "@/lib/stockMath";
import Badge from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

const PAGE_SIZES = [50, 100];

function Source({ movement }: { movement: LedgerMovement }) {
  if (movement.receipt_id) {
    return (
      <Link href={`/dashboard/receipts/${movement.receipt_id}`} className="text-brand-700 hover:underline">
        GR-{movement.receipt_id}
        {movement.invoice_number && (
          <span className="text-slate-500">
            {" "}· {movement.invoice_number}
            {movement.supplier_name ? ` · ${movement.supplier_name}` : ""}
          </span>
        )}
      </Link>
    );
  }
  if (movement.opening_id) {
    return <span>Opening stock #{movement.opening_id}</span>;
  }
  if (movement.kitchen_issue_id && movement.document_number) {
    return (
      <Link href={`/dashboard/kitchen-issues/${movement.kitchen_issue_id}`} className="text-brand-700 hover:underline">
        {movement.document_number}
      </Link>
    );
  }
  if (movement.stock_count_id && movement.document_number) {
    return (
      <Link href={`/dashboard/stock-counts/${movement.stock_count_id}`} className="text-brand-700 hover:underline">
        {movement.document_number}
      </Link>
    );
  }
  return (
    <span>
      {movement.reference_type} #{movement.reference_id}
    </span>
  );
}

function Fact({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-200 bg-white px-5 py-4 shadow-card">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold tracking-tight text-slate-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export default function ItemLedgerPage() {
  const params = useParams<{ itemId: string }>();
  const itemId = params.itemId;
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<ItemLedgerResponse | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");

  const url = `${itemLedgerEndpoint(itemId)}?page=${page}&page_size=${pageSize}`;
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    let active = true;
    api
      .get<ItemLedgerResponse>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load the item ledger."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });
    return () => {
      active = false;
    };
  }, [url, requestKey]);

  const back = (
    <Link
      href="/dashboard/stock"
      className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900"
    >
      <ArrowLeft size={15} aria-hidden />
      Stock balances
    </Link>
  );

  if (error && !loading && !data) {
    return (
      <div className="space-y-4 pb-6">
        {back}
        <Card>
          <ErrorState title="Couldn't load the item ledger" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        </Card>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4 pb-6">
        {back}
        <Card>
          <TableSkeleton rows={6} columns={7} />
        </Card>
      </div>
    );
  }

  const item = data.item;
  const state = stockState(item);
  const unit = item.unit_symbol ?? "";

  return (
    <div className="space-y-6 pb-6">
      {back}
      <PageHeader
        eyebrow="Stock ledger"
        icon={History}
        title={item.item_name}
        description="Every posted movement of this item, newest first. The balance after each movement replays the ledger in order of when the stock moved, then the order it was posted. Posted movements are never edited; a correction appears as a reversal."
        meta={
          <>
            <Badge>{item.category_name ?? "No category"}</Badge>
            {!item.is_active && <Badge>Inactive item</Badge>}
            {state === "below" && <Badge tone="warning" dot>Below minimum</Badge>}
            {state === "out" && <Badge tone="danger" dot>Out of stock</Badge>}
          </>
        }
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3" aria-label="Item stock">
        <Fact label="Balance" value={`${plainQuantity(item.balance)} ${unit}`} hint="From posted movements" />
        <Fact
          label="Minimum stock"
          value={item.has_minimum ? `${plainQuantity(item.minimum_stock)} ${unit}` : "Not set"}
          hint={item.below_minimum ? `${plainQuantity(item.shortfall)} ${unit} needed` : undefined}
        />
        <Fact label="Movements" value={String(data.total)} hint={item.last_movement_at ? `Latest effective ${formatDateTime(item.last_movement_at)}` : undefined} />
      </section>

      <Card>
        {data.movements.length === 0 ? (
          <EmptyState
            icon={History}
            title="No movements yet"
            description="Stock moves when opening stock is recorded or a goods receipt is accepted."
          />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="1040px">
              <THead>
                <tr>
                  <TH>Effective</TH>
                  <TH>Type</TH>
                  <TH align="right">Quantity</TH>
                  <TH align="right">Balance after</TH>
                  <TH>Source</TH>
                  <TH>Recorded by</TH>
                  <TH>Posted</TH>
                  <TH>Remarks</TH>
                </tr>
              </THead>
              <TBody>
                {data.movements.map((movement) => (
                  <TR key={movement.id} muted={Boolean(movement.reversed_by_movement_id)}>
                    <TD className="whitespace-nowrap">{formatDateTime(movement.effective_at)}</TD>
                    <TD>
                      <div className="flex flex-col items-start gap-1">
                        <Badge tone={movementTone(movement.movement_type)}>{movementLabel(movement.movement_type)}</Badge>
                        {movement.reversal_of_id && (
                          <span className="text-xs text-slate-500">Reverses movement #{movement.reversal_of_id}</span>
                        )}
                        {movement.reversed_by_movement_id && (
                          <span className="inline-flex items-center gap-1 text-xs text-amber-800">
                            <Undo2 size={12} aria-hidden />
                            Reversed by #{movement.reversed_by_movement_id}
                          </span>
                        )}
                      </div>
                    </TD>
                    <TD
                      align="right"
                      className={`font-medium whitespace-nowrap ${movement.direction < 0 ? "text-red-700" : "text-emerald-700"}`}
                    >
                      {signedQuantity(movement.direction, movement.quantity)} {movement.unit_symbol}
                    </TD>
                    <TD align="right" className="font-semibold whitespace-nowrap text-slate-900">
                      {plainQuantity(movement.balance_after)} {movement.unit_symbol}
                    </TD>
                    <TD className="whitespace-nowrap">
                      <Source movement={movement} />
                    </TD>
                    <TD className="whitespace-nowrap">{movement.created_by_name ?? "—"}</TD>
                    <TD className="whitespace-nowrap text-slate-500">
                      <span className="text-xs">#{movement.id}</span> · {formatDateTime(movement.created_at)}
                    </TD>
                    <TD className="max-w-56 truncate" title={movement.remarks ?? undefined}>
                      {movement.remarks ?? <span className="text-slate-400">—</span>}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination
              page={data.page}
              pageCount={data.total_pages}
              total={data.total}
              pageSize={data.page_size}
              noun="movements"
              onPageChange={setPage}
              pageSizeOptions={PAGE_SIZES}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
            />
          </div>
        )}
      </Card>
    </div>
  );
}
