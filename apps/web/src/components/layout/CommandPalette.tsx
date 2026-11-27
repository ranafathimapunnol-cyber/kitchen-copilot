"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ElementType } from "react";
import { useRouter } from "next/navigation";
import {
  CalendarRange,
  ClipboardCheck,
  ClipboardList,
  CookingPot,
  CornerDownLeft,
  FileText,
  Palette,
  PackageCheck,
  Search,
  Soup,
  UtensilsCrossed,
} from "lucide-react";

import { canAccessPath } from "@/lib/auth/permissions";
import { THEMES, setTheme, type ThemeId } from "@/lib/theme";
import { visibleNavGroups } from "./Sidebar";
import { cn } from "@/components/ui/cn";

type Command = {
  id: string;
  label: string;
  group: string;
  icon: ElementType;
  hint?: string;
  run: () => void;
};

/** Quick "new …" actions; each is shown only when its page is allowed. */
const CREATE: { label: string; href: string; icon: ElementType }[] = [
  { label: "Record a meal", href: "/dashboard/meals/new", icon: UtensilsCrossed },
  { label: "New supplier bill", href: "/dashboard/supplier-bills/new", icon: FileText },
  { label: "New goods receipt", href: "/dashboard/receipts/new", icon: PackageCheck },
  { label: "New purchase order", href: "/dashboard/purchase-orders/new", icon: ClipboardList },
  { label: "New kitchen issue", href: "/dashboard/kitchen-issues/new", icon: CookingPot },
  { label: "Record a stock count", href: "/dashboard/stock-counts/new", icon: ClipboardCheck },
  { label: "New meal plan", href: "/dashboard/meal-plans/new", icon: CalendarRange },
  { label: "New outsourced order", href: "/dashboard/outsourced-food/new", icon: Soup },
];

/**
 * ⌘K / Ctrl+K: jump to any screen the person may open, start a common
 * task, or switch theme. Visibility follows canAccessPath, exactly like the
 * sidebar; this adds no access of its own.
 */
export default function CommandPalette({
  role,
  permissions,
  open,
  onOpenChange,
}: {
  role: string;
  permissions: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const ref = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  // Global shortcut.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const go = (href: string) => () => { onOpenChange(false); router.push(href); };
    const pages = visibleNavGroups(role, permissions).flatMap((group) =>
      group.items.map((item) => ({
        id: `page:${item.href}`, label: item.label, group: "Go to", hint: group.label, icon: item.icon, run: go(item.href),
      })));
    const create = CREATE.filter((c) => canAccessPath(role, c.href, permissions)).map((c) => ({
      id: `new:${c.href}`, label: c.label, group: "Create", icon: c.icon, run: go(c.href),
    }));
    const themes = THEMES.map((t) => ({
      id: `theme:${t.id}`, label: `Theme: ${t.name}`, hint: t.description, group: "Appearance", icon: Palette,
      run: () => { setTheme(t.id as ThemeId); onOpenChange(false); },
    }));
    return [...pages, ...create, ...themes];
  }, [role, permissions, router, onOpenChange]);

  const needle = query.trim().toLowerCase();
  const shown = needle
    ? commands.filter((c) => `${c.label} ${c.hint ?? ""} ${c.group}`.toLowerCase().includes(needle))
    : commands;
  const current = Math.min(active, Math.max(shown.length - 1, 0));

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") { event.preventDefault(); setActive((i) => Math.min(i + 1, shown.length - 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
    else if (event.key === "Enter" && shown[current]) { event.preventDefault(); shown[current].run(); }
  };

  useEffect(() => {
    document.getElementById(`cmd-${current}`)?.scrollIntoView({ block: "nearest" });
  }, [current]);

  let lastGroup = "";

  return (
    <dialog
      ref={ref}
      aria-label="Search and jump to"
      onCancel={(event) => { event.preventDefault(); onOpenChange(false); }}
      onClose={() => { setQuery(""); setActive(0); }}
      onClick={(event) => { if (event.target === ref.current) onOpenChange(false); }}
      className="m-auto mt-[12vh] w-[calc(100%-2rem)] max-w-xl overflow-hidden rounded-2xl border border-slate-200/70 bg-white p-0 text-slate-900 shadow-overlay"
    >
      {open && (
        <div onKeyDown={onKeyDown}>
          <div className="flex items-center gap-3 border-b border-slate-100 px-4">
            <Search size={18} aria-hidden className="shrink-0 text-slate-400" />
            <input
              autoFocus
              value={query}
              onChange={(event) => { setQuery(event.target.value); setActive(0); }}
              placeholder="Search screens and actions…"
              aria-label="Search screens and actions"
              aria-controls="cmd-list"
              aria-activedescendant={shown[current] ? `cmd-${current}` : undefined}
              role="combobox"
              aria-expanded="true"
              className="h-14 min-w-0 flex-1 border-0 bg-transparent text-[15px] text-slate-900 placeholder:text-slate-400 focus:outline-none"
            />
            <kbd className="hidden rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-500 sm:block">Esc</kbd>
          </div>
          <ul id="cmd-list" role="listbox" aria-label="Results" className="max-h-[min(60vh,26rem)] overflow-y-auto p-2">
            {shown.length === 0 && <li className="px-3 py-8 text-center text-sm text-slate-500">Nothing matches &ldquo;{query}&rdquo;.</li>}
            {shown.map((c, index) => {
              const heading = c.group !== lastGroup ? c.group : null;
              lastGroup = c.group;
              const Icon = c.icon;
              return (
                <li key={c.id} role="presentation">
                  {heading && <p className="px-3 pt-3 pb-1.5 text-[10.5px] font-semibold tracking-[0.14em] text-slate-500 uppercase">{heading}</p>}
                  <div
                    id={`cmd-${index}`}
                    role="option"
                    aria-selected={index === current}
                    onMouseMove={() => setActive(index)}
                    onClick={c.run}
                    className={cn(
                      "flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors",
                      index === current ? "bg-brand-50 text-slate-900" : "text-slate-700"
                    )}
                  >
                    <span className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                      index === current ? "bg-white text-brand-700 ring-1 ring-brand-200" : "bg-slate-100 text-slate-500")}>
                      <Icon size={16} aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1 truncate font-medium">{c.label}</span>
                    {c.hint && <span className="hidden shrink-0 text-xs text-slate-500 sm:inline">{c.hint}</span>}
                    {index === current && <CornerDownLeft size={14} aria-hidden className="shrink-0 text-slate-400" />}
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-100 bg-slate-50/60 px-4 py-2.5 text-[11px] text-slate-500">
            <span>↑ ↓ to move</span><span>Enter to open</span><span>⌘K or Ctrl K anywhere</span>
          </p>
        </div>
      )}
    </dialog>
  );
}
