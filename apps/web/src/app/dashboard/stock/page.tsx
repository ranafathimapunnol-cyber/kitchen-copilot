"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeftRight,
  Boxes,
  PackageOpen,
  PackagePlus,
  ShoppingCart,
  TriangleAlert,
  Warehouse,
} from "lucide-react";

import { api } from "@/lib/api/client";
import {
  ENDPOINTS,
  STOCK_BALANCES_ENDPOINT,
  STOCK_REPLENISHMENT_ENDPOINT,
} from "@/lib/api/endpoints";
import { fetchAllRecords } from "@/lib/api/list";
import { errorMessage, formatDateTime, formatDay } from "@/lib/payments";
import {
  canManageOpeningStock,
  type BalancesResponse,
  type ReplenishmentResponse,
  type StockBalance,
} from "@/lib/stock";
import { levelRatio, plainQuantity, stockState, type StockState } from "@/lib/stockMath";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import { INK, SERIES } from "@/components/charts/tokens";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { SelectInput } from "@/components/ui/Field";
import PageHeader from "@/components/ui/PageHeader";
import Pagination from "@/components/ui/Pagination";
import SearchInput from "@/components/ui/SearchInput";
import SegmentedControl from "@/components/ui/SegmentedControl";
import StatCard from "@/components/ui/StatCard";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { cn } from "@/components/ui/cn";

type View = "balances" | "replenishment";
type CategoryOption = { id: number; name: string };

const PAGE_SIZES = [20, 50, 100];

const STATE_BADGE: Record<StockState, { tone: BadgeTone; label: string }> = {
  below: { tone: "warning", label: "Below minimum" },
  out: { tone: "danger", label: "Out of stock" },
  ok: { tone: "success", label: "At or above minimum" },
  "no-minimum": { tone: "neutral", label: "No minimum set" },
};

const linkButton =
  "inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50";

function LevelBar({ row }: { row: StockBalance }) {
  const state = stockState(row);
  if (state === "no-minimum") return null;
  const ratio = levelRatio(row.balance, row.minimum_stock);
  return (
    <div
      className="mt-1.5 h-1.5 w-24 overflow-hidden rounded-full bg-slate-100"
      role="img"
      aria-label={`${Math.round(ratio * 100)}% of the minimum stock`}
    >
      <div
        className={cn(
          "h-full rounded-full",
          state === "ok" ? "bg-emerald-500" : state === "below" ? "bg-amber-500" : "bg-red-500"
        )}
        style={{ width: `${Math.max(ratio * 100, state === "out" ? 0 : 4)}%` }}
      />
    </div>
  );
}

function ItemCell({ row }: { row: StockBalance }) {
  return (
    <div className="min-w-0">
      <Link
        href={`/dashboard/stock/${row.item_id}`}
        className="font-medium text-slate-900 hover:text-brand-700 hover:underline"
      >
        {row.item_name}
      </Link>
      <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
        <span>{row.category_name ?? "—"}</span>
        {!row.is_active && <Badge>Inactive</Badge>}
      </div>
    </div>
  );
}

function StockBalances() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { role } = useAuthorization();
  const view: View = searchParams.get("view") === "replenishment" ? "replenishment" : "balances";

  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [belowOnly, setBelowOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [categories, setCategories] = useState<CategoryOption[]>([]);

  const [data, setData] = useState<BalancesResponse | null>(null);
  const [error, setError] = useState("");
  const [loadedKey, setLoadedKey] = useState("");

  const [replenishment, setReplenishment] = useState<ReplenishmentResponse | null>(null);
  const [replenishmentError, setReplenishmentError] = useState("");

  // Search as you type, without a request per keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (query) params.set("search", query);
  if (categoryId) params.set("category_id", categoryId);
  if (belowOnly) params.set("below_minimum", "true");
  const url = `${STOCK_BALANCES_ENDPOINT}?${params}`;
  const requestKey = `${url}#${reloadKey}`;
  const loading = loadedKey !== requestKey;

  useEffect(() => {
    let active = true;
    api
      .get<BalancesResponse>(url)
      .then((response) => {
        if (!active) return;
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "Unable to load stock balances."));
      })
      .finally(() => {
        if (active) setLoadedKey(requestKey);
      });
    return () => {
      active = false;
    };
  }, [url, requestKey]);

  useEffect(() => {
    let active = true;
    api
      .get<ReplenishmentResponse>(STOCK_REPLENISHMENT_ENDPOINT)
      .then((response) => {
        if (!active) return;
        setReplenishment(response);
        setReplenishmentError("");
      })
      .catch((err: unknown) => {
        if (active) setReplenishmentError(errorMessage(err, "Unable to load the replenishment list."));
      });
    return () => {
      active = false;
    };
  }, [reloadKey]);

  useEffect(() => {
    let active = true;
    fetchAllRecords<CategoryOption>(ENDPOINTS.categories)
      .then(({ rows }) => {
        if (active) setCategories([...rows].sort((a, b) => a.name.localeCompare(b.name)));
      })
      .catch(() => {
        // The list still works without the category filter.
      });
    return () => {
      active = false;
    };
  }, []);

  function switchView(next: View) {
    router.replace(next === "replenishment" ? "/dashboard/stock?view=replenishment" : "/dashboard/stock");
  }

  const filtered = Boolean(query || categoryId || belowOnly);
  const summary = data?.summary;

  return (
    <div className="space-y-6 pb-6">
      <PageHeader
        eyebrow="Inventory"
        icon={Warehouse}
        title="Stock balances"
        description="Calculated from posted stock movements, in each item's standard unit. Items below their minimum stock are flagged, and the replenishment list shows how much is needed to reach the minimum."
        actions={
          <>
            {canManageOpeningStock(role) && (
              <Link href="/dashboard/opening-stock" className={linkButton}>
                <PackagePlus size={15} aria-hidden />
                Opening stock
              </Link>
            )}
            <Link href="/dashboard/stock-movements" className={linkButton}>
              <ArrowLeftRight size={15} aria-hidden />
              Stock movements
            </Link>
          </>
        }
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3" aria-label="Stock summary">
        <StatCard
          label="Items tracked"
          value={summary ? String(summary.items) : "—"}
          description={summary ? `${summary.without_minimum} without a minimum stock` : undefined}
          icon={Boxes}
          accent={SERIES.blue}
        />
        <StatCard
          label="Below minimum"
          value={summary ? String(summary.below_minimum) : "—"}
          description="Need replenishing"
          icon={TriangleAlert}
          accent={SERIES.orange}
        />
        <StatCard
          label="Nothing in stock"
          value={summary ? String(summary.zero_or_less) : "—"}
          description="Balance of zero"
          icon={PackageOpen}
          accent={INK.negative}
        />
      </section>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <SegmentedControl<View>
            label="Stock view"
            value={view}
            onChange={switchView}
            options={[
              { value: "balances", label: "All balances" },
              { value: "replenishment", label: "Replenishment list", count: replenishment?.total },
            ]}
          />
          {view === "replenishment" && replenishment && (
            <p className="text-xs text-slate-500">
              As of {formatDay(replenishment.campus_date)} · {formatDateTime(replenishment.generated_at)}
            </p>
          )}
        </div>

        {view === "balances" ? (
          <>
            <div className="grid grid-cols-1 gap-3 border-b border-slate-100 p-5 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] sm:items-center">
              <SearchInput value={search} onChange={setSearch} label="Search items" placeholder="Search items…" />
              <SelectInput
                aria-label="Category"
                className="h-9"
                value={categoryId}
                onChange={(event) => {
                  setCategoryId(event.target.value);
                  setPage(1);
                }}
              >
                <option value="">All categories</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </SelectInput>
              <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  checked={belowOnly}
                  onChange={(event) => {
                    setBelowOnly(event.target.checked);
                    setPage(1);
                  }}
                />
                Below minimum only
              </label>
            </div>

            {error && !loading ? (
              <ErrorState title="Couldn't load stock balances" message={error} onRetry={() => setReloadKey((key) => key + 1)} />
            ) : !data ? (
              <TableSkeleton rows={6} columns={6} />
            ) : data.items.length === 0 ? (
              <EmptyState
                icon={Warehouse}
                title={filtered ? "No items match these filters" : "No stock items yet"}
                description={filtered ? "Try another search, category or filter." : "Items appear here once they are added to master data."}
              />
            ) : (
              <div className={loading ? "opacity-60 transition-opacity" : undefined} aria-busy={loading}>
                <Table minWidth="820px">
                  <THead>
                    <tr>
                      <TH>Item</TH>
                      <TH align="right">Balance</TH>
                      <TH align="right">Minimum</TH>
                      <TH>Level</TH>
                      <TH align="right">Needed</TH>
                      <TH>Last movement</TH>
                    </tr>
                  </THead>
                  <TBody>
                    {data.items.map((row) => {
                      const state = stockState(row);
                      return (
                        <TR key={row.item_id} muted={!row.is_active}>
                          <TD>
                            <ItemCell row={row} />
                          </TD>
                          <TD align="right" className="font-semibold whitespace-nowrap text-slate-900">
                            {plainQuantity(row.balance)} <span className="font-normal text-slate-500">{row.unit_symbol}</span>
                          </TD>
                          <TD align="right" className="whitespace-nowrap">
                            {row.has_minimum ? `${plainQuantity(row.minimum_stock)} ${row.unit_symbol ?? ""}` : "—"}
                          </TD>
                          <TD>
                            <Badge tone={STATE_BADGE[state].tone} dot>
                              {STATE_BADGE[state].label}
                            </Badge>
                            <LevelBar row={row} />
                          </TD>
                          <TD align="right" className="whitespace-nowrap">
                            {row.below_minimum ? (
                              <span className="font-medium text-amber-800">
                                {plainQuantity(row.shortfall)} {row.unit_symbol}
                              </span>
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </TD>
                          <TD className="whitespace-nowrap text-slate-500">
                            {row.last_movement_at ? formatDateTime(row.last_movement_at) : "No movements"}
                          </TD>
                        </TR>
                      );
                    })}
                  </TBody>
                </Table>
                <Pagination
                  page={data.page}
                  pageCount={data.total_pages}
                  total={data.total}
                  pageSize={data.page_size}
                  noun="items"
                  onPageChange={setPage}
                  pageSizeOptions={PAGE_SIZES}
                  onPageSizeChange={(size) => {
                    setPageSize(size);
                    setPage(1);
                  }}
                />
              </div>
            )}
          </>
        ) : replenishmentError ? (
          <ErrorState
            title="Couldn't load the replenishment list"
            message={replenishmentError}
            onRetry={() => setReloadKey((key) => key + 1)}
          />
        ) : !replenishment ? (
          <TableSkeleton rows={5} columns={5} />
        ) : replenishment.items.length === 0 ? (
          <EmptyState
            icon={ShoppingCart}
            title="Nothing to replenish"
            description="Every active item with a minimum stock is at or above its minimum."
          />
        ) : (
          <>
            <p className="border-b border-slate-100 px-5 py-3 text-sm text-slate-600">
              {replenishment.total} active {replenishment.total === 1 ? "item is" : "items are"} below the minimum stock.
              &ldquo;Needed&rdquo; is the quantity that brings each back to its minimum.
            </p>
            <Table minWidth="680px">
              <THead>
                <tr>
                  <TH>Category</TH>
                  <TH>Item</TH>
                  <TH align="right">In stock</TH>
                  <TH align="right">Minimum</TH>
                  <TH align="right">Needed</TH>
                </tr>
              </THead>
              <TBody>
                {replenishment.items.map((row) => (
                  <TR key={row.item_id}>
                    <TD className="whitespace-nowrap text-slate-500">{row.category_name ?? "—"}</TD>
                    <TD>
                      <Link
                        href={`/dashboard/stock/${row.item_id}`}
                        className="font-medium text-slate-900 hover:text-brand-700 hover:underline"
                      >
                        {row.item_name}
                      </Link>
                    </TD>
                    <TD align="right" className="whitespace-nowrap">
                      {plainQuantity(row.balance)} {row.unit_symbol}
                    </TD>
                    <TD align="right" className="whitespace-nowrap">
                      {plainQuantity(row.minimum_stock)} {row.unit_symbol}
                    </TD>
                    <TD align="right" className="font-semibold whitespace-nowrap text-slate-900">
                      {plainQuantity(row.shortfall)} {row.unit_symbol}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </>
        )}
      </Card>
    </div>
  );
}

export default function StockBalancesPage() {
  return (
    <Suspense
      fallback={
        <Card>
          <TableSkeleton rows={6} columns={6} />
        </Card>
      }
    >
      <StockBalances />
    </Suspense>
  );
}
