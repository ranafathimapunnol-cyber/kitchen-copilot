import type {
  ReactNode,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";

import { cn } from "./cn";

type Align = "left" | "right" | "center";

const alignClass: Record<Align, string> = {
  left: "text-left",
  right: "text-right",
  center: "text-center",
};

/** Horizontal scroll stays inside the table, never on the page. */
export function Table({
  children,
  className,
  minWidth,
}: {
  children: ReactNode;
  className?: string;
  /** e.g. "640px" — below this the table scrolls instead of squeezing. */
  minWidth?: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table
        className={cn("w-full border-collapse text-sm", className)}
        style={minWidth ? { minWidth } : undefined}
      >
        {children}
      </table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return (
    <thead className="border-b border-slate-200/80 bg-slate-50/70">
      {children}
    </thead>
  );
}

export function TH({
  children,
  align = "left",
  className,
  ...props
}: ThHTMLAttributes<HTMLTableCellElement> & { align?: Align }) {
  return (
    <th
      scope="col"
      {...props}
      className={cn(
        "px-4 py-3 text-[11px] font-semibold tracking-[0.08em] whitespace-nowrap text-slate-500 uppercase first:pl-5 last:pr-5 sm:first:pl-6 sm:last:pr-6",
        alignClass[align],
        className
      )}
    >
      {children}
    </th>
  );
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-slate-100">{children}</tbody>;
}

export function TR({
  children,
  className,
  muted = false,
}: {
  children: ReactNode;
  className?: string;
  /** Inactive rows recede without disappearing. */
  muted?: boolean;
}) {
  return (
    <tr
      className={cn(
        "transition-colors duration-150 hover:bg-brand-50/50",
        muted && "bg-slate-50/40 text-slate-500",
        className
      )}
    >
      {children}
    </tr>
  );
}

export function TD({
  children,
  align = "left",
  className,
  ...props
}: TdHTMLAttributes<HTMLTableCellElement> & { align?: Align }) {
  return (
    <td
      {...props}
      className={cn(
        "px-4 py-3.5 align-middle text-slate-700 first:pl-5 last:pr-5 sm:first:pl-6 sm:last:pr-6",
        alignClass[align],
        align === "right" && "tabular-nums",
        className
      )}
    >
      {children}
    </td>
  );
}

export type SortState = { key: string; direction: "asc" | "desc" } | null;

/**
 * A column header that sorts: first click ascending, second descending,
 * third back to the original order. Announces the order with aria-sort.
 */
export function SortableTH({
  children,
  sortKey,
  sort,
  onSort,
  align = "left",
  className,
}: {
  children: ReactNode;
  sortKey: string;
  sort: SortState;
  onSort: (next: SortState) => void;
  align?: Align;
  className?: string;
}) {
  const active = sort?.key === sortKey;
  const direction = active ? sort.direction : null;
  const next: SortState = !active ? { key: sortKey, direction: "asc" }
    : direction === "asc" ? { key: sortKey, direction: "desc" } : null;

  return (
    <TH
      align={align}
      className={className}
      aria-sort={direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none"}
    >
      <button
        type="button"
        onClick={() => onSort(next)}
        className={cn(
          "group/sort inline-flex items-center gap-1 rounded uppercase transition-colors hover:text-slate-800",
          active && "text-slate-800",
          align === "right" && "flex-row-reverse"
        )}
      >
        {children}
        <span aria-hidden className={cn("text-[10px] leading-none", active ? "text-brand-700" : "text-slate-300 group-hover/sort:text-slate-400")}>
          {direction === "desc" ? "▼" : direction === "asc" ? "▲" : "↕"}
        </span>
      </button>
    </TH>
  );
}

/** Compares two cell texts: numbers numerically, text by locale; "—" last. */
export function compareCells(a: string, b: string, numeric: boolean): number {
  const blankA = a === "—" || a === "";
  const blankB = b === "—" || b === "";
  if (blankA || blankB) return blankA === blankB ? 0 : blankA ? 1 : -1;
  if (numeric) {
    const x = Number(a.replace(/[^0-9.-]/g, ""));
    const y = Number(b.replace(/[^0-9.-]/g, ""));
    if (Number.isFinite(x) && Number.isFinite(y)) return x - y;
  }
  return a.localeCompare(b, "en-IN", { numeric: true, sensitivity: "base" });
}
