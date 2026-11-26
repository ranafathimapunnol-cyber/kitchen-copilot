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
    <thead className="border-b border-slate-200 bg-slate-50/80">
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
        "px-4 py-3 text-xs font-semibold tracking-wide whitespace-nowrap text-slate-500 uppercase first:pl-5 last:pr-5",
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
        "transition-colors hover:bg-slate-50/70",
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
        "px-4 py-3 align-middle text-slate-700 first:pl-5 last:pr-5",
        alignClass[align],
        align === "right" && "tabular-nums",
        className
      )}
    >
      {children}
    </td>
  );
}
