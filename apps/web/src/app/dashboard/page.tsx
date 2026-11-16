"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Boxes,
  ChefHat,
  ClipboardList,
  Clock3,
  Coins,
  Package,
  Receipt,
  Recycle,
  RefreshCw,
  Users,
} from "lucide-react";

import { api } from "@/lib/api/client";
import { useAuthorization } from "@/components/layout/AuthorizationContext";

type TrendPoint = {
  date: string;
  count?: number;
  estimated_cost?: number;
};

type Purchase = {
  id: number;
  invoice_number?: string | null;
  purchase_date: string;
  grand_total: number | string;
  status: string;
};

type ReceiptRecord = {
  id: number;
  purchase_id: number;
  receipt_date: string;
  status: string;
};

type StockMovement = {
  id: number;
  item_name: string;
  movement_type: string;
  quantity: number | string;
  unit: string;
  created_at: string;
};

type MenuRecord = {
  id: number;
  name: string;
  meal_session: string;
};

type WasteRecord = {
  id: number;
  waste_date: string;
  notes?: string | null;
};

type ActivityRecord = {
  id: number;
  user_name: string;
  action: string;
  entity_type: string;
  entity_id?: number | null;
  details?: Record<string, unknown> | null;
  created_at: string;
};

type DashboardData = {
  campus_id: number;
  role: string;
  generated_at: string;
  permissions: string[];
  kpis: Record<string, number | string | null>;
  headcount?: {
    today: number | null;
    trend: TrendPoint[];
  };
  inventory?: {
    active_items: number;
    active_suppliers: number;
    recent_movements: StockMovement[];
  };
  purchases?: {
    count_this_month: number;
    total_this_month: number | string;
    recent: Purchase[];
  };
  receipts?: {
    count_this_month: number;
    recent: ReceiptRecord[];
  };
  menus?: {
    active_count: number;
    recent: MenuRecord[];
  };
  waste?: {
    records_today: number;
    quantity_today: number | string;
    estimated_cost_today: number | string;
    cost_trend: TrendPoint[];
    recent: WasteRecord[];
  };
  activity?: ActivityRecord[];
};

const moneyFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const numberFormatter = new Intl.NumberFormat("en-IN");

function toNumber(value: unknown): number {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number : 0;
}

function formatMoney(value: unknown): string {
  return moneyFormatter.format(toNumber(value));
}

function formatCompactMoney(value: unknown): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(toNumber(value));
}

function formatNumber(value: unknown): string {
  return numberFormatter.format(toNumber(value));
}

function formatDate(value?: string | null): string {
  if (!value) return "—";

  const parts = value.split("-").map(Number);

  if (parts.length === 3 && parts.every(Number.isFinite)) {
    const [year, month, day] = parts;
    return new Date(year, month - 1, day).toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  }

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
}

function formatDateTime(value?: string | null): string {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "—";

  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function readable(value?: string | null): string {
  if (!value) return "—";

  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function canRead(
  permissions: string[],
  code: string,
  role: string,
): boolean {
  return role === "ADMIN" || permissions.includes(code);
}

function StatusBadge({ value }: { value: string }) {
  const status = value.toUpperCase();

  let style = "bg-slate-100 text-slate-600";

  if (
    ["COMPLETED", "ACCEPTED", "ACTIVE", "APPROVED", "RECEIVED"].includes(
      status,
    )
  ) {
    style = "bg-blue-50 text-blue-700";
  } else if (
    ["PENDING", "DRAFT", "PARTIAL", "PROCESSING"].includes(status)
  ) {
    style = "bg-amber-50 text-amber-700";
  } else if (
    ["REJECTED", "CANCELLED", "FAILED"].includes(status)
  ) {
    style = "bg-red-50 text-red-700";
  }

  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${style}`}
    >
      {readable(value)}
    </span>
  );
}

function Panel({
  title,
  subtitle,
  icon: Icon,
  children,
  action,
}: {
  title: string;
  subtitle?: string;
  icon: React.ElementType;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="min-w-0 rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="rounded-lg bg-blue-50 p-2 text-blue-700">
            <Icon size={18} />
          </div>

          <div className="min-w-0">
            <h2 className="truncate text-sm font-bold text-slate-900">
              {title}
            </h2>

            {subtitle && (
              <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
            )}
          </div>
        </div>

        {action}
      </div>

      <div className="p-5">{children}</div>
    </section>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-400">
      {message}
    </div>
  );
}

function StatCard({
  title,
  value,
  description,
  icon: Icon,
}: {
  title: string;
  value: string;
  description: string;
  icon: React.ElementType;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-blue-200 hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-slate-500">{title}</p>
          <p className="mt-3 break-words text-2xl font-bold tracking-tight text-slate-900">
            {value}
          </p>
          <p className="mt-2 text-xs text-slate-400">{description}</p>
        </div>

        <div className="shrink-0 rounded-xl bg-blue-50 p-3 text-blue-700">
          <Icon size={21} />
        </div>
      </div>
    </div>
  );
}

function TrendChart({
  points,
  valueKey,
  valueFormatter,
}: {
  points: TrendPoint[];
  valueKey: "count" | "estimated_cost";
  valueFormatter: (value: unknown) => string;
}) {
  if (!points.length) {
    return <EmptyState message="No trend data available yet." />;
  }

  const values = points.map((point) => toNumber(point[valueKey]));
  const maximum = Math.max(...values, 1);

  return (
    <div className="pt-2">
      <div className="flex h-44 items-end gap-2">
        {points.map((point, index) => {
          const value = toNumber(point[valueKey]);
          const height = Math.max(5, (value / maximum) * 100);

          return (
            <div
              key={`${point.date}-${index}`}
              className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-2"
            >
              <span className="max-w-full truncate text-[10px] font-medium text-slate-500">
                {valueFormatter(value)}
              </span>

              <div className="flex h-full w-full items-end overflow-hidden rounded-t-md bg-slate-50">
                <div
                  className="w-full rounded-t-md bg-blue-600 transition-all duration-300"
                  style={{ height: `${height}%` }}
                  title={`${formatDate(point.date)}: ${valueFormatter(value)}`}
                />
              </div>

              <span className="text-[10px] text-slate-400">
                {new Date(`${point.date}T00:00:00`).toLocaleDateString(
                  "en-IN",
                  { day: "2-digit", month: "short" },
                )}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { role, permissions, loading: authLoading, error: authError } =
    useAuthorization();

  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const normalizedRole = role.toUpperCase();
  const isAdmin = normalizedRole === "ADMIN";

  const hasDashboardAccess =
    isAdmin || permissions.includes("dashboard.read");

  // Fetches the dashboard and stores the result. State is updated only in
  // the promise callbacks, so this is safe to call from an effect.
  function fetchDashboard() {
    return api
      .get<DashboardData>("/api/dashboard/overview")
      .then((response) => {
        setData(response);
        setError("");
      })
      .catch((err: unknown) => {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load dashboard data.",
        );
      })
      .finally(() => {
        setLoading(false);
      });
  }

  // Used by the "Try again" and "Refresh data" buttons.
  function loadDashboard() {
    setLoading(true);
    setError("");
    return fetchDashboard();
  }

  useEffect(() => {
    if (authLoading || !hasDashboardAccess) return;

    void fetchDashboard();

    // Refresh when the authenticated role or permission list changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, hasDashboardAccess, role, permissions.join(",")]);

  // Without dashboard access no request is made, so do not wait for one;
  // the access message below is shown instead.
  if (authLoading || (hasDashboardAccess && loading)) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <RefreshCw className="animate-spin text-blue-600" size={18} />
          Loading kitchen operations...
        </div>
      </div>
    );
  }

  if (authError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
        Unable to load your permissions: {authError}
      </div>
    );
  }

  if (!hasDashboardAccess) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-10 text-center">
        <ChefHat className="mx-auto mb-3 text-slate-400" size={32} />
        <h2 className="font-semibold text-slate-900">
          Dashboard access not assigned
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          Please contact your Admin to request dashboard access.
        </p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5">
        <p className="text-sm text-red-700">
          {error || "Dashboard data is unavailable."}
        </p>

        <button
          onClick={() => void loadDashboard()}
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800"
        >
          <RefreshCw size={15} />
          Try again
        </button>
      </div>
    );
  }

  const dashboardPermissions = data.permissions ?? permissions;
  const dashboardRole = data.role || normalizedRole;

  const showHeadcount = canRead(
    dashboardPermissions,
    "headcount.read",
    dashboardRole,
  );
  const showInventory = canRead(
    dashboardPermissions,
    "inventory.read",
    dashboardRole,
  );
  const showPurchases = canRead(
    dashboardPermissions,
    "purchase_order.read",
    dashboardRole,
  );
  const showMenus = canRead(
    dashboardPermissions,
    "menu.read",
    dashboardRole,
  );
  const showWaste = canRead(
    dashboardPermissions,
    "waste_tracking.read",
    dashboardRole,
  );
  const showAudit = canRead(
    dashboardPermissions,
    "audit.read",
    dashboardRole,
  );

  const statCards = [
    ...(showHeadcount
      ? [
          {
            title: "Today's Headcount",
            value:
              data.headcount?.today == null
                ? "—"
                : formatNumber(data.headcount.today),
            description: "Student count recorded today",
            icon: Users,
          },
        ]
      : []),
    ...(showInventory
      ? [
          {
            title: "Active Inventory Items",
            value: formatNumber(data.inventory?.active_items),
            description: `${formatNumber(data.inventory?.active_suppliers)} active suppliers`,
            icon: Package,
          },
        ]
      : []),
    ...(showPurchases
      ? [
          {
            title: "Purchases This Month",
            value: formatNumber(data.purchases?.count_this_month),
            description: formatMoney(data.purchases?.total_this_month),
            icon: Receipt,
          },
        ]
      : []),
    ...(showWaste
      ? [
          {
            title: "Today's Waste Cost",
            value: formatMoney(data.waste?.estimated_cost_today),
            description: `${formatNumber(data.waste?.records_today)} waste records today`,
            icon: Recycle,
          },
        ]
      : []),
  ];

  const quickActions = [
    ...(showInventory
      ? [
          {
            label: "Inventory",
            href: "/dashboard/items",
            icon: Boxes,
          },
        ]
      : []),
    ...(showMenus
      ? [
          {
            label: "Menus",
            href: "/dashboard/menus",
            icon: BookOpen,
          },
        ]
      : []),
    ...(showWaste
      ? [
          {
            label: "Waste Tracking",
            href: "/dashboard/waste-tracking",
            icon: Recycle,
          },
        ]
      : []),
  ];

  return (
    <div className="space-y-6 pb-8">
      {/* Page heading */}
      <section className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-700">
            Kitchen Operations
          </p>

          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            Dashboard
          </h1>

          <p className="mt-2 text-sm text-slate-500">
            Your kitchen operations at a glance.
          </p>

          <p className="mt-2 text-xs font-medium text-slate-400">
            {readable(dashboardRole)} · Campus #{data.campus_id}
          </p>
        </div>

        <button
          onClick={() => void loadDashboard()}
          className="inline-flex w-fit items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-blue-300 hover:text-blue-700"
        >
          <RefreshCw size={15} />
          Refresh data
        </button>
      </section>

      {/* KPI cards */}
      {statCards.length > 0 ? (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {statCards.map((card) => (
            <StatCard key={card.title} {...card} />
          ))}
        </section>
      ) : (
        <EmptyState message="No operational modules have been assigned to your account yet." />
      )}

      {/* Quick actions */}
      {quickActions.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-900">
              Quick access
            </h2>
            <span className="text-xs text-slate-400">
              Your available modules
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {quickActions.map(({ label, href, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className="group flex items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-blue-300 hover:shadow-md"
              >
                <span className="flex min-w-0 items-center gap-3">
                  <span className="rounded-lg bg-blue-50 p-2 text-blue-700">
                    <Icon size={18} />
                  </span>
                  <span className="truncate text-sm font-semibold text-slate-700">
                    {label}
                  </span>
                </span>
                <ArrowUpRight
                  size={16}
                  className="shrink-0 text-slate-400 group-hover:text-blue-700"
                />
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Trends */}
      {(showHeadcount || showWaste) && (
        <section className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          {showHeadcount && (
            <Panel
              title="Headcount trend"
              subtitle="Daily student count · Last 7 days"
              icon={Users}
            >
              <TrendChart
                points={data.headcount?.trend ?? []}
                valueKey="count"
                valueFormatter={(value) => formatNumber(value)}
              />
            </Panel>
          )}

          {showWaste && (
            <Panel
              title="Waste cost trend"
              subtitle="Estimated waste cost · Last 7 days"
              icon={Recycle}
            >
              <TrendChart
                points={data.waste?.cost_trend ?? []}
                valueKey="estimated_cost"
                valueFormatter={(value) => formatCompactMoney(value)}
              />
            </Panel>
          )}
        </section>
      )}

      {/* Purchases and receipts */}
      {(showPurchases || showInventory) && (
        <section className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          {showPurchases && (
            <Panel
              title="Recent purchases"
              subtitle={`${formatNumber(data.purchases?.count_this_month)} purchases this month · ${formatMoney(data.purchases?.total_this_month)}`}
              icon={Receipt}
            >
              {data.purchases?.recent.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[420px] text-left text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-xs text-slate-400">
                        <th className="pb-3 font-medium">Invoice</th>
                        <th className="pb-3 font-medium">Date</th>
                        <th className="pb-3 text-right font-medium">Amount</th>
                        <th className="pb-3 text-right font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.purchases.recent.map((purchase) => (
                        <tr
                          key={purchase.id}
                          className="border-b border-slate-50 last:border-0"
                        >
                          <td className="py-3 font-semibold text-slate-700">
                            {purchase.invoice_number || `#${purchase.id}`}
                          </td>
                          <td className="py-3 text-xs text-slate-500">
                            {formatDate(purchase.purchase_date)}
                          </td>
                          <td className="py-3 text-right font-medium text-slate-700">
                            {formatMoney(purchase.grand_total)}
                          </td>
                          <td className="py-3 text-right">
                            <StatusBadge value={purchase.status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState message="No purchases recorded yet." />
              )}
            </Panel>
          )}

          {showInventory && (
            <Panel
              title="Goods receipts"
              subtitle={`${formatNumber(data.receipts?.count_this_month)} receipts this month`}
              icon={ClipboardList}
            >
              {data.receipts?.recent.length ? (
                <div className="space-y-3">
                  {data.receipts.recent.map((receipt) => (
                    <div
                      key={receipt.id}
                      className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 p-3"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="rounded-lg bg-slate-50 p-2 text-slate-500">
                          <Receipt size={17} />
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-slate-800">
                            Receipt #{receipt.id}
                          </p>
                          <p className="mt-1 text-xs text-slate-400">
                            Purchase #{receipt.purchase_id} · {formatDate(receipt.receipt_date)}
                          </p>
                        </div>
                      </div>
                      <StatusBadge value={receipt.status} />
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState message="No goods receipts recorded yet." />
              )}
            </Panel>
          )}
        </section>
      )}

      {/* Inventory movements and menus */}
      {(showInventory || showMenus) && (
        <section className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          {showInventory && (
            <Panel
              title="Recent inventory movements"
              subtitle="Latest recorded stock movements"
              icon={Boxes}
            >
              {data.inventory?.recent_movements.length ? (
                <div className="space-y-3">
                  {data.inventory.recent_movements.map((movement) => (
                    <div
                      key={movement.id}
                      className="flex items-center justify-between gap-3 border-b border-slate-100 pb-3 last:border-0 last:pb-0"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="rounded-lg bg-blue-50 p-2 text-blue-700">
                          <Package size={17} />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-800">
                            {movement.item_name}
                          </p>
                          <p className="mt-1 text-xs text-slate-400">
                            {readable(movement.movement_type)} · {formatDateTime(movement.created_at)}
                          </p>
                        </div>
                      </div>

                      <span className="shrink-0 text-sm font-bold text-slate-700">
                        {formatNumber(movement.quantity)} {movement.unit}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState message="No inventory movements recorded yet." />
              )}
            </Panel>
          )}

          {showMenus && (
            <Panel
              title="Active menus"
              subtitle={`${formatNumber(data.menus?.active_count)} active menus`}
              icon={BookOpen}
            >
              {data.menus?.recent.length ? (
                <div className="space-y-3">
                  {data.menus.recent.map((menu) => (
                    <div
                      key={menu.id}
                      className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 p-3"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="rounded-lg bg-blue-50 p-2 text-blue-700">
                          <ChefHat size={17} />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-800">
                            {menu.name}
                          </p>
                          <p className="mt-1 text-xs text-slate-400">
                            {menu.meal_session}
                          </p>
                        </div>
                      </div>
                      <span className="rounded-full bg-blue-50 px-2.5 py-1 text-[11px] font-semibold text-blue-700">
                        Active
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState message="No active menus found." />
              )}
            </Panel>
          )}
        </section>
      )}

      {/* Waste overview */}
      {showWaste && (
        <section className="grid grid-cols-1 gap-5 xl:grid-cols-3">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-blue-50 p-2 text-blue-700">
                <Recycle size={19} />
              </div>
              <p className="text-sm font-semibold text-slate-700">
                Waste recorded today
              </p>
            </div>

            <p className="mt-4 text-2xl font-bold text-slate-900">
              {formatNumber(data.waste?.records_today)}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Waste records
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-blue-50 p-2 text-blue-700">
                <Boxes size={19} />
              </div>
              <p className="text-sm font-semibold text-slate-700">
                Waste quantity today
              </p>
            </div>

            <p className="mt-4 text-2xl font-bold text-slate-900">
              {formatNumber(data.waste?.quantity_today)}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Combined quantity across recorded units
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-blue-50 p-2 text-blue-700">
                <Coins size={19} />
              </div>
              <p className="text-sm font-semibold text-slate-700">
                Estimated cost today
              </p>
            </div>

            <p className="mt-4 text-2xl font-bold text-slate-900">
              {formatMoney(data.waste?.estimated_cost_today)}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Based on recorded waste estimates
            </p>
          </div>
        </section>
      )}

      {/* Recent waste records */}
      {showWaste && (
        <Panel
          title="Recent waste records"
          subtitle="Latest recorded waste entries"
          icon={Recycle}
        >
          {data.waste?.recent.length ? (
            <div className="space-y-3">
              {data.waste.recent.map((record) => (
                <div
                  key={record.id}
                  className="flex items-center justify-between gap-3 border-b border-slate-100 pb-3 last:border-0 last:pb-0"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800">
                      Waste record #{record.id}
                    </p>
                    <p className="mt-1 truncate text-xs text-slate-400">
                      {record.notes || "No notes added"}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-slate-500">
                    {formatDate(record.waste_date)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState message="No waste records available yet." />
          )}
        </Panel>
      )}

      {/* Audit activity */}
      {showAudit && (
        <Panel
          title="Recent system activity"
          subtitle="Latest audit log entries"
          icon={Activity}
        >
          {data.activity?.length ? (
            <div className="space-y-4">
              {data.activity.map((activity) => (
                <div
                  key={activity.id}
                  className="flex gap-3"
                >
                  <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-600">
                    <Activity size={16} />
                  </div>

                  <div className="min-w-0 flex-1 border-b border-slate-100 pb-4 last:border-0 last:pb-0">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-slate-800">
                        {activity.user_name}
                      </p>
                      <span className="text-[11px] text-slate-400">
                        {formatDateTime(activity.created_at)}
                      </span>
                    </div>

                    <p className="mt-1 text-sm text-slate-600">
                      {readable(activity.action)}{" "}
                      <span className="font-medium text-slate-800">
                        {readable(activity.entity_type)}
                      </span>
                      {activity.entity_id != null &&
                        ` #${activity.entity_id}`}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState message="No recent audit activity available." />
          )}
        </Panel>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-4 text-xs text-slate-400">
        <span className="flex items-center gap-2">
          <Clock3 size={13} />
          Data generated: {formatDateTime(data.generated_at)}
        </span>
        <span>Campus-scoped dashboard</span>
      </div>
    </div>
  );
}
