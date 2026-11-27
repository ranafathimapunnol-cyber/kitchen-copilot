import type { LucideIcon } from "lucide-react";
import {
  ArrowLeftRight,
  Banknote,
  ClipboardCheck,
  ClipboardList,
  CookingPot,
  BookOpen,
  CalendarRange,
  BarChart3,
  Bot,
  ScrollText,
  ShieldCheck,
  UserCog,
  ChartColumn,
  FileText,
  LayoutDashboard,
  ListChecks,
  ListPlus,
  Package,
  PackageCheck,
  PackagePlus,
  Recycle,
  Ruler,
  Scale,
  Soup,
  Tags,
  Truck,
  Users,
  Utensils,
  UtensilsCrossed,
  Wallet,
  Warehouse,
  Weight,
} from "lucide-react";

/**
 * The application's navigation, grouped by module. This file only describes
 * the routes; who may see each one is decided by canAccessPath in
 * lib/auth/permissions.ts, which this file does not change.
 */

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Shown instead when `href` is not allowed but this page is. */
  alternate?: { label: string; href: string };
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      // Stage 12: the agent (every campus user; jobs check permissions).
      { label: "Kitchen Copilot", href: "/dashboard/copilot", icon: Bot },
    ],
  },
  {
    label: "Inventory",
    items: [
      { label: "Items", href: "/dashboard/items", icon: Package },
      { label: "Categories", href: "/dashboard/categories", icon: Tags },
      { label: "Units", href: "/dashboard/units", icon: Ruler },
      {
        label: "Unit Conversions",
        href: "/dashboard/unit-conversions",
        icon: Scale,
      },
      { label: "Suppliers", href: "/dashboard/suppliers", icon: Truck },
      {
        label: "Stock Balances",
        href: "/dashboard/stock",
        icon: Warehouse,
      },
      {
        label: "Opening Stock",
        href: "/dashboard/opening-stock",
        icon: PackagePlus,
      },
      {
        label: "Stock Counts",
        href: "/dashboard/stock-counts",
        icon: ClipboardCheck,
        // stock_count.create without stock_count.read: record counts only.
        alternate: { label: "Record Stock Count", href: "/dashboard/stock-counts/new" },
      },
      {
        label: "Stock Adjustments",
        href: "/dashboard/stock-adjustments",
        icon: ListChecks,
      },
      {
        label: "Stock Movements",
        href: "/dashboard/stock-movements",
        icon: ArrowLeftRight,
      },
    ],
  },
  {
    label: "Purchasing",
    items: [
      {
        label: "Purchase Orders",
        href: "/dashboard/purchase-orders",
        icon: ClipboardList,
      },
      {
        label: "Supplier Bills",
        href: "/dashboard/supplier-bills",
        icon: FileText,
      },
      {
        label: "Goods Receipts",
        href: "/dashboard/receipts",
        icon: PackageCheck,
      },
      {
        label: "Supplier Payments",
        href: "/dashboard/supplier-payments",
        icon: Banknote,
      },
      {
        label: "Supplier Balances",
        href: "/dashboard/supplier-balances",
        icon: Wallet,
      },
      {
        label: "Purchases vs Payments",
        href: "/dashboard/purchase-payment-report",
        icon: ChartColumn,
      },
    ],
  },
  {
    label: "Menu Planning",
    items: [
      {
        label: "Meal Sessions",
        href: "/dashboard/meal-sessions",
        icon: Utensils,
      },
      { label: "Menus", href: "/dashboard/menus", icon: BookOpen },
      {
        label: "Menu Main Items",
        href: "/dashboard/menu-main-items",
        icon: ListPlus,
      },
      // Stage 6 meal planning: ADMIN and KITCHEN_MANAGER (canAccessPath).
      {
        label: "Portion Standards",
        href: "/dashboard/portion-standards",
        icon: Weight,
      },
      {
        label: "Meal Plans",
        href: "/dashboard/meal-plans",
        icon: CalendarRange,
      },
    ],
  },
  {
    label: "Operations",
    items: [
      {
        label: "Meals",
        href: "/dashboard/meals",
        icon: UtensilsCrossed,
        // meal.create without meal.read: record meals only.
        alternate: { label: "Record a Meal", href: "/dashboard/meals/new" },
      },
      {
        label: "Kitchen Issues",
        href: "/dashboard/kitchen-issues",
        icon: CookingPot,
      },
      // Stage 8a: outsourced orders, deliveries and the report.
      {
        label: "Outsourced Food",
        href: "/dashboard/outsourced-food",
        icon: Soup,
      },
      {
        label: "Waste Tracking",
        href: "/dashboard/waste-tracking",
        icon: Recycle,
      },
    ],
  },
  {
    label: "Reports",
    items: [
      // Stage 9: DASH01–DASH05 and the §5.8 report catalogue.
      { label: "Spending Analysis", href: "/dashboard/analytics", icon: ChartColumn },
      { label: "Reports", href: "/dashboard/reports", icon: BarChart3 },
    ],
  },
  {
    label: "Administration",
    items: [
      { label: "User Accounts", href: "/dashboard/users", icon: UserCog },
      { label: "Staff Management", href: "/dashboard/staff", icon: Users },
      { label: "Audit Log", href: "/dashboard/audit", icon: ScrollText },
      { label: "Account Security", href: "/dashboard/account", icon: ShieldCheck },
    ],
  },
];

export function isActivePath(pathname: string, href: string): boolean {
  return (
    pathname === href ||
    (href !== "/dashboard" && pathname.startsWith(`${href}/`))
  );
}

/** The nav entry (and its group) that owns a pathname, if any. */
export function findNavEntry(
  pathname: string
): { group: NavGroup; item: NavItem } | null {
  for (const group of NAV_GROUPS) {
    for (const item of group.items) {
      if (isActivePath(pathname, item.href)) return { group, item };
    }
  }
  return null;
}

/** "KITCHEN_MANAGER" → "Kitchen Manager". */
export function formatRole(role: string): string {
  return role
    .toLowerCase()
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
