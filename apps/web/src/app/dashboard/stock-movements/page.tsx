"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeftRight, CalendarDays, PackageCheck, X } from "lucide-react";

import { api } from "@/lib/api/client";
import { ENDPOINTS, STOCK_MOVEMENTS_ENDPOINT } from "@/lib/api/endpoints";
import { errorMessage, fetchAllPages, formatDateTime, type Page } from "@/lib/payments";
import { type StockMovementRow } from "@/lib/receipts";
import { MOVEMENT_TYPE_LABELS, movementLabel, movementTone } from "@/lib/stock";
import { signedQuantity } from "@/lib/stockMath";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import SearchSelect from "@/components/ui/SearchSelect";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type Filters = { itemId: string; type: string; dateFrom: string; dateTo: string };
type ItemOption = { id: number; name: string; is_active?: boolean };

const NO_FILTERS: Filters = { itemId: "", type: "", dateFrom: "", dateTo: "" };
const PAGE_SIZES = [20, 50, 100];

function StockMovements() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const receiptFilter = Number(searchParams.get("receipt")) || null;

  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<Page<StockMovementRow> | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");
  const [items, setItems] = useState<ItemOption[]>([]);

  const filtersInvalid = Boolean(filters.dateFrom && filters.dateTo) && filters.dateFrom > filters.dateTo;
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (filters.itemId) params.set("item_id", filters.itemId);
  if (filters.type) params.set("movement_type", filters.type);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (receiptFilter) params.set("receipt_id", String(receiptFilter));
  const url = `${STOCK_MOVEMENTS_ENDPOINT}?${params}`;
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    if (filtersInvalid) return;
    let active = true;
    api
      .get<Page<StockMovementRow>>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load stock movements."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });
    return () => {
      active = false;
    };
  }, [url, requestKey, filtersInvalid]);

  useEffect(() => {
    let active = true;
    fetchAllPages<ItemOption>(ENDPOINTS.items)
      .then(({ items: all }) => {
        if (active) setItems([...all].sort((a, b) => a.name.localeCompare(b.name)));
      })
      .catch(() => {
        // The log still works without the item filter.
      });
    return () => {
      active = false;
    };
  }, []);

  function update(key: keyof Filters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  }

  const filtered = Object.values(filters).some(Boolean) || Boolean(receiptFilter);

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Inventory"
        icon={ArrowLeftRight}
        title="Stock movements"
        description="Every posted change to stock, newest posting first, in each item's standard unit: opening stock, accepted goods receipts, kitchen issues, unused returns and reversals. Count adjustments will appear here when stock counts arrive. Posted movements are never edited; a correction is a reversal."
        actions={
          <Link
            href="/dashboard/receipts"
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50"
          >
            <PackageCheck size={15} aria-hidden />
            Goods receipts
          </Link>
        }
      />

      {receiptFilter && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-800">
          <span>
            Showing the stock posted by receipt{" "}
            <Link href={`/dashboard/receipts/${receiptFilter}`} className="font-semibold hover:underline">
              GR-{receiptFilter}
            </Link>
            .
          </span>
          <Button size="sm" variant="ghost" icon={<X size={14} aria-hidden />} onClick={() => router.replace("/dashboard/stock-movements")}>
            Show all movements
          </Button>
        </div>
      )}

      <Card>
        <div className="grid grid-cols-1 gap-4 border-b border-slate-100 p-5 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))_auto] lg:items-end">
          <Field label="Item">
            {({ id }) => (
              <SearchSelect
                id={id}
                value={filters.itemId}
                noun="items"
                emptyLabel="All items"
                options={items.map((item) => ({
                  value: String(item.id),
                  label: `${item.name}${item.is_active === false ? " (inactive)" : ""}`,
                }))}
                onChange={(value) => update("itemId", value)}
              />
            )}
          </Field>
          <Field label="Type">
            {({ id }) => (
              <SelectInput id={id} value={filters.type} onChange={(event) => update("type", event.target.value)}>
                <option value="">All types</option>
                {Object.entries(MOVEMENT_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </SelectInput>
            )}
          </Field>
          <Field label="Posted from">
            {({ id }) => (
              <TextInput
                id={id}
                type="date"
                value={filters.dateFrom}
                max={filters.dateTo || undefined}
                onChange={(event) => update("dateFrom", event.target.value)}
              />
            )}
          </Field>
          <Field label="Posted to" error={filtersInvalid ? "Must be on or after the From date." : undefined}>
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                type="date"
                aria-describedby={describedBy}
                aria-invalid={filtersInvalid}
                value={filters.dateTo}
                min={filters.dateFrom || undefined}
                onChange={(event) => update("dateTo", event.target.value)}
              />
            )}
          </Field>
          <Button
            variant="ghost"
            disabled={!Object.values(filters).some(Boolean)}
            icon={<X size={15} aria-hidden />}
            onClick={() => {
              setFilters(NO_FILTERS);
              setPage(1);
            }}
          >
            Clear
          </Button>
        </div>

        {filtersInvalid ? (
          <EmptyState icon={CalendarDays} title="Check the date range" description="The From date must be on or before the To date." />
        ) : error && !loading ? (
          <ErrorState title="Couldn't load stock movements" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : !data ? (
          <TableSkeleton rows={6} columns={7} />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={ArrowLeftRight}
            title={filtered ? "No movements match these filters" : "No stock movements yet"}
            description={
              filtered ? "Try another item, type or date range." : "Stock moves when opening stock is recorded or a goods receipt is accepted."
            }
          />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="1060px">
              <THead>
                <tr>
                  <TH>Effective</TH>
                  <TH>Item</TH>
                  <TH>Type</TH>
                  <TH align="right">Quantity</TH>
                  <TH>Source</TH>
                  <TH>Recorded by</TH>
                  <TH>Posted</TH>
                  <TH>Remarks</TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((movement) => (
                  <TR key={movement.id} muted={Boolean(movement.reversed_by_movement_id)}>
                    <TD className="whitespace-nowrap">{formatDateTime(movement.effective_at ?? movement.created_at)}</TD>
                    <TD className="font-medium text-slate-900">
                      <Link href={`/dashboard/stock/${movement.item_id}`} className="hover:text-brand-700 hover:underline">
                        {movement.item_name ?? `Item #${movement.item_id}`}
                      </Link>
                    </TD>
                    <TD>
                      <div className="flex flex-col items-start gap-1">
                        <Badge tone={movementTone(movement.movement_type)}>{movementLabel(movement.movement_type)}</Badge>
                        {movement.reversal_of_id && (
                          <span className="text-xs text-slate-500">Reverses #{movement.reversal_of_id}</span>
                        )}
                        {movement.reversed_by_movement_id && (
                          <span className="text-xs text-amber-800">Reversed by #{movement.reversed_by_movement_id}</span>
                        )}
                      </div>
                    </TD>
                    <TD
                      align="right"
                      className={`whitespace-nowrap tabular-nums font-medium ${(movement.direction ?? 1) < 0 ? "text-red-700" : "text-emerald-700"}`}
                    >
                      {signedQuantity(movement.direction ?? 1, movement.quantity)} {movement.unit_symbol}
                    </TD>
                    <TD className="whitespace-nowrap">
                      {movement.receipt_id ? (
                        <Link href={`/dashboard/receipts/${movement.receipt_id}`} className="text-brand-700 hover:underline">
                          GR-{movement.receipt_id}
                          <span className="text-slate-500">
                            {" "}· {movement.invoice_number} · {movement.supplier_name}
                          </span>
                        </Link>
                      ) : movement.opening_id ? (
                        `Opening stock #${movement.opening_id}`
                      ) : movement.kitchen_issue_id && movement.document_number ? (
                        <Link href={`/dashboard/kitchen-issues/${movement.kitchen_issue_id}`} className="text-brand-700 hover:underline">
                          {movement.document_number}
                        </Link>
                      ) : movement.stock_count_id && movement.document_number ? (
                        <Link href={`/dashboard/stock-counts/${movement.stock_count_id}`} className="text-brand-700 hover:underline">
                          {movement.document_number}
                        </Link>
                      ) : (
                        `${movement.reference_type} #${movement.reference_id}`
                      )}
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

export default function StockMovementsPage() {
  return (
    <Suspense
      fallback={
        <Card>
          <TableSkeleton rows={6} columns={7} />
        </Card>
      }
    >
      <StockMovements />
    </Suspense>
  );
}
