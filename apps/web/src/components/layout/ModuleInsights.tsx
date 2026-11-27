"use client";

import type { ElementType } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CalendarRange,
  ClipboardCheck,
  CookingPot,
  FileText,
  PackageX,
  Soup,
  Truck,
  Users,
  UtensilsCrossed,
  Wallet,
  Warehouse,
} from "lucide-react";

import { canAccessPath } from "@/lib/auth/permissions";
import { canReadDashboard, percentText, type DashboardOverview } from "@/lib/dashboard";
import { formatRupees } from "@/lib/payments";
import { useOverview } from "@/lib/useOverview";
import { cn } from "@/components/ui/cn";

type Insight = { label: string; value: string; href: string; icon: ElementType; tone?: "warning" | "neutral" };
type Module = { title: string; insights: (d: DashboardOverview) => (Insight | null)[] };

const n = (value: number | undefined | null) => (value ?? 0).toLocaleString("en-IN");

/**
 * Figures shown at the top of each module's list screens. Every figure
 * comes from the dashboard overview (one cached request; sections appear
 * only when the API includes them for this user) and links to the screen
 * where it can be acted on.
 */
const MODULES: Record<string, Module> = {
  purchasing: {
    title: "Purchasing at a glance",
    insights: ({ spending, payments }) => [
      spending ? { label: "Purchases this month", value: formatRupees(spending.current), href: "/dashboard/analytics", icon: Wallet } : null,
      spending ? { label: "Against the same days last month", value: percentText(spending.change_percent), href: "/dashboard/analytics", icon: Wallet } : null,
      payments ? { label: "Outstanding payables", value: formatRupees(payments.outstanding), href: "/dashboard/supplier-balances", icon: FileText } : null,
      payments ? { label: "Open bills", value: `${n(payments.open_bill_count)} · ${n(payments.suppliers_owed)} suppliers`, href: "/dashboard/supplier-bills", icon: Truck } : null,
    ],
  },
  stock: {
    title: "Stock at a glance",
    insights: ({ stock, counts, kitchen }) => [
      stock ? { label: "Below minimum", value: n(stock.below_minimum), href: "/dashboard/stock", icon: Warehouse, tone: stock.below_minimum ? "warning" : "neutral" } : null,
      stock ? { label: "Out of stock", value: `${n(stock.out_of_stock)} of ${n(stock.items_tracked)}`, href: "/dashboard/stock", icon: PackageX, tone: stock.out_of_stock ? "warning" : "neutral" } : null,
      counts ? { label: "Adjustments to approve", value: n(counts.pending_adjustments), href: "/dashboard/stock-adjustments", icon: ClipboardCheck, tone: counts.pending_adjustments ? "warning" : "neutral" } : null,
      kitchen ? { label: "Kitchen issues today", value: `${n(kitchen.issues_today)} · ${n(kitchen.draft_issues)} drafts`, href: "/dashboard/kitchen-issues", icon: CookingPot } : null,
    ],
  },
  meals: {
    title: "Meals at a glance",
    insights: ({ headcount, meals, planning }) => [
      headcount ? { label: "Today's headcount", value: headcount.today === null ? "Not recorded" : n(headcount.today), href: "/dashboard/meals", icon: Users } : null,
      meals ? { label: "Open meal records", value: `${n(meals.open_count)} · ${n(meals.awaiting_close_count)} from earlier days`, href: "/dashboard/meals", icon: UtensilsCrossed, tone: meals.awaiting_close_count ? "warning" : "neutral" } : null,
      planning ? { label: "Plans for the next 7 days", value: n(planning.upcoming.length), href: "/dashboard/meal-plans", icon: CalendarRange } : null,
      planning ? { label: "Drafts to finish", value: `${n(planning.draft_plans)} plans · ${n(planning.draft_standards)} standards`, href: "/dashboard/portion-standards", icon: AlertTriangle, tone: planning.draft_plans || planning.draft_standards ? "warning" : "neutral" } : null,
    ],
  },
  outsourced: {
    title: "Outsourced food at a glance",
    insights: ({ outsourced }) => outsourced ? [
      { label: "Orders around today", value: n(outsourced.orders.length), href: "/dashboard/outsourced-food", icon: Soup },
      { label: "Deliveries to confirm", value: n(outsourced.draft_deliveries), href: "/dashboard/outsourced-food", icon: Truck, tone: outsourced.draft_deliveries ? "warning" : "neutral" },
      { label: "Waiting for a meal record", value: n(outsourced.waiting_for_meal_record), href: "/dashboard/meals", icon: UtensilsCrossed, tone: outsourced.waiting_for_meal_record ? "warning" : "neutral" },
      outsourced.planned_cost_this_month !== undefined ? { label: "Planned cost this month", value: formatRupees(outsourced.planned_cost_this_month), href: "/dashboard/outsourced-food/report", icon: Wallet } : null,
    ] : [],
  },
};

/** List screens (exact paths) and the module whose figures they show. */
const ROUTES: Record<string, keyof typeof MODULES> = {
  "/dashboard/purchase-orders": "purchasing",
  "/dashboard/supplier-bills": "purchasing",
  "/dashboard/receipts": "purchasing",
  "/dashboard/supplier-payments": "purchasing",
  "/dashboard/stock-counts": "stock",
  "/dashboard/stock-adjustments": "stock",
  "/dashboard/stock-movements": "stock",
  "/dashboard/opening-stock": "stock",
  "/dashboard/kitchen-issues": "stock",
  "/dashboard/meals": "meals",
  "/dashboard/meal-plans": "meals",
  "/dashboard/portion-standards": "meals",
  "/dashboard/outsourced-food": "outsourced",
};

export default function ModuleInsights({ pathname, role, permissions }: { pathname: string; role: string; permissions: string[] }) {
  const key = ROUTES[pathname];
  const enabled = Boolean(key) && canReadDashboard(role, permissions);
  const { data } = useOverview(enabled);
  if (!key || !enabled || !data) return null;

  const items = MODULES[key].insights(data)
    .filter((i): i is Insight => i !== null && canAccessPath(role, i.href, permissions));
  if (items.length === 0) return null;

  return (
    <section aria-label={MODULES[key].title} className="print:hidden" data-module-insights={key}>
      <p className="mb-2 text-[10.5px] font-semibold tracking-[0.14em] text-slate-500 uppercase">{MODULES[key].title}</p>
      <ul className="grid grid-cols-1 gap-2.5 min-[480px]:grid-cols-2 xl:grid-cols-4">
        {items.map((item) => (
          <li key={item.label} className="min-w-0">
            <Link href={item.href}
              className={cn("group flex h-full items-center gap-3 rounded-xl border bg-white px-3.5 py-3 transition-[border-color,box-shadow] duration-200 hover:shadow-card",
                item.tone === "warning" ? "border-amber-200/80 hover:border-amber-300" : "border-slate-200/80 hover:border-brand-200")}>
              <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                item.tone === "warning" ? "bg-amber-50 text-amber-700" : "bg-brand-50 text-brand-700")}>
                <item.icon size={16} aria-hidden />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[15px] font-semibold text-slate-900 tabular-nums">{item.value}</span>
                <span className="block truncate text-xs text-slate-500">{item.label}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
