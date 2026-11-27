"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ChefHat,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  X,
} from "lucide-react";

import { canAccessPath } from "@/lib/auth/permissions";
import { NAV_GROUPS, isActivePath, type NavGroup } from "@/lib/navigation";
import { cn } from "@/components/ui/cn";

type SidebarProps = {
  role: string;
  permissions: string[];
  mobileOpen: boolean;
  /** Desktop only: icons-only rail. The mobile drawer is always full. */
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onClose: () => void;
};

/**
 * Visibility is decided only by canAccessPath, exactly as before; grouping,
 * collapsing and the rail are presentation. Groups with nothing visible are
 * dropped. An entry whose page is not allowed may offer an alternate page
 * the user is allowed to open (a counter who may record but not view counts).
 */
export function visibleNavGroups(role: string, permissions: string[]): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.flatMap((item) => {
      if (canAccessPath(role, item.href, permissions)) return [item];
      const alternate = item.alternate;
      return alternate && canAccessPath(role, alternate.href, permissions)
        ? [{ ...item, ...alternate }]
        : [];
    }),
  })).filter((group) => group.items.length > 0);
}

export default function Sidebar({
  role,
  permissions,
  mobileOpen,
  collapsed,
  onToggleCollapsed,
  onClose,
}: SidebarProps) {
  const pathname = usePathname();
  const groups = visibleNavGroups(role, permissions);

  // Groups the person has folded away. The group holding the current page
  // always shows, so the active entry is never hidden.
  const [folded, setFolded] = useState<Set<string>>(new Set());
  const toggleGroup = (label: string) =>
    setFolded((previous) => {
      const next = new Set(previous);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });

  return (
    <aside
      id="app-sidebar"
      aria-label="Main navigation"
      className={cn(
        "fixed inset-y-0 left-0 z-50 flex w-[17.5rem] flex-col border-r border-slate-200/70 bg-sidebar transition-[transform,visibility,width] duration-300 ease-out lg:visible lg:translate-x-0 print:hidden",
        collapsed ? "lg:w-[76px]" : "lg:w-[17rem]",
        mobileOpen
          ? "visible translate-x-0 shadow-overlay"
          : "invisible -translate-x-full"
      )}
    >
      {/* Logo */}
      <div
        className={cn(
          "flex h-[68px] shrink-0 items-center justify-between gap-2 px-5",
          collapsed && "lg:justify-center lg:px-0"
        )}
      >
        <Link
          href="/dashboard"
          onClick={onClose}
          className="flex min-w-0 items-center gap-3 rounded-xl"
          aria-label="Kitchen Copilot home"
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-[0_6px_16px_-6px_rgb(111_89_64/0.6)]">
            <ChefHat size={20} aria-hidden />
          </span>
          <span className={cn("min-w-0 leading-tight", collapsed && "lg:hidden")}>
            <span className="font-display block truncate text-[17px] font-medium text-slate-900">
              Kitchen Copilot
            </span>
            <span className="block text-[11px] tracking-[0.12em] text-slate-500 uppercase">
              Mess management
            </span>
          </span>
        </Link>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close navigation"
          className="rounded-lg p-2 text-slate-500 hover:bg-brand-50 hover:text-slate-900 lg:hidden"
        >
          <X size={18} />
        </button>
      </div>

      <div className="mx-5 h-px bg-gradient-to-r from-transparent via-slate-200 to-transparent" />

      {/* Navigation */}
      <nav className="flex-1 overflow-x-hidden overflow-y-auto px-3 pt-3 pb-4">
        {groups.map((group) => {
          const holdsActive = group.items.some((item) => isActivePath(pathname, item.href));
          const open = holdsActive || !folded.has(group.label);
          const listId = `nav-${group.label.replace(/\W+/g, "-").toLowerCase()}`;

          return (
            <div key={group.label} className="mt-4 first:mt-1">
              <button
                type="button"
                onClick={() => !holdsActive && toggleGroup(group.label)}
                aria-expanded={open}
                aria-controls={listId}
                className={cn(
                  "group/heading flex w-full items-center justify-between rounded-md px-3 py-1 text-[10.5px] font-semibold tracking-[0.14em] text-slate-500 uppercase transition-colors hover:text-slate-700",
                  collapsed && "lg:hidden",
                  holdsActive && "cursor-default hover:text-slate-500"
                )}
              >
                {group.label}
                {!holdsActive && (
                  <ChevronDown
                    size={13}
                    aria-hidden
                    className={cn(
                      "opacity-0 transition-[transform,opacity] duration-200 group-hover/heading:opacity-100 group-focus-visible/heading:opacity-100",
                      !open && "-rotate-90 opacity-100"
                    )}
                  />
                )}
              </button>
              {collapsed && (
                <div aria-hidden className="mx-auto my-2 hidden h-px w-8 bg-slate-200 first:hidden lg:block" />
              )}

              <ul
                id={listId}
                className={cn(
                  "mt-1 space-y-0.5",
                  !open && "hidden",
                  // The rail always lists every entry.
                  collapsed && "lg:block"
                )}
              >
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = isActivePath(pathname, item.href);

                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onClose}
                        aria-current={active ? "page" : undefined}
                        title={collapsed ? item.label : undefined}
                        className={cn(
                          "group relative flex h-9 items-center gap-3 rounded-[10px] px-3 text-[13.5px] transition-[background-color,color,box-shadow] duration-200",
                          collapsed && "lg:mx-auto lg:h-10 lg:w-10 lg:justify-center lg:px-0",
                          active
                            ? "bg-white font-semibold text-slate-900 shadow-[0_1px_2px_rgb(56_45_37/0.06),0_0_0_1px_rgb(229_218_200/0.9)]"
                            : "font-medium text-slate-600 hover:bg-sand/45 hover:text-slate-900"
                        )}
                      >
                        {active && (
                          <span
                            aria-hidden
                            className={cn(
                              "absolute top-2 bottom-2 -left-3 w-[3px] rounded-r-full bg-brand-600",
                              collapsed && "lg:hidden"
                            )}
                          />
                        )}
                        <Icon
                          size={17}
                          aria-hidden
                          strokeWidth={active ? 2.1 : 1.8}
                          className={cn(
                            "shrink-0 transition-colors",
                            active
                              ? "text-brand-700"
                              : "text-slate-400 group-hover:text-brand-700"
                          )}
                        />
                        <span className={cn("truncate", collapsed && "lg:sr-only")}>
                          {item.label}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      {/* Collapse control (desktop) */}
      <div className="hidden shrink-0 border-t border-slate-200/70 p-3 lg:block">
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-controls="app-sidebar"
          aria-expanded={!collapsed}
          className={cn(
            "flex h-9 w-full items-center gap-2.5 rounded-[10px] px-3 text-[13px] font-medium text-slate-500 transition-colors hover:bg-sand/45 hover:text-slate-900",
            collapsed && "justify-center px-0"
          )}
        >
          {collapsed ? <ChevronsRight size={17} aria-hidden /> : <ChevronsLeft size={17} aria-hidden />}
          {!collapsed && "Collapse"}
        </button>
      </div>
    </aside>
  );
}
