"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Copy, History, Plus, Weight } from "lucide-react";

import { api } from "@/lib/api/client";
import { PORTION_STANDARDS_ENDPOINT, PORTION_STANDARD_OPTIONS_ENDPOINT } from "@/lib/api/endpoints";
import { errorMessage, formatDay } from "@/lib/payments";
import {
  KIND_LABELS,
  SOURCE_LABELS,
  STANDARD_STATE_LABELS,
  STANDARD_STATE_TONES,
  type StandardListResponse,
  type StandardOptions,
  type StandardStatus,
} from "@/lib/planning";
import { plainQuantity } from "@/lib/stockMath";
import { CopyModal, StandardModal } from "@/components/planning/StandardModals";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SegmentedControl from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

type StatusFilter = "ALL" | StandardStatus;
const PAGE_SIZES = [50, 100, 200];

export default function PortionStandardsPage() {
  const router = useRouter();
  const toast = useToast();
  const [status, setStatus] = useState<StatusFilter>("ALL");
  const [menuId, setMenuId] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [data, setData] = useState<StandardListResponse | null>(null);
  const [options, setOptions] = useState<StandardOptions | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");
  const [dialog, setDialog] = useState<"new" | "copy" | null>(null);

  const url = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status !== "ALL") params.set("status", status);
    if (menuId) params.set("menu_id", menuId);
    return `${PORTION_STANDARDS_ENDPOINT}?${params}`;
  }, [page, pageSize, status, menuId]);
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    let active = true;
    api
      .get<StandardListResponse>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load portion standards."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });
    return () => {
      active = false;
    };
  }, [url, requestKey]);

  useEffect(() => {
    api.get<StandardOptions>(PORTION_STANDARD_OPTIONS_ENDPOINT).then(setOptions).catch(() => setOptions(null));
  }, []);

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Menu Planning"
        icon={Weight}
        title="Portion Standards"
        description="Approved per-person quantities by menu and item, with effective dates. A change is a new version: plans dated on or after its date use it, and approved plans keep the values they were approved with."
        actions={
          <>
            <Link href="/dashboard/portion-standards/suggest"
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50">
              <History size={16} aria-hidden />
              Suggest from past meals
            </Link>
            <Button variant="secondary" icon={<Copy size={15} aria-hidden />} disabled={!options} onClick={() => setDialog("copy")}>
              Copy from menu
            </Button>
            <Button icon={<Plus size={16} aria-hidden />} disabled={!options} onClick={() => setDialog("new")}>New draft</Button>
          </>
        }
      />

      <Card>
        <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 lg:flex-row lg:items-end lg:justify-between">
          <SegmentedControl<StatusFilter>
            label="Standard status"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setPage(1);
            }}
            options={[
              { value: "ALL", label: "All" },
              { value: "DRAFT", label: "Drafts", count: data?.status_counts.DRAFT },
              { value: "APPROVED", label: "Approved", count: data?.status_counts.APPROVED },
              { value: "CANCELLED", label: "Cancelled", count: data?.status_counts.CANCELLED },
            ]}
          />
          <Field label="Menu" className="sm:w-72">
            {({ id }) => (
              <SelectInput id={id} className="h-9" value={menuId} onChange={(event) => { setMenuId(event.target.value); setPage(1); }}>
                <option value="">All menus</option>
                {options?.menus.map((m) => <option key={m.id} value={m.id}>{m.name} ({m.meal_session_name})</option>)}
              </SelectInput>
            )}
          </Field>
        </div>

        {error && !loading ? (
          <ErrorState title="Couldn't load portion standards" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
        ) : !data ? (
          <TableSkeleton rows={6} columns={6} />
        ) : data.items.length === 0 ? (
          <EmptyState icon={Weight}
            title={status !== "ALL" || menuId ? "No standards match these filters" : "No portion standards yet"}
            description="Create a draft, copy a menu's main items as drafts, or suggest one from past meals. Each draft needs approval." />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
            <Table minWidth="980px">
              <THead>
                <tr>
                  <TH>Menu</TH>
                  <TH>Item</TH>
                  <TH align="right">Per person</TH>
                  <TH>Effective from</TH>
                  <TH>Version</TH>
                  <TH>State</TH>
                  <TH>Source</TH>
                </tr>
              </THead>
              <TBody>
                {data.items.map((row) => (
                  <TR key={row.id} muted={row.state === "CANCELLED" || row.state === "SUPERSEDED"}>
                    <TD>
                      {row.menu_name}
                      <div className="text-xs text-slate-500">{row.meal_session_name}</div>
                    </TD>
                    <TD>
                      <Link href={`/dashboard/portion-standards/${row.id}`} className="font-semibold text-brand-700 hover:underline">{row.item_name}</Link>
                      <div className="text-xs text-slate-500">{row.item_kind ? KIND_LABELS[row.item_kind] : "Not classified"}</div>
                    </TD>
                    <TD align="right" className="whitespace-nowrap">{plainQuantity(row.quantity_per_person)} {row.unit_symbol}</TD>
                    <TD className="whitespace-nowrap">{formatDay(row.effective_from)}</TD>
                    <TD>{row.version_no ? `v${row.version_no}` : "—"}</TD>
                    <TD className="whitespace-nowrap"><Badge tone={STANDARD_STATE_TONES[row.state]} dot>{STANDARD_STATE_LABELS[row.state]}</Badge></TD>
                    <TD className="text-slate-600">{SOURCE_LABELS[row.source] ?? row.source}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <Pagination page={data.page} pageCount={data.total_pages} total={data.total} pageSize={data.page_size}
              noun="standards" onPageChange={setPage} pageSizeOptions={PAGE_SIZES}
              onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />
          </div>
        )}
      </Card>

      {dialog === "new" && options && (
        <StandardModal options={options} onClose={() => setDialog(null)}
          onSaved={(saved) => { toast.success("Draft standard created."); router.push(`/dashboard/portion-standards/${saved.id}`); }} />
      )}
      {dialog === "copy" && options && (
        <CopyModal options={options} onClose={() => setDialog(null)} onCopied={() => setReloadKey((key) => key + 1)} />
      )}
    </div>
  );
}
