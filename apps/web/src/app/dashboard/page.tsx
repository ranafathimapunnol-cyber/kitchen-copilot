"use client";

import type { ElementType, ReactNode } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bot,
  CalendarRange,
  ChartColumn,
  ClipboardCheck,
  CookingPot,
  FileText,
  History,
  LayoutDashboard,
  PackageCheck,
  RefreshCw,
  Soup,
  Sparkles,
  Users,
  UtensilsCrossed,
  Wallet,
  Warehouse,
} from "lucide-react";

import { canAccessPath } from "@/lib/auth/permissions";
import { attentionItems, canReadDashboard, percentText } from "@/lib/dashboard";
import { errorMessage, formatDateTime, formatDay, formatRupees } from "@/lib/payments";
import { plainQuantity } from "@/lib/stockMath";
import { useOverview } from "@/lib/useOverview";
import { useAuthorization } from "@/components/layout/AuthorizationContext";
import { useCurrentUser } from "@/components/layout/CurrentUser";
import AreaChart from "@/components/charts/AreaChart";
import BarList from "@/components/charts/BarList";
import { SERIES } from "@/components/charts/tokens";
import Badge, { StatusBadge, humanize } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import StatCard from "@/components/ui/StatCard";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { cn } from "@/components/ui/cn";

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

function Panel({ title, subtitle, icon: Icon, href, linkLabel, children, className }: {
  title: string; subtitle?: string; icon: ElementType; href?: string; linkLabel?: string; children: ReactNode; className?: string;
}) {
  return (
    <Card className={cn("flex min-w-0 flex-col", className)}>
      <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
            <Icon size={16} aria-hidden />
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-[15px] font-semibold text-slate-900">{title}</h2>
            {subtitle && <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{subtitle}</p>}
          </div>
        </div>
        {href && (
          <Link href={href} aria-label={`${linkLabel ?? "Open"}: ${title}`} className="group mt-1 inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-[13px] font-medium text-brand-700 transition-colors hover:bg-brand-50">
            <span className="hidden sm:inline">{linkLabel ?? "Open"}</span> <ArrowRight size={14} aria-hidden className="transition-transform group-hover:translate-x-0.5" />
          </Link>
        )}
      </div>
      <div className="flex-1 px-5 pt-2 pb-5 sm:px-6">{children}</div>
    </Card>
  );
}

function Row({ children, href }: { children: ReactNode; href?: string }) {
  const body = <div className="flex items-center justify-between gap-3 px-2 py-2.5 text-sm">{children}</div>;
  return (
    <li className="border-b border-slate-100 last:border-0">
      {href ? <Link href={href} className="-mx-2 block rounded-lg transition-colors hover:bg-brand-50/50">{body}</Link> : body}
    </li>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="py-4 text-sm text-slate-500">{children}</p>;
}

function Shortcuts({ items }: { items: typeof SHORTCUTS }) {
  return (
    <ul className="grid grid-cols-1 gap-2.5 p-5 min-[420px]:grid-cols-2 sm:grid-cols-3 sm:p-6 lg:grid-cols-5" data-shortcuts>
      {items.map((s) => (
        <li key={s.href}>
          <Link href={s.href} className="group flex h-full items-center gap-3 rounded-xl border border-slate-200/80 bg-white px-3.5 py-3 text-sm font-medium text-slate-700 transition-[border-color,background-color,box-shadow] duration-200 hover:border-brand-200 hover:bg-brand-50/50 hover:shadow-xs">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sand/50 text-brand-700 transition-colors group-hover:bg-brand-100">
              <s.icon size={16} aria-hidden />
            </span>
            <span className="min-w-0">{s.label}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

export default function DashboardPage() {
  const { role, permissions } = useAuthorization();
  const user = useCurrentUser();
  const allowed = canReadDashboard(role, permissions);
  const { data, error: loadError, loading, reload } = useOverview(allowed);
  const error = loadError ? errorMessage(loadError, "Unable to load the dashboard.") : "";
  const firstName = user?.full_name?.trim().split(/\s+/)[0];
  const canCopilot = canAccessPath(role, "/dashboard/copilot", permissions);
  const today = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  const header = (
    <section className="relative overflow-hidden rounded-[1.4rem] border border-slate-200/70 bg-gradient-to-br from-white via-white to-brand-50 px-5 py-6 shadow-card sm:px-8 sm:py-7">
      <div aria-hidden className="pointer-events-none absolute -top-24 -right-16 h-64 w-64 rounded-full bg-sand/60 blur-3xl" />
      <div className="relative flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold tracking-[0.14em] text-brand-700 uppercase">{today}</p>
          <h1 className="font-display mt-2 text-[1.9rem] leading-tight font-medium text-slate-900 sm:text-[2.35rem]">
            {greeting()}{firstName ? `, ${firstName}` : ""}
          </h1>
          <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-slate-500">
            {allowed
              ? "Today's meals, stock, planning, outsourced food and spending for your campus."
              : "Your account has no dashboard figures assigned. Use the menu or the shortcuts below."}
          </p>
          {data && (
            <div className="mt-4 flex flex-wrap gap-2">
              <Badge tone="brand">{humanize(data.role)}</Badge>
              {data.campus_name && <Badge>{data.campus_name}</Badge>}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {allowed && (
            <Button variant="secondary" icon={<RefreshCw size={15} aria-hidden />} loading={loading} onClick={reload}>Refresh</Button>
          )}
          {canCopilot && (
            <Link href="/dashboard/copilot" className="inline-flex h-10 items-center gap-2 rounded-[10px] bg-slate-900 px-4 text-sm font-medium text-white shadow-sm transition-colors hover:bg-slate-800">
              <Sparkles size={15} aria-hidden className="text-brand-200" /> Ask Copilot
            </Link>
          )}
        </div>
      </div>
    </section>
  );

  if (!allowed && role) {
    const mine = SHORTCUTS.filter((s) => canAccessPath(role, s.href, permissions));
    return (
      <div className="space-y-6 pb-6">
        {header}
        <Card data-dashboard-welcome>
          <CardHeader title="Your shortcuts" icon={ArrowUpRight} iconTone="brand" />
          {mine.length === 0 ? (
            <EmptyState icon={LayoutDashboard} title="Nothing to show yet"
              description="Your account has no modules assigned yet. An Admin can assign the modules you work with." />
          ) : <Shortcuts items={mine} />}
        </Card>
      </div>
    );
  }

  if (error && !data) return <div className="space-y-6 pb-6">{header}<Card><ErrorState title="Couldn't load the dashboard" message={error} onRetry={reload} /></Card></div>;
  if (!data) return (
    <div className="space-y-6 pb-6">{header}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-36 rounded-2xl" />)}</div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3"><Skeleton className="h-80 rounded-2xl xl:col-span-2" /><Skeleton className="h-80 rounded-2xl" /></div>
    </div>
  );

  const { headcount, stock, meals, planning, outsourced, spending, payments } = data;
  const shortcuts = SHORTCUTS.filter((s) => canAccessPath(role, s.href, permissions));
  // Low stock has its own panel here; the list keeps the rest.
  const attention = attentionItems(data).filter((a) => a.href !== "/dashboard/stock" && canAccessPath(role, a.href, permissions));
  const noSections = !headcount && !stock && !meals && !planning && !outsourced && !spending && !payments;

  return (
    <div className="space-y-6 pb-6" data-dashboard>
      {header}
      {error && <p className="text-sm text-red-700">{error}</p>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {headcount && (
          <StatCard label="Today's headcount" icon={Users} accent={SERIES.coffee}
            value={headcount.today === null ? "—" : headcount.today.toLocaleString("en-IN")}
            description={headcount.today === null ? "No meal recorded today"
              : headcount.today_basis === "actual" ? "People served at the largest meal" : "Expected at the largest meal"}
            trend={headcount.trend.map((t) => t.count ?? 0)} />
        )}
        {stock && (
          <StatCard label="Below minimum stock" icon={Warehouse} accent={SERIES.dusk}
            value={String(stock.below_minimum)} description={`${stock.out_of_stock} of ${stock.items_tracked} items at zero`} />
        )}
        {spending && (
          <StatCard label="Purchases this month" icon={Wallet} accent={SERIES.coffee} value={formatRupees(spending.current)}
            description={`${percentText(spending.change_percent)} vs ${formatDay(spending.periods.previous.date_from)} – ${formatDay(spending.periods.previous.date_to)}`} />
        )}
        {payments && (
          <StatCard label="Outstanding payables" icon={FileText} accent={SERIES.dusk} value={formatRupees(payments.outstanding)}
            description={`${payments.open_bill_count} open bills · ${payments.suppliers_owed} suppliers`} />
        )}
        {!spending && meals && (
          <StatCard label="Open meal records" icon={UtensilsCrossed} value={String(meals.open_count)}
            description={`${meals.awaiting_close_count} from earlier days`} />
        )}
        {!payments && outsourced && (
          <StatCard label="Outsourced orders (±2 days)" icon={Soup} accent={SERIES.dusk} value={String(outsourced.orders.length)}
            description={`${outsourced.draft_deliveries} deliveries to confirm`} />
        )}
      </div>

      {attention.length > 0 && (
        <Card className="border-amber-200/80 bg-gradient-to-br from-amber-50/80 to-white" data-attention>
          <CardHeader title="Needs attention" subtitle="Work waiting for someone on this campus" icon={AlertTriangle} className="border-amber-100" />
          <ul className="grid grid-cols-1 gap-2.5 px-5 pt-1 pb-5 sm:grid-cols-2 sm:px-6 xl:grid-cols-3">
            {attention.map((a) => (
              <li key={a.label}>
                <Link href={a.href} className="group flex h-full items-center justify-between gap-3 rounded-xl border border-amber-200/70 bg-white px-3.5 py-2.5 text-sm text-slate-700 transition-colors hover:border-amber-300 hover:bg-amber-50/60">
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

      <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-3">
        {(headcount || meals) && (
          <Panel className={stock ? "xl:col-span-2" : "xl:col-span-3"} title="Today's meals" subtitle="Expected and actual people per meal, from the meal records" icon={UtensilsCrossed}
            href={canAccessPath(role, "/dashboard/meals", permissions) ? "/dashboard/meals" : undefined} linkLabel="Meals">
            {headcount && headcount.sessions.length > 0 ? (
              <ul data-today-meals>
                {headcount.sessions.map((s) => (
                  <Row key={s.meal_record_id} href={`/dashboard/meals/${s.meal_record_id}`}>
                    <span className="font-medium text-slate-900">{s.meal_session_name}</span>
                    <span className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 text-slate-600">
                      <span className="tabular-nums">{s.expected ?? "—"} expected · {s.actual ?? "—"} served</span><StatusBadge status={s.status} />
                    </span>
                  </Row>
                ))}
              </ul>
            ) : <Empty>No meal recorded for today yet.</Empty>}
            {headcount && headcount.tomorrow.length > 0 && (
              <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
                <span className="font-medium text-slate-700">Tomorrow:</span> {headcount.tomorrow.map((t) => `${t.meal_session_name} ${t.expected ?? "—"}`).join(" · ")} expected
              </p>
            )}
            {meals && (
              <p className="mt-3 text-xs text-slate-500">{meals.open_count} open meal records · {meals.awaiting_close_count} from earlier days · {meals.dishes_today} dishes recorded today</p>
            )}
            {headcount && headcount.trend.length > 1 && (
              <div className="mt-5">
                <AreaChart points={headcount.trend.map((t) => ({ date: t.date, value: t.count ?? 0 }))} color={SERIES.coffee}
                  seriesLabel="Headcount (largest meal)" formatValue={(v) => v.toLocaleString("en-IN")} />
              </div>
            )}
          </Panel>
        )}

        {stock && (
          <Panel className={headcount || meals ? "" : "xl:col-span-3"} title="Low-stock alerts" subtitle="Items furthest below their minimum" icon={Warehouse}
            href="/dashboard/stock" linkLabel="Stock">
            {stock.lowest.length === 0 ? <Empty>Every item is at or above its minimum stock.</Empty> : (
              <ul data-stock-alerts>
                {stock.lowest.map((s) => {
                  const minimum = Number(s.minimum);
                  const share = minimum > 0 ? Math.max(0, Math.min(1, Number(s.balance) / minimum)) : 0;
                  return (
                    <li key={s.item_id} className="border-b border-slate-100 last:border-0">
                      <Link href={`/dashboard/stock/${s.item_id}`} className="-mx-2 block rounded-lg px-2 py-2.5 transition-colors hover:bg-brand-50/50">
                        <span className="flex items-baseline justify-between gap-3 text-sm">
                          <span className="min-w-0 truncate font-medium text-slate-900">{s.item_name}</span>
                          <span className="shrink-0 text-xs text-slate-600 tabular-nums">{plainQuantity(s.balance)} / {plainQuantity(s.minimum)} {s.unit}</span>
                        </span>
                        <span aria-hidden className="mt-2 block h-1.5 overflow-hidden rounded-full bg-slate-100">
                          <span className={cn("block h-full rounded-full", share === 0 ? "bg-red-500" : "bg-amber-500")} style={{ width: `${Math.max(share * 100, 3)}%` }} />
                        </span>
                        <span className="mt-1 block text-xs text-amber-800">needs {plainQuantity(s.needed)} {s.unit}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>
        )}

        {spending && (
          <Panel className={payments ? "xl:col-span-2" : "xl:col-span-3"} title="Purchase spending" icon={Wallet} href="/dashboard/analytics" linkLabel="Analysis"
            subtitle={`${formatDay(spending.periods.current.date_from)} – ${formatDay(spending.periods.current.date_to)} against the same days last month`}>
            <dl className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-3">
              {[["This period", formatRupees(spending.current)], ["Same days last month", formatRupees(spending.previous)], ["Change", percentText(spending.change_percent)]].map(([label, value]) => (
                <div key={label} className="rounded-xl bg-slate-50 px-4 py-3">
                  <dt className="text-xs text-slate-500">{label}</dt>
                  <dd className="font-display mt-1 text-lg font-medium text-slate-900">{value}</dd>
                </div>
              ))}
            </dl>
            {spending.top_categories.length > 0 ? (
              <div className="mt-5">
                <BarList color={SERIES.coffee} measureLabel="Spending by category this month" rows={spending.top_categories.map((c) => ({
                  id: c.category_id, label: c.category_name ?? "—", value: Number(c.value), display: formatRupees(c.value) }))} />
              </div>
            ) : <Empty>No supplier bills this month yet.</Empty>}
          </Panel>
        )}

        {payments && (
          <Panel className={spending ? "" : "xl:col-span-3"} title="Payables" subtitle="What is owed to suppliers today" icon={FileText}
            href="/dashboard/supplier-balances" linkLabel="Balances">
            {payments.top_outstanding.length === 0 ? <Empty>Nothing is owed to suppliers.</Empty> : (
              <ul>
                {payments.top_outstanding.map((s) => (
                  <Row key={s.supplier_id}>
                    <span className="min-w-0 truncate font-medium text-slate-900">{s.supplier_name}</span>
                    <span className="shrink-0 text-right text-slate-600"><span className="tabular-nums">{formatRupees(s.outstanding)}</span><span className="block text-xs text-slate-500">{s.open_bill_count} bills</span></span>
                  </Row>
                ))}
              </ul>
            )}
            <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">Paid this month: <span className="font-medium text-slate-800">{formatRupees(payments.paid_this_month)}</span></p>
          </Panel>
        )}

        {planning && (
          <Panel title="Meal planning" subtitle="Plans for the next seven days" icon={CalendarRange} href="/dashboard/meal-plans" linkLabel="Plans">
            {planning.upcoming.length === 0 ? <Empty>No meal plan for the next seven days.</Empty> : (
              <ul>
                {planning.upcoming.map((p) => (
                  <Row key={p.id} href={`/dashboard/meal-plans/${p.id}`}>
                    <span className="min-w-0"><span className="font-medium text-slate-900">{p.meal_session_name}</span><span className="block text-xs text-slate-500">{formatDay(p.plan_date)} · {p.expected_headcount} people</span></span>
                    <StatusBadge status={p.status} />
                  </Row>
                ))}
              </ul>
            )}
            <p className="mt-3 text-xs text-slate-500">{planning.approved_standards} approved portion standards · {planning.draft_standards} drafts</p>
          </Panel>
        )}

        {outsourced && (
          <Panel title="Outsourced food" subtitle="Yesterday to the day after tomorrow" icon={Soup}
            href="/dashboard/outsourced-food" linkLabel="Orders">
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
              <p className="mt-3 text-xs text-slate-500">Planned cost of this month&rsquo;s ordered meals: {formatRupees(outsourced.planned_cost_this_month)}</p>
            )}
          </Panel>
        )}

        {data.activity && (
          <Panel title="Recent activity" subtitle="Latest recorded actions on this campus" icon={History}
            href={canAccessPath(role, "/dashboard/audit", permissions) ? "/dashboard/audit" : undefined} linkLabel="Audit log">
            {data.activity.length === 0 ? <Empty>No recorded activity yet.</Empty> : (
              <ol className="relative mt-1 space-y-4 border-l border-slate-200 pl-5">
                {data.activity.slice(0, 7).map((a) => (
                  <li key={a.id} className="relative text-sm">
                    <span aria-hidden className="absolute top-1.5 -left-[25px] h-2 w-2 rounded-full bg-brand-500 ring-4 ring-white" />
                    <p className="text-slate-800"><span className="font-medium text-slate-900">{a.user_name}</span> · {humanize(a.action).toLowerCase()} {humanize(a.entity_type).toLowerCase()}{a.entity_id ? ` #${a.entity_id}` : ""}</p>
                    <p className="text-xs text-slate-500">{formatDateTime(a.created_at)}</p>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        )}

        {data.team && (
          <Panel title="Team and access" icon={Users} href="/dashboard/staff" linkLabel="Staff">
            <ul>
              <Row><span>Admins</span><span className="font-medium tabular-nums">{data.team.active_admins}</span></Row>
              <Row><span>Kitchen managers</span><span className="font-medium tabular-nums">{data.team.active_kitchen_managers}</span></Row>
              <Row><span>Staff</span><span className="font-medium tabular-nums">{data.team.active_staff}</span></Row>
              <Row><span>Staff with no access assigned</span><span className="font-medium tabular-nums">{data.team.staff_without_access}</span></Row>
              <Row><span>Inactive accounts</span><span className="font-medium tabular-nums">{data.team.inactive_users}</span></Row>
            </ul>
          </Panel>
        )}

        {canCopilot && (
          <section className="relative flex min-w-0 flex-col justify-between overflow-hidden rounded-2xl bg-slate-900 p-6 text-white shadow-card">
            <div aria-hidden className="pointer-events-none absolute -right-10 -bottom-16 h-52 w-52 rounded-full bg-brand-600/40 blur-3xl" />
            <div className="relative">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10 text-brand-200 ring-1 ring-white/15"><Bot size={19} aria-hidden /></span>
              <h2 className="font-display mt-4 text-xl font-medium">Kitchen Copilot</h2>
              <p className="mt-1.5 text-sm leading-relaxed text-white/70">Plan and order for a meal, explain this month&rsquo;s spending, or look into a stock difference. Nothing changes until a person approves it.</p>
            </div>
            <Link href="/dashboard/copilot" className="relative mt-6 inline-flex w-fit items-center gap-2 rounded-[10px] bg-white px-4 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-brand-50">
              Open Copilot <ArrowRight size={15} aria-hidden />
            </Link>
          </section>
        )}
      </div>

      {shortcuts.length > 0 && (
        <Card>
          <CardHeader title="Shortcuts" subtitle="The screens you use most" icon={ArrowUpRight} iconTone="brand" />
          <Shortcuts items={shortcuts} />
        </Card>
      )}

      <p className="text-xs text-slate-500">Data generated {formatDateTime(data.generated_at)} · campus-scoped</p>
    </div>
  );
}
