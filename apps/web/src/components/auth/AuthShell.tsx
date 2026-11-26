import type { ReactNode } from "react";
import { Bot, CalendarRange, ChefHat, Package } from "lucide-react";

const MODULES = [
  {
    icon: Package,
    title: "Stock, purchasing & suppliers",
    body: "A ledger that cannot be rewritten, bills, receipts and payments in one place.",
  },
  {
    icon: CalendarRange,
    title: "Meals & planning",
    body: "Headcounts, portion standards and plans that become purchase orders.",
  },
  {
    icon: Bot,
    title: "Kitchen Copilot",
    body: "Ask in plain words; every action waits for a person to approve it.",
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
    <main className="grid min-h-screen bg-slate-50 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <section
        aria-hidden
        className="relative m-3 hidden overflow-hidden rounded-[1.75rem] bg-slate-900 p-12 text-white lg:flex lg:flex-col lg:justify-between"
      >
        <div
          className="pointer-events-none absolute inset-0 opacity-60"
          style={{
            background:
              "radial-gradient(50rem 28rem at 0% 0%, rgb(139 111 80 / 0.45), transparent 60%), radial-gradient(36rem 26rem at 100% 100%, rgb(232 221 202 / 0.12), transparent 60%)",
          }}
        />

        <div className="relative flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 ring-1 ring-white/20">
            <ChefHat size={21} />
          </div>
          <div className="leading-tight">
            <p className="font-display text-lg font-medium">Kitchen Copilot</p>
            <p className="text-xs text-white/75">Mess management</p>
          </div>
        </div>

        <div className="relative max-w-md">
          <h2 className="font-display text-[2.4rem] leading-[1.1] font-normal">
            Every meal served, every gram accounted for.
          </h2>
          <p className="mt-3 text-white/80">
            One workspace for the campus kitchen, from the store room to the
            serving counter.
          </p>

          <ul className="mt-10 space-y-5">
            {MODULES.map(({ icon: Icon, title: moduleTitle, body }) => (
              <li key={moduleTitle} className="flex gap-4">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/8 text-brand-200 ring-1 ring-white/15">
                  <Icon size={17} />
                </div>
                <div>
                  <p className="font-medium">{moduleTitle}</p>
                  <p className="mt-0.5 text-sm text-white/70">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-white/60">
          Authorized campus users only
        </p>
      </section>

      <section className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <div className="mb-6 flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm lg:hidden">
              <ChefHat size={22} aria-hidden />
            </div>

            <h1 className="font-display text-[2rem] leading-tight font-medium text-slate-900">
              {title}
            </h1>
            {description && (
              <p className="mt-2 text-sm text-slate-500">{description}</p>
            )}
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-card sm:p-8">
            {children}
          </div>

          {footer && (
            <div className="mt-8 text-center text-sm text-slate-500">
              {footer}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
