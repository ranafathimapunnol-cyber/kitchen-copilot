"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CookingPot, Plus, X } from "lucide-react";

import { api } from "@/lib/api/client";
import { KITCHEN_ISSUES_ENDPOINT } from "@/lib/api/endpoints";
import { errorMessage, formatDateTime, formatDay } from "@/lib/payments";
import {
  STATUS_LABELS,
  STATUS_TONES,
  canRecordIssues,
  type DocumentStatus,
  type IssueListResponse,
} from "@/lib/kitchen";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SearchInput from "@/components/ui/SearchInput";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";

type StatusFilter = "ALL" | DocumentStatus;
const PAGE_SIZES = [20, 50, 100];

export default function KitchenIssuesPage() {
  const { role, permissions } = useAuthorization();
  const [status, setStatus] = useState<StatusFilter>("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<IssueListResponse | null>(null);
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
    if (status !== "ALL") params.set("status", status);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    if (query) params.set("search", query);
    return `${KITCHEN_ISSUES_ENDPOINT}?${params}`;
  }, [page, pageSize, status, dateFrom, dateTo, query]);
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    if (datesInvalid) return;
    let active = true;
    api
      .get<IssueListResponse>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load kitchen issues."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });
    return () => {
      active = false;
    };
  }, [url, requestKey, datesInvalid]);

  const counts = data?.status_counts;
  const filtered = status !== "ALL" || Boolean(dateFrom || dateTo || query);

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Operations"
        icon={CookingPot}
        title="Kitchen issues"
        description="Ingredients issued from the store to the kitchen for a meal session and menu, and unused stock returned. A draft changes no stock; confirming an issue takes the stock out, confirming a return puts it back. Net usage is issued minus returned."
        actions={
          canRecordIssues(role, permissions) ? (
            <Link
              href="/dashboard/kitchen-issues/new"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700"
            >
              <Plus size={16} aria-hidden />
              New issue
            </Link>
          ) : undefined
        }
      />

      <Card>
        <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 lg:flex-row lg:items-end lg:justify-between">
          <SegmentedControl<StatusFilter>
            label="Issue status"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={[
              { value: "ALL", label: "All" },
              ...(["DRAFT", "CONFIRMED", "CANCELLED", "REVERSED"] as DocumentStatus[]).map((value) => ({
                value,
                label: STATUS_LABELS[value],
                count: counts?.[value],
              })),
            ]}
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[repeat(2,minmax(0,10rem))_minmax(0,14rem)_auto] sm:items-end">
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
            <SearchInput value={search} onChange={setSearch} label="Search by issue number" placeholder="KI-00001" />
            <Button variant="ghost" icon={<X size={15} aria-hidden />} disabled={!filtered}
              onClick={() => { setStatus("ALL"); setDateFrom(""); setDateTo(""); setSearch(""); setPage(1); }}>
              Clear
            </Button>
          </div>
        </div>

        {error && !loading ? (
          <ErrorState title="Couldn't load kitchen issues" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : !data ? (
          <TableSkeleton rows={6} columns={7} />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={CookingPot}
            title={filtered ? "No issues match these filters" : "No kitchen issues yet"}
            description={filtered ? "Try another status, date range or number." : "Record what the store issues to the kitchen for each meal."}
          />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="980px">
              <THead>
                <tr>
                  <TH>Issue</TH>
                  <TH>Date</TH>
                  <TH>Session · menu</TH>
                  <TH>Items</TH>
                  <TH>Status</TH>
                  <TH>Recorded by</TH>
                  <TH>Confirmed</TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((issue) => (
                  <TR key={issue.id} muted={issue.status === "CANCELLED"}>
                    <TD className="whitespace-nowrap">
                      <Link href={`/dashboard/kitchen-issues/${issue.id}`} className="font-semibold text-brand-700 hover:underline">
                        {issue.issue_number}
                      </Link>
                    </TD>
                    <TD className="whitespace-nowrap">{formatDay(issue.issue_date)}</TD>
                    <TD>
                      <div className="font-medium text-slate-900">{issue.menu_name}</div>
                      <div className="text-xs text-slate-500">{issue.meal_session_name}</div>
                    </TD>
                    <TD className="max-w-64">
                      <span className="line-clamp-2" title={issue.item_names.join(", ")}>{issue.item_names.join(", ")}</span>
                      {issue.confirmed_return_count > 0 && (
                        <span className="text-xs text-slate-500">
                          {issue.confirmed_return_count} return{issue.confirmed_return_count > 1 ? "s" : ""}
                        </span>
                      )}
                    </TD>
                    <TD>
                      <Badge tone={STATUS_TONES[issue.status]} dot>{STATUS_LABELS[issue.status]}</Badge>
                    </TD>
                    <TD className="whitespace-nowrap">{issue.created_by_name ?? "—"}</TD>
                    <TD className="whitespace-nowrap text-slate-500">{issue.confirmed_at ? formatDateTime(issue.confirmed_at) : "—"}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination page={data.page} pageCount={data.total_pages} total={data.total} pageSize={data.page_size}
              noun="issues" onPageChange={setPage} pageSizeOptions={PAGE_SIZES}
              onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />
          </div>
        )}
      </Card>
    </div>
  );
}
