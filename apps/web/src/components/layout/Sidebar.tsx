"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChefHat, Loader2, LogOut, X } from "lucide-react";

import { canAccessPath } from "@/lib/auth/permissions";
import { NAV_GROUPS, formatRole, isActivePath } from "@/lib/navigation";
import { cn } from "@/components/ui/cn";
import type { User } from "@/types";

type SidebarProps = {
  user: User;
  role: string;
  permissions: string[];
  mobileOpen: boolean;
  onClose: () => void;
  onLogout: () => Promise<void>;
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

export default function Sidebar({
  user,
  role,
  permissions,
  mobileOpen,
  onClose,
  onLogout,
}: SidebarProps) {
  const pathname = usePathname();
  const [signingOut, setSigningOut] = useState(false);

  // Visibility is decided only by canAccessPath, exactly as before; the
  // grouping is presentation. Groups with nothing visible are dropped. An
  // entry whose page is not allowed may offer an alternate page the user is
  // allowed to open (a counter who may record but not view stock counts).
  const visibleGroups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.flatMap((item) => {
      if (canAccessPath(role, item.href, permissions)) return [item];
      const alternate = item.alternate;
      return alternate && canAccessPath(role, alternate.href, permissions)
        ? [{ ...item, ...alternate }]
        : [];
    }),
  })).filter((group) => group.items.length > 0);

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
    <aside
      id="app-sidebar"
      aria-label="Main navigation"
      className={cn(
        "fixed inset-y-0 left-0 z-50 flex w-[17rem] flex-col border-r border-slate-200 bg-white transition-[transform,visibility] duration-300 ease-out lg:visible lg:w-64 lg:translate-x-0 print:hidden",
        mobileOpen
          ? "visible translate-x-0 shadow-overlay"
          : "invisible -translate-x-full"
      )}
    >
      <div className="flex h-16 shrink-0 items-center justify-between px-5">
        <Link
          href="/dashboard"
          onClick={onClose}
          className="flex items-center gap-3 rounded-lg"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white shadow-sm">
            <ChefHat size={19} aria-hidden />
          </div>
          <div className="leading-tight">
            <p className="text-sm font-bold tracking-tight text-slate-900">
              Kitchen Copilot
            </p>
            <p className="text-xs text-slate-500">Mess management</p>
          </div>
        </Link>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close navigation"
          className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 lg:hidden"
        >
          <X size={18} />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pt-2 pb-4">
        {visibleGroups.map((group) => (
          <div key={group.label} className="mt-5 first:mt-2">
            <p className="mb-1.5 px-3 text-[11px] font-semibold tracking-wider text-slate-500 uppercase">
              {group.label}
            </p>

            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = isActivePath(pathname, item.href);

                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onClose}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "group relative flex h-9 items-center gap-3 rounded-lg px-3 text-sm transition-colors",
                        active
                          ? "bg-brand-50 font-semibold text-brand-700"
                          : "font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                      )}
                    >
                      {active && (
                        <span
                          aria-hidden
                          className="absolute top-2 bottom-2 -left-3 w-[3px] rounded-r-full bg-brand-500"
                        />
                      )}
                      <Icon
                        size={18}
                        aria-hidden
                        className={cn(
                          "shrink-0",
                          active
                            ? "text-brand-600"
                            : "text-slate-400 group-hover:text-slate-600"
                        )}
                      />
                      <span className="truncate">{item.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="shrink-0 border-t border-slate-200 p-3">
        <div className="flex items-center gap-3 rounded-lg p-2">
          <div
            aria-hidden
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-bold text-brand-700 ring-1 ring-brand-100"
          >
            {initials(displayName)}
          </div>

          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-slate-900">
              {displayName}
            </p>
            <p className="truncate text-xs text-slate-500">
              {formatRole(user.role)}
            </p>
          </div>

          <button
            type="button"
            onClick={() => void signOut()}
            disabled={signingOut}
            aria-label="Sign out"
            title="Sign out"
            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-700 disabled:opacity-50"
          >
            {signingOut ? (
              <Loader2 size={17} className="animate-spin" />
            ) : (
              <LogOut size={17} />
            )}
          </button>
        </div>
      </div>
    </aside>
  );
}
