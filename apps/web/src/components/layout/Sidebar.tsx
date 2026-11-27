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
import { useCampusMedia } from "@/lib/campusMedia";
import { NAV_GROUPS, isActivePath, type NavGroup } from "@/lib/navigation";
import { cn } from "@/components/ui/cn";

type SidebarProps = {
  role: string;
  permissions: string[];
  mobileOpen: boolean;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onClose: () => void;
};

export function visibleNavGroups(
  role: string,
  permissions: string[],
): NavGroup[] {
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
  const { logo: campusLogo } = useCampusMedia();

  const [folded, setFolded] = useState<Set<string>>(new Set());

  const toggleGroup = (label: string) => {
    setFolded((previous) => {
      const next = new Set(previous);

      if (next.has(label)) next.delete(label);
      else next.add(label);

      return next;
    });
  };

  return (
    <aside
      id="app-sidebar"
      aria-label="Main navigation"
      className={cn(
        "fixed inset-y-0 left-0 z-50 flex w-[17rem] flex-col",
        "border-r border-slate-200 bg-white",
        "transition-[transform,visibility,width] duration-300 ease-out",
        "lg:visible lg:translate-x-0",
        collapsed ? "lg:w-[76px]" : "lg:w-[17rem]",
        mobileOpen
          ? "visible translate-x-0 shadow-overlay"
          : "invisible -translate-x-full",
        "print:hidden",
      )}
    >
      {/* Brand */}
      <div
        className={cn(
          "flex h-[76px] shrink-0 items-center justify-between px-5",
          collapsed && "lg:justify-center lg:px-0",
        )}
      >
        <Link
          href="/dashboard"
          onClick={onClose}
          aria-label="Kitchen Copilot home"
          className="flex min-w-0 items-center gap-3"
        >
          {campusLogo ? (
            <span className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-white">
              {/* eslint-disable-next-line @next/next/no-img-element -- authenticated API image */}
              <img src={campusLogo} alt="Campus logo" className="h-full w-full object-contain p-1" data-campus-logo />
            </span>
          ) : (
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-brand-200">
              <ChefHat size={21} strokeWidth={2} aria-hidden />
            </span>
          )}

          <span
            className={cn(
              "min-w-0 leading-tight",
              collapsed && "lg:hidden",
            )}
          >
            <span className="block truncate text-[16px] font-bold tracking-tight text-slate-900">
              Kitchen Copilot
            </span>
            <span className="mt-1 block text-[9px] font-semibold tracking-[0.18em] text-slate-500 uppercase">
              Mess management
            </span>
          </span>
        </Link>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close navigation"
          className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 lg:hidden"
        >
          <X size={18} />
        </button>
      </div>

      <div className="mx-4 h-px bg-slate-200" />

      {/* Navigation */}
      <nav className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-3 pt-5 pb-4">
        {groups.map((group) => {
          const holdsActive = group.items.some((item) =>
            isActivePath(pathname, item.href),
          );

          const open = holdsActive || !folded.has(group.label);

          const listId = `nav-${group.label
            .replace(/\W+/g, "-")
            .toLowerCase()}`;

          return (
            <section key={group.label} className="mb-6 last:mb-0">
              <button
                type="button"
                onClick={() => !holdsActive && toggleGroup(group.label)}
                aria-expanded={open}
                aria-controls={listId}
                className={cn(
                  "mb-2 flex w-full items-center justify-between px-3",
                  "text-[10px] font-bold tracking-[0.16em] text-slate-400 uppercase",
                  "transition-colors hover:text-slate-700",
                  collapsed && "lg:hidden",
                  holdsActive && "cursor-default",
                )}
              >
                <span>{group.label}</span>

                {!holdsActive && (
                  <ChevronDown
                    size={13}
                    aria-hidden
                    className={cn(
                      "transition-transform",
                      !open && "-rotate-90",
                    )}
                  />
                )}
              </button>

              {collapsed && (
                <div
                  aria-hidden
                  className="mx-auto mb-3 hidden h-px w-8 bg-slate-200 lg:block"
                />
              )}

              <ul
                id={listId}
                className={cn(
                  "space-y-1",
                  !open && "hidden",
                  collapsed && "lg:block",
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
                          "group relative flex h-10 items-center gap-3",
                          "rounded-lg px-3 text-[13px]",
                          "transition-colors duration-150",
                          collapsed &&
                            "lg:mx-auto lg:h-10 lg:w-10 lg:justify-center lg:px-0",
                          active
                            ? "bg-brand-100 font-semibold text-slate-950"
                            : "font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-950",
                        )}
                      >
                        {active && (
                          <span
                            aria-hidden
                            className={cn(
                              "absolute top-2 bottom-2 left-0 w-[3px] rounded-r-full bg-brand-600",
                              collapsed && "lg:hidden",
                            )}
                          />
                        )}

                        <Icon
                          size={18}
                          strokeWidth={active ? 2.2 : 1.8}
                          aria-hidden
                          className={cn(
                            "shrink-0",
                            active
                              ? "text-slate-900"
                              : "text-slate-400 group-hover:text-slate-700",
                          )}
                        />

                        <span
                          className={cn(
                            "min-w-0 truncate",
                            collapsed && "lg:sr-only",
                          )}
                        >
                          {item.label}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </nav>

      {/* Desktop collapse control */}
      <div className="hidden shrink-0 border-t border-slate-200 p-3 lg:block">
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-controls="app-sidebar"
          aria-expanded={!collapsed}
          className={cn(
            "flex h-10 w-full items-center gap-3 rounded-lg px-3",
            "text-[12px] font-semibold text-slate-500",
            "transition-colors hover:bg-slate-100 hover:text-slate-900",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? (
            <ChevronsRight size={18} aria-hidden />
          ) : (
            <ChevronsLeft size={18} aria-hidden />
          )}

          {!collapsed && <span>Collapse sidebar</span>}
        </button>
      </div>
    </aside>
  );
}
