"use client";

import { useEffect, useState } from "react";
import type { ElementType, ReactNode } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CalendarRange,
  ChartColumn,
  ClipboardCheck,
  CookingPot,
  FileText,
  LayoutDashboard,
  PackageCheck,
  RefreshCw,
  Soup,
  Users,
  UtensilsCrossed,
  Wallet,
  Warehouse,
} from "lucide-react";

import { api } from "@/lib/api/client";
import { DASHBOARD_OVERVIEW_ENDPOINT } from "@/lib/api/endpoints";
import { canAccessPath } from "@/lib/auth/permissions";
import { percentText, type DashboardOverview } from "@/lib/dashboard";
import { errorMessage, formatDateTime, formatDay, formatRupees } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import AreaChart from "@/components/charts/AreaChart";
import BarList from "@/components/charts/BarList";
import { SERIES } from "@/components/charts/tokens";
import Badge, { StatusBadge, humanize } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import PageHeader from "@/components/ui/PageHeader";
import StatCard from "@/components/ui/StatCard";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";

const SHORTCUTS: { label: string; href: string; icon: ElementType }[] = [
  { label: "Record a meal", href: "/dashboard/meals/new", icon: UtensilsCrossed },
  { label: "New kitchen issue", href: "/dashboard/kitchen-issues/new", icon: CookingPot },
  { label: "Record stock count", href: "/dashboard/stock-counts/new", icon: ClipboardCheck },
  { label: "Stock balances", href: "/dashboard/stock", icon: Warehouse },
  { label: "New meal plan", href: "/dashboard/meal-plans/new", icon: CalendarRange },
  { label: "Outsourced food", href: "/dashboard/outsourced-food", icon: Soup },
  { label: "New supplier bill", href: "/dashboard/supplier-bills/new", icon: FileText },
  { label: "Goods receipt", href: "/dashboard/receipts/new", icon: PackageCheck },
  { label: "Spending analysis", href: "/dashboard/analytics", icon: ChartColumn },
  { label: "Reports", href: "/dashboard/reports", icon: BarChart3 },
];

function Panel({ title, subtitle, icon, href, linkLabel, children }: {
  title: string; subtitle?: string; icon: ElementType; href?: string; linkLabel?: string; children: ReactNode;
}) {
  return (
    <Card className="flex min-w-0 flex-col">
      <CardHeader title={title} subtitle={subtitle} icon={icon}
        action={href ? (
          <Link href={href} className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
            {linkLabel ?? "Open"} <ArrowRight size={14} aria-hidden />
          </Link>
        ) : undefined} />
      <div className="flex-1 px-5 pb-5">{children}</div>
    </Card>
  );
}

function Row({ children, href }: { children: ReactNode; href?: string }) {
  const body = <div className="flex items-center justify-between gap-3 py-2 text-sm">{children}</div>;
  return (
    <li className="border-b border-slate-100 last:border-0">
      {href ? <Link href={href} className="block rounded hover:bg-slate-50">{body}</Link> : body}
    </li>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="py-3 text-sm text-slate-500">{children}</p>;
}

export default function DashboardPage() {
  const { role, permissions } = useAuthorization();
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [loadedKey, setLoadedKey] = useState(-1);
  const loading = loadedKey !== reloadKey;
  const load = () => setReloadKey((key) => key + 1);

  // Without the dashboard code the overview is refused (403): show the
  // welcome state and the user's shortcuts instead of an error.
  const canReadDashboard = role === "ADMIN" || role === "KITCHEN_MANAGER" || permissions.includes("dashboard.read");

  useEffect(() => {
    if (!canReadDashboard) return;
    let active = true;
    api.get<DashboardOverview>(DASHBOARD_OVERVIEW_ENDPOINT)
      .then((response) => { if (active) { setData(response); setError(""); } })
      .catch((err: unknown) => active && setError(errorMessage(err, "Unable to load the dashboard.")))
      .finally(() => active && setLoadedKey(reloadKey));
    return () => { active = false; };
  }, [reloadKey, canReadDashboard]);

  const header = (
    <PageHeader eyebrow="Overview" icon={LayoutDashboard} title="Dashboard"
      description="Today's meals, stock, planning, outsourced food and spending for your campus."
      meta={data ? (
        <span className="flex flex-wrap gap-2">
          <Badge tone="brand">{humanize(data.role)}</Badge>
          {data.campus_name && <Badge>{data.campus_name}</Badge>}
        </span>
      ) : undefined}
      actions={<Button variant="secondary" icon={<RefreshCw size={15} aria-hidden />} loading={loading} onClick={load}>Refresh</Button>} />
  );

  if (!canReadDashboard && role) {
    const mine = SHORTCUTS.filter((s) => canAccessPath(role, s.href, permissions));
    return (
      <div className="space-y-6 pb-6">
        <PageHeader eyebrow="Overview" icon={LayoutDashboard} title="Welcome to Kitchen Copilot"
          description="Your account has no dashboard figures assigned. Use the menu or the shortcuts below." />
        <Card data-dashboard-welcome>
          {mine.length === 0 ? (
            <EmptyState icon={LayoutDashboard} title="Nothing to show yet"
              description="Your account has no modules assigned yet. An Admin can assign the modules you work with." />
          ) : (
            <ul className="grid grid-cols-2 gap-2 p-5 sm:grid-cols-3 lg:grid-cols-5">
              {mine.map((s) => (
                <li key={s.href}>
                  <Link href={s.href} className="flex h-full items-center gap-2 rounded-lg border border-slate-200 px-3 py-2.5 text-sm font-medium text-slate-700 hover:border-brand-200 hover:bg-brand-50">
                    <s.icon size={16} className="shrink-0 text-brand-600" aria-hidden /><span className="min-w-0">{s.label}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    );
  }

  if (error && !data) return <div className="space-y-6 pb-6">{header}<Card><ErrorState title="Couldn't load the dashboard" message={error} onRetry={load} /></Card></div>;
  if (!data) return (
    <div className="space-y-6 pb-6">{header}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}</div>
    </div>
  );

  const { headcount, stock, meals, planning, outsourced, spending, payments, kitchen, counts } = data;
  const shortcuts = SHORTCUTS.filter((s) => canAccessPath(role, s.href, permissions));
  const attention: { label: string; href: string; count: number }[] = [
    { label: "Meal records from earlier days still open", href: "/dashboard/meals", count: meals?.awaiting_close_count ?? 0 },
    { label: "Stock adjustments waiting for approval", href: "/dashboard/stock-adjustments", count: counts?.pending_adjustments ?? 0 },
    { label: "Draft kitchen issues to confirm", href: "/dashboard/kitchen-issues", count: kitchen?.draft_issues ?? 0 },
    { label: "Draft outsourced deliveries to confirm", href: "/dashboard/outsourced-food", count: outsourced?.draft_deliveries ?? 0 },
    { label: "Outsourced food waiting for its meal record", href: "/dashboard/outsourced-food", count: outsourced?.waiting_for_meal_record ?? 0 },
    { label: "Draft meal plans", href: "/dashboard/meal-plans", count: planning?.draft_plans ?? 0 },
    { label: "Draft portion standards to approve", href: "/dashboard/portion-standards", count: planning?.draft_standards ?? 0 },
  ].filter((a) => a.count > 0 && canAccessPath(role, a.href, permissions));
  const noSections = !headcount && !stock && !meals && !planning && !outsourced && !spending && !payments;

  return (
    <div className="space-y-6 pb-6" data-dashboard>
      {header}
      {error && <p className="text-sm text-red-700">{error}</p>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {headcount && (
          <StatCard label="Today's headcount" icon={Users} accent={SERIES.blue}
            value={headcount.today === null ? "—" : headcount.today.toLocaleString("en-IN")}
            description={headcount.today === null ? "No meal recorded today"
              : headcount.today_basis === "actual" ? "People served at the largest meal" : "Expected at the largest meal"}
            trend={headcount.trend.map((t) => t.count ?? 0)} />
        )}
        {stock && (
          <StatCard label="Below minimum stock" icon={Warehouse} accent={SERIES.orange}
            value={String(stock.below_minimum)} description={`${stock.out_of_stock} of ${stock.items_tracked} items at zero`} />
        )}
        {spending && (
          <StatCard label="Purchases this month" icon={Wallet} value={formatRupees(spending.current)}
            description={`${percentText(spending.change_percent)} vs ${formatDay(spending.periods.previous.date_from)} – ${formatDay(spending.periods.previous.date_to)}`} />
        )}
        {payments && (
          <StatCard label="Outstanding payables" icon={FileText} value={formatRupees(payments.outstanding)}
            description={`${payments.open_bill_count} open bills · ${payments.suppliers_owed} suppliers`} />
        )}
        {!spending && meals && (
          <StatCard label="Open meal records" icon={UtensilsCrossed} value={String(meals.open_count)}
            description={`${meals.awaiting_close_count} from earlier days`} />
        )}
        {!payments && outsourced && (
          <StatCard label="Outsourced orders (±2 days)" icon={Soup} value={String(outsourced.orders.length)}
            description={`${outsourced.draft_deliveries} deliveries to confirm`} />
        )}
      </div>

      {attention.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/50" data-attention>
          <CardHeader title="Needs attention" icon={AlertTriangle} />
          <ul className="grid grid-cols-1 gap-2 px-5 pb-5 sm:grid-cols-2">
            {attention.map((a) => (
              <li key={a.label}>
                <Link href={a.href} className="flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm hover:bg-amber-50">
                  <span>{a.label}</span><Badge tone="warning">{a.count}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {noSections && (
        <Card><EmptyState icon={LayoutDashboard} title="Nothing to show yet"
          description="Your account has no dashboard sections yet. An Admin can assign the modules you work with." /></Card>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {(headcount || meals) && (
          <Panel title="Today's meals" subtitle="Expected and actual people per meal, from the meal records" icon={UtensilsCrossed}
            href={canAccessPath(role, "/dashboard/meals", permissions) ? "/dashboard/meals" : undefined} linkLabel="Meals">
            {headcount && headcount.sessions.length > 0 ? (
              <ul data-today-meals>
                {headcount.sessions.map((s) => (
                  <Row key={s.meal_record_id} href={`/dashboard/meals/${s.meal_record_id}`}>
                    <span className="font-medium text-slate-900">{s.meal_session_name}</span>
                    <span className="flex items-center gap-3 text-slate-600">
                      <span>{s.expected ?? "—"} expected · {s.actual ?? "—"} served</span><StatusBadge status={s.status} />
                    </span>
                  </Row>
                ))}
              </ul>
            ) : <Empty>No meal recorded for today yet.</Empty>}
            {headcount && headcount.tomorrow.length > 0 && (
              <p className="mt-2 text-xs text-slate-500">
                Tomorrow: {headcount.tomorrow.map((t) => `${t.meal_session_name} ${t.expected ?? "—"}`).join(" · ")} expected
              </p>
            )}
            {headcount && headcount.trend.length > 1 && (
              <div className="mt-4">
                <AreaChart points={headcount.trend.map((t) => ({ date: t.date, value: t.count ?? 0 }))} color={SERIES.blue}
                  seriesLabel="Headcount (largest meal)" formatValue={(v) => v.toLocaleString("en-IN")} />
              </div>
            )}
          </Panel>
        )}

        {stock && (
          <Panel title="Stock alerts" subtitle="Items furthest below their minimum stock" icon={Warehouse}
            href="/dashboard/stock" linkLabel="Stock balances">
            {stock.lowest.length === 0 ? <Empty>Every item is at or above its minimum stock.</Empty> : (
              <ul data-stock-alerts>
                {stock.lowest.map((s) => (
                  <Row key={s.item_id} href={`/dashboard/stock/${s.item_id}`}>
                    <span className="font-medium text-slate-900">{s.item_name}</span>
                    <span className="text-right text-slate-600">
                      {plainQuantity(s.balance)} of {plainQuantity(s.minimum)} {s.unit}
                      <span className="block text-xs text-amber-700">needs {plainQuantity(s.needed)} {s.unit}</span>
                    </span>
                  </Row>
                ))}
              </ul>
            )}
          </Panel>
        )}

        {spending && (
          <Panel title="Purchase spending" icon={Wallet} href="/dashboard/analytics" linkLabel="Spending analysis"
            subtitle={`${formatDay(spending.periods.current.date_from)} – ${formatDay(spending.periods.current.date_to)} against the same days last month`}>
            <dl className="grid grid-cols-3 gap-3 text-sm">
              <div><dt className="text-xs text-slate-500">This period</dt><dd className="font-semibold">{formatRupees(spending.current)}</dd></div>
              <div><dt className="text-xs text-slate-500">Same days last month</dt><dd className="font-semibold">{formatRupees(spending.previous)}</dd></div>
              <div><dt className="text-xs text-slate-500">Change</dt><dd className="font-semibold">{percentText(spending.change_percent)}</dd></div>
            </dl>
            {spending.top_categories.length > 0 ? (
              <div className="mt-4">
                <BarList color={SERIES.blue} measureLabel="Spending by category this month" rows={spending.top_categories.map((c) => ({
                  id: c.category_id, label: c.category_name ?? "—", value: Number(c.value), display: formatRupees(c.value) }))} />
              </div>
            ) : <Empty>No supplier bills this month yet.</Empty>}
          </Panel>
        )}

        {payments && (
          <Panel title="Payables" subtitle="What is owed to suppliers today" icon={FileText}
            href="/dashboard/supplier-balances" linkLabel="Supplier balances">
            {payments.top_outstanding.length === 0 ? <Empty>Nothing is owed to suppliers.</Empty> : (
              <ul>
                {payments.top_outstanding.map((s) => (
                  <Row key={s.supplier_id}>
                    <span className="font-medium text-slate-900">{s.supplier_name}</span>
                    <span className="text-slate-600">{formatRupees(s.outstanding)} · {s.open_bill_count} bills</span>
                  </Row>
                ))}
              </ul>
            )}
            <p className="mt-2 text-xs text-slate-500">Paid this month: {formatRupees(payments.paid_this_month)}</p>
          </Panel>
        )}

        {planning && (
          <Panel title="Meal planning" subtitle="Plans for the next seven days" icon={CalendarRange} href="/dashboard/meal-plans" linkLabel="Meal plans">
            {planning.upcoming.length === 0 ? <Empty>No meal plan for the next seven days.</Empty> : (
              <ul>
                {planning.upcoming.map((p) => (
                  <Row key={p.id} href={`/dashboard/meal-plans/${p.id}`}>
                    <span className="font-medium text-slate-900">{p.meal_session_name} · {formatDay(p.plan_date)}</span>
                    <span className="flex items-center gap-2 text-slate-600">{p.expected_headcount} people <StatusBadge status={p.status} /></span>
                  </Row>
                ))}
              </ul>
            )}
            <p className="mt-2 text-xs text-slate-500">{planning.approved_standards} approved portion standards · {planning.draft_standards} drafts</p>
          </Panel>
        )}

        {outsourced && (
          <Panel title="Outsourced food" subtitle="Orders from yesterday to the day after tomorrow" icon={Soup}
            href="/dashboard/outsourced-food" linkLabel="Outsourced food">
            {outsourced.orders.length === 0 ? <Empty>No outsourced order around today.</Empty> : (
              <ul>
                {outsourced.orders.map((o) => (
                  <Row key={o.id} href={`/dashboard/outsourced-food/${o.id}`}>
                    <span className="min-w-0"><span className="font-medium text-slate-900">{o.order_number}</span>
                      <span className="block text-xs text-slate-500">{o.meal_session_name} · {formatDay(o.meal_date)} · {o.supplier_name}</span></span>
                    {o.receiving_status && <Badge tone={o.receiving_status === "RECEIVED" ? "success" : "warning"}>{humanize(o.receiving_status)}</Badge>}
                  </Row>
                ))}
              </ul>
            )}
            {outsourced.planned_cost_this_month !== undefined && (
              <p className="mt-2 text-xs text-slate-500">Planned cost of this month&rsquo;s ordered meals: {formatRupees(outsourced.planned_cost_this_month)}</p>
            )}
          </Panel>
        )}
      </div>

      {shortcuts.length > 0 && (
        <Card>
          <CardHeader title="Shortcuts" icon={ArrowRight} />
          <ul className="grid grid-cols-2 gap-2 px-5 pb-5 sm:grid-cols-3 lg:grid-cols-5" data-shortcuts>
            {shortcuts.map((s) => (
              <li key={s.href}>
                <Link href={s.href} className="flex h-full items-center gap-2 rounded-lg border border-slate-200 px-3 py-2.5 text-sm font-medium text-slate-700 hover:border-brand-200 hover:bg-brand-50">
                  <s.icon size={16} className="shrink-0 text-brand-600" aria-hidden /><span className="min-w-0">{s.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {data.activity && (
          <Panel title="Recent activity" subtitle="Latest recorded actions on this campus" icon={RefreshCw}>
            {data.activity.length === 0 ? <Empty>No recorded activity yet.</Empty> : (
              <ul>
                {data.activity.slice(0, 8).map((a) => (
                  <Row key={a.id}>
                    <span className="min-w-0"><span className="font-medium text-slate-900">{a.user_name}</span>
                      <span className="block text-xs text-slate-500">{humanize(a.action)} {humanize(a.entity_type).toLowerCase()}{a.entity_id ? ` #${a.entity_id}` : ""}</span></span>
                    <span className="shrink-0 text-xs text-slate-500">{formatDateTime(a.created_at)}</span>
                  </Row>
                ))}
              </ul>
            )}
          </Panel>
        )}
        {data.team && (
          <Panel title="Team and access" icon={Users} href="/dashboard/staff" linkLabel="Staff management">
            <ul>
              <Row><span>Admins</span><span>{data.team.active_admins}</span></Row>
              <Row><span>Kitchen managers</span><span>{data.team.active_kitchen_managers}</span></Row>
              <Row><span>Staff</span><span>{data.team.active_staff}</span></Row>
              <Row><span>Staff with no access assigned</span><span>{data.team.staff_without_access}</span></Row>
              <Row><span>Inactive accounts</span><span>{data.team.inactive_users}</span></Row>
            </ul>
          </Panel>
        )}
      </div>
      <p className="text-xs text-slate-500">Data generated {formatDateTime(data.generated_at)} · campus-scoped</p>
    </div>
  );
}
