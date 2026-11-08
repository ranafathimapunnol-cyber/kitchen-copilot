import Link from "next/link";
import {
  Tags,
  Ruler,
  Package,
  Truck,
  Utensils,
  BookOpen,
  ArrowUpRight,
  ChefHat,
} from "lucide-react";

const modules = [
  {
    title: "Categories",
    description: "Organize ingredients into stock categories.",
    href: "/dashboard/categories",
    icon: Tags,
  },
  {
    title: "Units",
    description: "Manage standard measurement units.",
    href: "/dashboard/units",
    icon: Ruler,
  },
  {
    title: "Items",
    description: "Manage kitchen ingredients and stock items.",
    href: "/dashboard/items",
    icon: Package,
  },
  {
    title: "Suppliers",
    description: "Maintain supplier and contact information.",
    href: "/dashboard/suppliers",
    icon: Truck,
  },
  {
    title: "Meal Sessions",
    description: "Configure breakfast, lunch, snacks and dinner.",
    href: "/dashboard/meal-sessions",
    icon: Utensils,
  },
  {
    title: "Menus",
    description: "Create and manage daily meal menus.",
    href: "/dashboard/menus",
    icon: BookOpen,
  },
];

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <section>
        <p className="text-xs font-bold uppercase tracking-widest text-blue-700">
          Workspace Overview
        </p>

        <h1 className="mt-3 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Dashboard
        </h1>

        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 sm:text-base">
          Manage your campus kitchen operations from one centralized workspace.
        </p>
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {modules.map(({ title, description, href, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition duration-200 hover:-translate-y-1 hover:border-blue-300 hover:shadow-lg sm:p-6"
          >
            <div className="flex items-center justify-between">
              <div className="rounded-xl bg-blue-50 p-3 text-blue-700 transition group-hover:bg-blue-700 group-hover:text-white">
                <Icon size={23} />
              </div>

              <ArrowUpRight
                size={19}
                className="text-slate-400 transition group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-blue-700"
              />
            </div>

            <h2 className="mt-5 text-base font-semibold text-slate-900">
              {title}
            </h2>

            <p className="mt-2 text-sm leading-6 text-slate-500">
              {description}
            </p>
          </Link>
        ))}
      </section>

      <section className="flex flex-col gap-4 rounded-xl border border-blue-100 bg-blue-50/70 p-5 sm:flex-row sm:items-center sm:p-6">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-white text-blue-700 shadow-sm">
          <ChefHat size={25} />
        </div>

        <div>
          <h2 className="font-semibold text-slate-900">
            Kitchen operations management
          </h2>

          <p className="mt-1 text-sm leading-6 text-slate-600">
            Start by configuring master data. These records will support
            purchasing, inventory, meal planning and operational reporting.
          </p>
        </div>
      </section>
    </div>
  );
}