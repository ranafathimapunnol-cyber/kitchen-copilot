import type { ReactNode } from "react";
import { BookOpen, ChefHat, Package, Recycle } from "lucide-react";

const MODULES = [
  {
    icon: Package,
    title: "Inventory & suppliers",
    body: "Items, units and conversions kept consistent across the store.",
  },
  {
    icon: BookOpen,
    title: "Menus & meal sessions",
    body: "Plan each session and the quantities it needs per person.",
  },
  {
    icon: Recycle,
    title: "Waste tracking",
    body: "See what is lost at storage, cooking and serving, and what it costs.",
  },
];

/**
 * The signed-out layout shared by sign-in and the password pages: a brand
 * panel on wide screens, the form column everywhere.
 */
export default function AuthShell({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="grid min-h-screen bg-white lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <section
        aria-hidden
        className="relative hidden overflow-hidden bg-brand-700 p-12 text-white lg:flex lg:flex-col lg:justify-between"
      >
        <div
          className="pointer-events-none absolute inset-0 opacity-60"
          style={{
            background:
              "radial-gradient(60rem 30rem at 0% 0%, rgb(255 255 255 / 0.12), transparent 60%), radial-gradient(40rem 30rem at 100% 100%, rgb(15 23 42 / 0.35), transparent 60%)",
          }}
        />

        <div className="relative flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/25">
            <ChefHat size={21} />
          </div>
          <div className="leading-tight">
            <p className="font-bold tracking-tight">Kitchen Copilot</p>
            <p className="text-xs text-white/75">Mess management</p>
          </div>
        </div>

        <div className="relative max-w-md">
          <h2 className="text-3xl leading-tight font-bold tracking-tight">
            Every meal served, every gram accounted for.
          </h2>
          <p className="mt-3 text-white/80">
            One workspace for the campus kitchen, from the store room to the
            serving counter.
          </p>

          <ul className="mt-10 space-y-5">
            {MODULES.map(({ icon: Icon, title: moduleTitle, body }) => (
              <li key={moduleTitle} className="flex gap-4">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/20">
                  <Icon size={17} />
                </div>
                <div>
                  <p className="font-semibold">{moduleTitle}</p>
                  <p className="mt-0.5 text-sm text-white/75">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-white/60">
          Authorized campus users only
        </p>
      </section>

      <section className="flex items-center justify-center bg-slate-50 px-4 py-12 sm:px-8 lg:bg-white">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <div className="mb-6 flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm lg:hidden">
              <ChefHat size={22} aria-hidden />
            </div>

            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              {title}
            </h1>
            {description && (
              <p className="mt-2 text-sm text-slate-500">{description}</p>
            )}
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card sm:p-7 lg:border-0 lg:p-0 lg:shadow-none">
            {children}
          </div>

          {footer && (
            <div className="mt-8 text-center text-sm text-slate-500 lg:text-left">
              {footer}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
