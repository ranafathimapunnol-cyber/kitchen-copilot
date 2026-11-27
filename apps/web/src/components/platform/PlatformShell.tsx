"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity, BarChart3, Building2, LayoutDashboard, Loader2, LogOut, Menu, PlugZap, ScrollText, Settings, ShieldCheck, Users, X,
} from "lucide-react";

import { api, clearCsrfToken } from "@/lib/api/client";
import { PLATFORM_API, type PlatformUser } from "@/lib/platform";
import ThemePicker from "@/components/ui/ThemePicker";
import { ToastProvider } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";

const NAV = [
  { label: "Organisation overview", href: "/platform", icon: LayoutDashboard },
  { label: "Campuses", href: "/platform/campuses", icon: Building2 },
  { label: "Organisation analytics", href: "/platform/analytics", icon: BarChart3 },
  { label: "Platform users", href: "/platform/users", icon: Users },
  { label: "Platform audit log", href: "/platform/audit", icon: ScrollText },
  { label: "Integrations", href: "/platform/integrations", icon: PlugZap },
  { label: "System health", href: "/platform/health", icon: Activity },
  { label: "Settings", href: "/platform/settings", icon: Settings },
];

const PlatformUserContext = createContext<PlatformUser | null>(null);

export function usePlatformUser(): PlatformUser {
  const user = useContext(PlatformUserContext);
  if (!user) throw new Error("usePlatformUser must be used inside PlatformShell");
  return user;
}

export function isActive(pathname: string, href: string): boolean {
  return href === "/platform" ? pathname === "/platform" : pathname === href || pathname.startsWith(`${href}/`);
}

export async function platformSignOut(): Promise<void> {
  try {
    await api.post(`${PLATFORM_API}/auth/logout`);
  } finally {
    clearCsrfToken();
    window.location.replace("/platform/login");
  }
}

/**
 * The platform console: organisation-level navigation only (never campus
 * screens), its own session (checked with /api/platform/auth/me), and the
 * shared theme. A campus session does not open it and it does not open
 * campus screens.
 */
export default function PlatformShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<PlatformUser | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    let active = true;
    api.get<PlatformUser>(`${PLATFORM_API}/auth/me`)
      .then((u) => active && setUser(u))
      .catch((err: unknown) => {
        if (!active) return;
        const message = err instanceof Error ? err.message : "";
        if (/d5e8f0b2a314|not available/i.test(message)) setProblem(message);
        else router.replace("/platform/login");
      });
    return () => { active = false; };
  }, [router]);

  // eslint-disable-next-line react-hooks/set-state-in-effect -- close the phone menu on navigation
  useEffect(() => { setMenuOpen(false); }, [pathname]);

  if (problem) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <div className="max-w-md space-y-3 text-center">
          <p className="text-[11px] font-semibold tracking-[0.16em] text-slate-500 uppercase">Platform</p>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Not available on this database yet</h1>
          <p className="text-sm leading-relaxed text-slate-600">{problem}</p>
          <Link href="/login" className="inline-block text-sm font-medium text-slate-900 underline">Go to the campus sign-in</Link>
        </div>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="flex min-h-screen items-center justify-center gap-2.5 bg-slate-50 text-sm text-slate-500" role="status">
        <Loader2 size={16} className="animate-spin" aria-hidden /> Checking your platform session…
      </main>
    );
  }

  const nav = (
    <nav aria-label="Platform navigation" className="space-y-1">
      {NAV.map(({ label, href, icon: Icon }) => {
        const active = isActive(pathname, href);
        return (
          <Link key={href} href={href} aria-current={active ? "page" : undefined}
            className={cn("flex h-10 items-center gap-3 rounded-lg px-3 text-[13.5px] transition-colors",
              active ? "bg-slate-900 font-semibold text-white" : "font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-950")}>
            <Icon size={17} aria-hidden className={active ? "text-current" : "text-slate-400"} />
            {label}
          </Link>
        );
      })}
    </nav>
  );

  const brand = (
    <Link href="/platform" className="flex items-center gap-3">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#d9f18d] text-[#202522]"><ShieldCheck size={20} aria-hidden /></span>
      <span className="leading-tight">
        <span className="block text-[15px] font-bold tracking-tight text-slate-900">Kitchen Copilot</span>
        <span className="block text-[9.5px] font-semibold tracking-[0.18em] text-slate-500 uppercase">Platform administration</span>
      </span>
    </Link>
  );

  return (
    <PlatformUserContext.Provider value={user}>
      <ToastProvider>
        <div className="min-h-screen bg-slate-50" data-platform-shell>
          <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-slate-200 bg-sidebar px-4 py-5 lg:flex">
            {brand}
            <div className="mt-8 flex-1 overflow-y-auto">{nav}</div>
            <div className="border-t border-slate-200 pt-4 text-xs text-slate-500">
              <p className="truncate font-medium text-slate-800">{user.full_name}</p>
              <p className="truncate">{user.email}</p>
            </div>
          </aside>

          {menuOpen && (
            <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Platform navigation">
              <button type="button" aria-label="Close navigation" className="absolute inset-0 bg-black/40" onClick={() => setMenuOpen(false)} />
              <div className="relative h-full w-72 max-w-[85vw] bg-sidebar px-4 py-5 shadow-overlay">
                <div className="flex items-center justify-between">{brand}
                  <button type="button" aria-label="Close navigation" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" onClick={() => setMenuOpen(false)}><X size={18} /></button>
                </div>
                <div className="mt-8">{nav}</div>
              </div>
            </div>
          )}

          <div className="lg:pl-64">
            <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-slate-200 bg-slate-50/90 px-4 backdrop-blur-md sm:px-6 lg:px-10">
              <div className="flex min-w-0 items-center gap-2">
                <button type="button" aria-label="Open navigation" className="-ml-2 rounded-xl p-2 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setMenuOpen(true)}><Menu size={20} /></button>
                <span className="rounded-full bg-[#d9f18d] px-2.5 py-1 text-[10.5px] font-semibold tracking-[0.12em] text-[#202522] uppercase">Platform</span>
                <span className="hidden truncate text-sm text-slate-500 sm:inline">Organisation-level administration · separate from campus operations</span>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <ThemePicker compact />
                <button type="button" disabled={signingOut}
                  onClick={() => { setSigningOut(true); void platformSignOut(); }}
                  className="flex h-9 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 hover:border-slate-400 disabled:opacity-60">
                  {signingOut ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <LogOut size={15} aria-hidden />}
                  <span className="hidden sm:inline">Sign out</span>
                </button>
              </div>
            </header>
            <main id="main-content" className="mx-auto w-full max-w-[1400px] min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-9">
              {children}
            </main>
          </div>
        </div>
      </ToastProvider>
    </PlatformUserContext.Provider>
  );
}
