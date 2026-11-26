"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ClipboardCheck, ListChecks, Plus, X } from "lucide-react";

import { api } from "@/lib/api/client";
import { STOCK_COUNTS_ENDPOINT } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime, type Page } from "@/lib/payments";
import { canRecordCounts, type CountSummary } from "@/lib/stockCounts";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SearchInput from "@/components/ui/SearchInput";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

const PAGE_SIZES = [20, 50, 100];

export default function StockCountsPage() {
  const { role, permissions } = useAuthorization();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<Page<CountSummary> | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const datesInvalid = Boolean(dateFrom && dateTo) && dateFrom > dateTo;
  const url = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    if (query) params.set("search", query);
    return `${STOCK_COUNTS_ENDPOINT}?${params}`;
  }, [page, pageSize, dateFrom, dateTo, query]);
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    if (datesInvalid) return;
    let active = true;
    api
      .get<Page<CountSummary>>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load stock counts."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });
    return () => {
      active = false;
    };
  }, [url, requestKey, datesInvalid]);

  const filtered = Boolean(dateFrom || dateTo || query);

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Inventory"
        icon={ClipboardCheck}
        title="Stock counts"
        description="Physical counts of the store. Each count keeps the system balance at the time it was saved, the quantity found and the difference; it is never changed. Stock changes only through an approved adjustment."
        actions={
          <>
            <Link href="/dashboard/stock-adjustments"
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm transition-colors hover:bg-slate-50">
              <ListChecks size={16} aria-hidden />
              Adjustments
            </Link>
            {canRecordCounts(role, permissions) && (
              <Link href="/dashboard/stock-counts/new"
                className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700">
                <Plus size={16} aria-hidden />
                New count
              </Link>
            )}
          </>
        }
      />

      <Card>
        <div className="grid grid-cols-1 gap-3 border-b border-slate-100 px-5 py-4 sm:grid-cols-[repeat(2,minmax(0,10rem))_minmax(0,14rem)_auto] sm:items-end">
          <Field label="From">
            {({ id }) => (
              <TextInput id={id} type="date" className="h-9" value={dateFrom} max={dateTo || undefined}
                onChange={(event) => { setDateFrom(event.target.value); setPage(1); }} />
            )}
          </Field>
          <Field label="To" error={datesInvalid ? "Must be on or after From." : undefined}>
            {({ id }) => (
              <TextInput id={id} type="date" className="h-9" value={dateTo} min={dateFrom || undefined}
                onChange={(event) => { setDateTo(event.target.value); setPage(1); }} />
            )}
          </Field>
          <SearchInput value={search} onChange={setSearch} label="Search by count number" placeholder="SC-00001" />
          <Button variant="ghost" icon={<X size={15} aria-hidden />} disabled={!filtered}
            onClick={() => { setDateFrom(""); setDateTo(""); setSearch(""); setPage(1); }}>
            Clear
          </Button>
        </div>

        {error && !loading ? (
          <ErrorState title="Couldn't load stock counts" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : !data ? (
          <TableSkeleton rows={6} columns={6} />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={ClipboardCheck}
            title={filtered ? "No counts match these filters" : "No stock counts yet"}
            description={filtered ? "Try another date range or number." : "Record a physical count to compare the store with the system."}
          />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="900px">
              <THead>
                <tr>
                  <TH>Count</TH>
                  <TH>Counted</TH>
                  <TH>Verifier</TH>
                  <TH>Items</TH>
                  <TH>Differences</TH>
                  <TH>Adjustments</TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((count) => (
                  <TR key={count.id}>
                    <TD className="whitespace-nowrap">
                      <Link href={`/dashboard/stock-counts/${count.id}`} className="font-semibold text-brand-700 hover:underline">
                        {count.count_number}
                      </Link>
                    </TD>
                    <TD className="whitespace-nowrap">{formatDateTime(count.counted_at)}</TD>
                    <TD className="whitespace-nowrap">{count.counted_by_name ?? "—"}</TD>
                    <TD className="max-w-64">
                      <span className="line-clamp-2" title={count.item_names.join(", ")}>{count.item_names.join(", ")}</span>
                      <span className="text-xs text-slate-500">{count.reason}</span>
                    </TD>
                    <TD className="whitespace-nowrap">
                      {count.difference_count === 0 ? (
                        <Badge tone="success">All match</Badge>
                      ) : (
                        <span>{count.difference_count} of {count.line_count}</span>
                      )}
                    </TD>
                    <TD>
                      <div className="flex flex-wrap gap-1.5">
                        {count.pending_count > 0 && <Badge tone="warning" dot>{count.pending_count} pending</Badge>}
                        {count.approved_count > 0 && <Badge tone="success" dot>{count.approved_count} approved</Badge>}
                        {count.rejected_count > 0 && <Badge tone="danger" dot>{count.rejected_count} rejected</Badge>}
                        {count.not_raised_count > 0 && <Badge tone="neutral">{count.not_raised_count} not raised</Badge>}
                        {count.difference_count === 0 && <span className="text-slate-400">—</span>}
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination page={data.page} pageCount={data.total_pages} total={data.total} pageSize={data.page_size}
              noun="counts" onPageChange={setPage} pageSizeOptions={PAGE_SIZES}
              onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />
          </div>
        )}
      </Card>
    </div>
  );
}
