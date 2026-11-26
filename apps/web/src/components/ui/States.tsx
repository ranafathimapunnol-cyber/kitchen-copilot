import type { ElementType, ReactNode } from "react";
import { AlertCircle, Inbox, Loader2, RefreshCw } from "lucide-react";

import Button from "./Button";
import { cn } from "./cn";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded-lg bg-slate-200/60", className)}
    />
  );
}

/** Placeholder rows shaped like a data table. */
export function TableSkeleton({
  rows = 6,
  columns = 4,
}: {
  rows?: number;
  columns?: number;
}) {
  return (
    <div role="status" aria-label="Loading" className="divide-y divide-slate-100">
      {Array.from({ length: rows }, (_, row) => (
        <div key={row} className="flex items-center gap-6 px-5 py-4">
          {Array.from({ length: columns }, (_, column) => (
            <Skeleton
              key={column}
              className={cn(
                "h-3.5",
                column === 0 ? "w-10" : column === 1 ? "w-40" : "flex-1"
              )}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function Spinner({
  label = "Loading…",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      className={cn(
        "flex items-center justify-center gap-3 text-sm text-slate-500",
        className
      )}
    >
      <Loader2 size={18} className="animate-spin text-brand-500" aria-hidden />
      {label}
    </div>
  );
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  compact = false,
  className,
}: {
  icon?: ElementType;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  /** Smaller treatment for use inside a dashboard panel. */
  compact?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center px-6 text-center",
        compact ? "py-8" : "py-14",
        className
      )}
    >
      <div
        className={cn(
          "flex items-center justify-center rounded-2xl bg-sand/50 text-brand-600",
          compact ? "h-10 w-10" : "h-12 w-12"
        )}
      >
        <Icon size={compact ? 18 : 22} aria-hidden />
      </div>
      <h3
        className={cn(
          "text-sm font-semibold text-slate-900",
          compact ? "mt-3" : "mt-4"
        )}
      >
        {title}
      </h3>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-slate-500">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  retrying = false,
  className,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center px-6 py-14 text-center",
        className
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-600">
        <AlertCircle size={22} aria-hidden />
      </div>
      <h3 className="mt-4 text-sm font-semibold text-slate-900">{title}</h3>
      <p className="mt-1 max-w-md text-sm wrap-break-word text-slate-500">
        {message}
      </p>
      {onRetry && (
        <Button
          variant="secondary"
          size="sm"
          className="mt-5"
          onClick={onRetry}
          loading={retrying}
          icon={<RefreshCw size={14} aria-hidden />}
        >
          Try again
        </Button>
      )}
    </div>
  );
}
