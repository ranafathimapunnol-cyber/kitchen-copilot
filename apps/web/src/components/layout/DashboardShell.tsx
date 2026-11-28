"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Bell,
  CalendarDays,
  ChefHat,
  ChevronDown,
  ChevronRight,
  Loader2,
  LogOut,
  Menu,
  Search,
  ShieldCheck,
} from "lucide-react";

import CommandPalette from "./CommandPalette";
import CopilotDock from "@/components/copilot/CopilotDock";
import CopilotProvider from "@/components/copilot/CopilotProvider";
import Sidebar from "./Sidebar";
import { CurrentUserContext } from "./CurrentUser";
import {
  AuthorizationProvider,
  useAuthorization,
} from "./AuthorizationContext";
import ThemePicker from "@/components/ui/ThemePicker";
import { ToastProvider } from "@/components/ui/Toast";
import { cn } from "@/components/ui/cn";
import { useAuth } from "@/hooks/useAuth";
import { canAccessPath, homePath } from "@/lib/auth/permissions";
import { attentionItems, canReadDashboard } from "@/lib/dashboard";
import { findNavEntry, formatRole } from "@/lib/navigation";
import { clearOverviewCache, useOverview } from "@/lib/useOverview";
import type { User } from "@/types";

const COLLAPSE_KEY = "kc.sidebar.collapsed";

function LoadingWorkspace() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 bg-slate-50">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-raised">
        <ChefHat size={23} aria-hidden />
      </div>
      <div role="status" className="flex items-center gap-2.5 text-sm text-slate-500">
        <Loader2 size={16} className="animate-spin text-brand-600" aria-hidden />
        Preparing your workspace…
      </div>
    </div>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

/** A menu anchored to a top-bar button; closes on outside click and Escape. */
function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        ref.current?.querySelector<HTMLButtonElement>("button")?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return { open, setOpen, ref };
}

const popoverPanel =
  "absolute right-0 top-[calc(100%+8px)] z-50 w-[min(22rem,calc(100vw-2rem))] origin-top-right animate-pop-in overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-overlay";

function Notifications({ role, permissions }: { role: string; permissions: string[] }) {
  const { open, setOpen, ref } = usePopover();
  const enabled = canReadDashboard(role, permissions);
  const { data, loading } = useOverview(enabled);
  const items = data
    ? attentionItems(data).filter((item) => canAccessPath(role, item.href, permissions))
    : [];
  const total = items.reduce((sum, item) => sum + item.count, 0);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={total > 0 ? `Notifications, ${total} waiting` : "Notifications"}
        className="relative flex h-10 w-10 items-center justify-center rounded-xl text-slate-600 transition-colors hover:bg-sand/50 hover:text-slate-900"
      >
        <Bell size={18} aria-hidden />
        {total > 0 && (
          <span className="absolute top-1.5 right-1.5 flex h-[17px] min-w-[17px] items-center justify-center rounded-full bg-brand-600 px-1 text-[10px] leading-none font-semibold text-white ring-2 ring-slate-50">
            {total > 99 ? "99+" : total}
          </span>
        )}
      </button>

      {open && (
        <div className={popoverPanel} role="dialog" aria-label="Notifications">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-slate-900">Needs attention</p>
            {total > 0 && <span className="text-xs text-slate-500">{total} waiting</span>}
          </div>
          {!enabled ? (
            <p className="px-4 py-6 text-center text-sm text-slate-500">
              Your account has no dashboard figures, so there is nothing to report here.
            </p>
          ) : loading && !data ? (
            <p className="flex items-center justify-center gap-2 px-4 py-6 text-sm text-slate-500">
              <Loader2 size={15} className="animate-spin" aria-hidden /> Checking…
            </p>
          ) : items.length === 0 ? (
            <div className="px-4 py-7 text-center">
              <p className="text-sm font-medium text-slate-900">All caught up</p>
              <p className="mt-1 text-xs text-slate-500">Nothing is waiting for you right now.</p>
            </div>
          ) : (
            <ul className="max-h-80 overflow-y-auto py-1.5">
              {items.map((item) => (
                <li key={item.label}>
                  <Link
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm text-slate-700 transition-colors hover:bg-brand-50/60"
                  >
                    <span className="min-w-0">{item.label}</span>
                    <span className="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-800 ring-1 ring-amber-200/70 ring-inset">
                      {item.count}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function AccountMenu({ user, onLogout }: { user: User; onLogout: () => Promise<void> }) {
  const { open, setOpen, ref } = usePopover();
  const [signingOut, setSigningOut] = useState(false);
  const displayName = user.full_name || user.email;

  const signOut = async () => {
    setSigningOut(true);
    try {
      await onLogout();
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`Account menu for ${displayName}`}
        className="flex h-10 items-center gap-2.5 rounded-xl py-1 pr-2 pl-1 transition-colors hover:bg-sand/50"
      >
        <span
          aria-hidden
          className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-brand-100 to-brand-200 text-xs font-semibold text-brand-800 ring-1 ring-brand-200"
        >
          {initials(displayName)}
        </span>
        <span className="hidden min-w-0 text-left leading-tight md:block">
          <span className="block max-w-[10rem] truncate text-[13px] font-semibold text-slate-900">{displayName}</span>
          <span className="block text-[11px] text-slate-500">{formatRole(user.role)}</span>
        </span>
        <ChevronDown size={15} aria-hidden className={cn("hidden text-slate-400 transition-transform md:block", open && "rotate-180")} />
      </button>

      {open && (
        <div className={cn(popoverPanel, "w-64")} role="menu" aria-label="Account">
          <div className="border-b border-slate-100 px-4 py-3.5">
            <p className="truncate text-sm font-semibold text-slate-900">{displayName}</p>
            <p className="truncate text-xs text-slate-500">{user.email}</p>
            <span className="mt-2 inline-flex rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700 ring-1 ring-brand-100 ring-inset">
              {formatRole(user.role)}
            </span>
          </div>
          <div className="border-b border-slate-100 px-4 py-3">
            <p className="mb-2 text-[11px] font-semibold tracking-[0.12em] text-slate-500 uppercase">Theme</p>
            <ThemePicker compact />
          </div>
          <div className="p-1.5">
            <Link
              href="/dashboard/account"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-slate-700 transition-colors hover:bg-brand-50/70"
            >
              <ShieldCheck size={16} aria-hidden className="text-slate-500" /> Account security
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={() => void signOut()}
              disabled={signingOut}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-red-700 transition-colors hover:bg-red-50 disabled:opacity-60"
            >
              {signingOut ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <LogOut size={16} aria-hidden />}
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function DashboardWorkspace({
  user,
  logout,
  children,
}: {
  user: User;
  logout: () => Promise<void>;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const { permissions, loading: permissionsLoading } = useAuthorization();

  const allowed = canAccessPath(user.role, pathname, permissions);

  useEffect(() => {
    if (!permissionsLoading && !allowed) {
      router.replace(homePath(user.role));
    }
  }, [permissionsLoading, allowed, router, user.role]);

  // The rail preference is per browser; storage may be unavailable.
  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- read once from storage after mount
      setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      /* storage blocked: keep the full sidebar */
    }
  }, []);

  const toggleCollapsed = () => {
    setCollapsed((value) => {
      try {
        window.localStorage.setItem(COLLAPSE_KEY, value ? "0" : "1");
      } catch {
        /* storage blocked */
      }
      return !value;
    });
  };

  // The drawer closes on Escape and holds the page still while open.
  useEffect(() => {
    if (!mobileOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };

    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    root.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      root.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [mobileOpen]);

  if (permissionsLoading || !allowed) {
    return <LoadingWorkspace />;
  }

  const current = findNavEntry(pathname);
  const isDetail = current ? pathname !== current.item.href && pathname !== current.item.alternate?.href : false;
  const detailLabel = isDetail
    ? pathname.endsWith("/new") ? "New" : pathname.endsWith("/report") ? "Report" : pathname.endsWith("/suggest") ? "Suggestions" : "Details"
    : null;
  const title = detailLabel ?? current?.item.label ?? "Kitchen Copilot";
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });

  return (
    <CopilotProvider userId={user.id} role={user.role} permissions={permissions}>
    <div className="min-h-screen bg-slate-50 print:min-h-0 print:bg-white">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[200] focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-brand-700 focus:shadow-raised"
      >
        Skip to content
      </a>

      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          tabIndex={-1}
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-40 animate-fade-in bg-black/40 backdrop-blur-[2px] lg:hidden print:hidden"
        />
      )}

      <CommandPalette role={user.role} permissions={permissions} open={paletteOpen} onOpenChange={setPaletteOpen} />

      <Sidebar
        role={user.role}
        permissions={permissions}
        mobileOpen={mobileOpen}
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
        onClose={() => setMobileOpen(false)}
      />

      <div
        className={cn(
          "flex min-h-screen min-w-0 flex-col transition-[padding] duration-300 ease-out print:min-h-0 print:pl-0",
          collapsed ? "lg:pl-[76px]" : "lg:pl-[17rem]"
        )}
      >
        <header className="sticky top-0 z-30 flex h-[68px] shrink-0 items-center justify-between gap-3 border-b border-slate-200/70 bg-slate-50/85 px-4 backdrop-blur-md sm:px-6 lg:px-10 print:hidden">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
              aria-expanded={mobileOpen}
              aria-controls="app-sidebar"
              className="-ml-2 rounded-xl p-2 text-slate-600 hover:bg-sand/50 lg:hidden"
            >
              <Menu size={20} />
            </button>

            <div className="min-w-0">
              <nav aria-label="Breadcrumb" className="hidden sm:block">
                <ol className="flex min-w-0 items-center gap-1 text-[11.5px] text-slate-500">
                  <li>
                    <Link href={homePath(user.role)} className="hover:text-slate-800">Home</Link>
                  </li>
                  {current && current.group.label !== "Overview" && (
                    <li className="flex items-center gap-1">
                      <ChevronRight size={12} aria-hidden className="text-slate-300" />
                      {current.group.label}
                    </li>
                  )}
                  {current && (isDetail || current.group.label === "Overview") && current.item.href !== "/dashboard" && (
                    <li className="flex min-w-0 items-center gap-1">
                      <ChevronRight size={12} aria-hidden className="text-slate-300" />
                      {isDetail ? (
                        <Link href={current.item.href} className="truncate hover:text-slate-800">{current.item.label}</Link>
                      ) : (
                        <span className="truncate">{current.item.label}</span>
                      )}
                    </li>
                  )}
                </ol>
              </nav>
              <p aria-current="page" className="truncate text-[15px] font-semibold text-slate-900 sm:mt-0.5">
                {title}
              </p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1 sm:gap-2">
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              aria-label="Search screens and actions"
              aria-keyshortcuts="Meta+K Control+K"
              className="flex h-10 items-center gap-2 rounded-xl text-slate-600 transition-colors hover:bg-sand/50 hover:text-slate-900 max-md:w-10 max-md:justify-center md:mr-1 md:w-56 md:border md:border-slate-200/80 md:bg-white md:px-3 md:text-sm md:text-slate-500 md:hover:bg-white md:hover:border-brand-200 lg:w-64"
            >
              <Search size={17} aria-hidden className="shrink-0" />
              <span className="hidden flex-1 text-left md:inline">Search or jump to…</span>
              <kbd className="hidden rounded-md border border-slate-200 bg-slate-50 px-1.5 text-[11px] leading-5 text-slate-500 md:inline">⌘K</kbd>
            </button>
            <p className="mr-1 hidden items-center gap-2 rounded-full border border-slate-200/80 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 2xl:flex">
              <CalendarDays size={13} aria-hidden className="text-brand-600" />
              {today}
            </p>
            <Notifications role={user.role} permissions={permissions} />
            <span aria-hidden className="mx-1 hidden h-6 w-px bg-slate-200 sm:block" />
            <AccountMenu user={user} onLogout={logout} />
          </div>
        </header>

        <main
          id="main-content"
          tabIndex={-1}
          className="mx-auto w-full max-w-[1480px] min-w-0 flex-1 px-4 pt-6 pb-28 focus:outline-none sm:px-6 lg:px-10 lg:pt-9 print:max-w-none print:p-0"
        >
          {children}
        </main>
      </div>
      <CopilotDock hidden={mobileOpen} />
    </div>
    </CopilotProvider>
  );
}

export default function DashboardShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, loading, logout } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      clearOverviewCache();
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return <LoadingWorkspace />;
  }

  const signOut = async () => {
    clearOverviewCache();
    await logout();
  };

  return (
    <AuthorizationProvider userId={user.id}>
      <ToastProvider>
        <CurrentUserContext.Provider value={user}>
          <DashboardWorkspace key={user.id} user={user} logout={signOut}>
            {children}
          </DashboardWorkspace>
        </CurrentUserContext.Provider>
      </ToastProvider>
    </AuthorizationProvider>
  );
}
