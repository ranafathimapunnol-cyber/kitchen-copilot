"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CalendarDays, ChefHat, ChevronRight, Menu } from "lucide-react";

import Sidebar from "./Sidebar";
import {
  AuthorizationProvider,
  useAuthorization,
} from "./AuthorizationContext";
import { ToastProvider } from "@/components/ui/Toast";
import { useAuth } from "@/hooks/useAuth";
import { canAccessPath, homePath } from "@/lib/auth/permissions";
import { findNavEntry } from "@/lib/navigation";
import type { User } from "@/types";

function LoadingWorkspace() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50">
      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm">
        <ChefHat size={22} aria-hidden />
      </div>
      <div
        role="status"
        className="flex items-center gap-2.5 text-sm text-slate-500"
      >
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
        Loading workspace…
      </div>
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

  const {
    permissions,
    loading: permissionsLoading,
  } = useAuthorization();

  const allowed = canAccessPath(
    user.role,
    pathname,
    permissions
  );

  useEffect(() => {
    if (!permissionsLoading && !allowed) {
      router.replace(homePath(user.role));
    }
  }, [permissionsLoading, allowed, router, user.role]);

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
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });

  return (
    <div className="min-h-screen bg-slate-50 print:min-h-0 print:bg-white">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[200] focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-brand-700 focus:shadow-raised"
      >
        Skip to content
      </a>

      {/* One overlay, owned here; the sidebar no longer draws its own. */}
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          tabIndex={-1}
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-40 animate-fade-in bg-slate-950/40 backdrop-blur-[2px] lg:hidden print:hidden"
        />
      )}

      <Sidebar
        user={user}
        role={user.role}
        permissions={permissions}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
        onLogout={logout}
      />

      <div className="flex min-h-screen flex-col lg:pl-64 print:min-h-0 print:pl-0">
        <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white/85 px-4 backdrop-blur-md sm:px-6 lg:px-8 print:hidden">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
              aria-expanded={mobileOpen}
              aria-controls="app-sidebar"
              className="-ml-2 rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden"
            >
              <Menu size={20} />
            </button>

            <nav aria-label="Breadcrumb" className="min-w-0">
              <ol className="flex min-w-0 items-center gap-1.5 text-sm">
                {current && current.group.label !== "Overview" && (
                  <li className="hidden items-center gap-1.5 text-slate-500 sm:flex">
                    {current.group.label}
                    <ChevronRight
                      size={14}
                      aria-hidden
                      className="text-slate-300"
                    />
                  </li>
                )}
                <li
                  aria-current="page"
                  className="truncate font-semibold text-slate-900"
                >
                  {current?.item.label ?? "Kitchen Copilot"}
                </li>
              </ol>
            </nav>
          </div>

          <p className="hidden shrink-0 items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 sm:flex">
            <CalendarDays size={13} aria-hidden className="text-slate-400" />
            {today}
          </p>
        </header>

        <main
          id="main-content"
          tabIndex={-1}
          className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 focus:outline-none sm:px-6 lg:px-8 lg:py-8 print:max-w-none print:p-0"
        >
          {children}
        </main>
      </div>
    </div>
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
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return <LoadingWorkspace />;
  }

  return (
    <AuthorizationProvider userId={user.id}>
      <ToastProvider>
        <DashboardWorkspace user={user} logout={logout}>
          {children}
        </DashboardWorkspace>
      </ToastProvider>
    </AuthorizationProvider>
  );
}
