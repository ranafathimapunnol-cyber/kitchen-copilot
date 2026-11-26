import type { ReactNode } from "react";

import { cn } from "./cn";

export type BadgeTone = "neutral" | "brand" | "success" | "warning" | "danger";

const tones: Record<BadgeTone, { badge: string; dot: string }> = {
  neutral: {
    badge: "bg-slate-100 text-slate-700 ring-slate-200",
    dot: "bg-slate-400",
  },
  brand: {
    badge: "bg-brand-50 text-brand-700 ring-brand-100",
    dot: "bg-brand-500",
  },
  success: {
    badge: "bg-emerald-50 text-emerald-700 ring-emerald-100",
    dot: "bg-emerald-500",
  },
  warning: {
    badge: "bg-amber-50 text-amber-700 ring-amber-100",
    dot: "bg-amber-500",
  },
  danger: {
    badge: "bg-red-50 text-red-700 ring-red-100",
    dot: "bg-red-500",
  },
};

export default function Badge({
  children,
  tone = "neutral",
  dot = false,
  className,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  /** A leading dot; the label still carries the meaning. */
  dot?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
        tones[tone].badge,
        className
      )}
    >
      {dot && (
        <span
          aria-hidden
          className={cn("h-1.5 w-1.5 rounded-full", tones[tone].dot)}
        />
      )}
      {children}
    </span>
  );
}

const STATUS_TONES: Record<string, BadgeTone> = {
  ACTIVE: "success",
  COMPLETED: "success",
  ACCEPTED: "success",
  APPROVED: "success",
  RECEIVED: "success",
  PENDING: "warning",
  DRAFT: "warning",
  PARTIAL: "warning",
  PROCESSING: "warning",
  REJECTED: "danger",
  CANCELLED: "danger",
  FAILED: "danger",
  INACTIVE: "neutral",
};

/** "PARTIALLY_RECEIVED" → "Partially Received". */
export function humanize(value?: string | null): string {
  if (!value) return "—";

  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/** Badge for a workflow or record status string from the API. */
export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONES[status.toUpperCase()] ?? "neutral";

  return (
    <Badge tone={tone} dot>
      {humanize(status)}
    </Badge>
  );
}
