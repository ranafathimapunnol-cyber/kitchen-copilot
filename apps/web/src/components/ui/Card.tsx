import type { ElementType, ReactNode } from "react";

import { cn } from "./cn";

export function Card({
  children,
  className,
  as: Tag = "section",
  ...data
}: {
  children: ReactNode;
  className?: string;
  as?: ElementType;
  /** data-* attributes are passed through (used by tests and analytics). */
  [key: `data-${string}`]: string | boolean | undefined;
}) {
  return (
    <Tag
      {...data}
      className={cn(
        "min-w-0 rounded-2xl border border-slate-200/80 bg-white shadow-card",
        className
      )}
    >
      {children}
    </Tag>
  );
}

export function CardHeader({
  title,
  subtitle,
  icon: Icon,
  iconTone = "neutral",
  action,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: ElementType;
  iconTone?: "neutral" | "brand" | "accent";
  action?: ReactNode;
  className?: string;
}) {
  const tone = {
    neutral: "bg-sand/60 text-brand-700",
    brand: "bg-brand-50 text-brand-600",
    accent: "bg-accent-50 text-accent-500",
  }[iconTone];

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 sm:px-6",
        className
      )}
    >
      <div className="flex min-w-0 flex-1 basis-56 items-center gap-3">
        {Icon && (
          <div
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl",
              tone
            )}
          >
            <Icon size={16} aria-hidden />
          </div>
        )}

        <div className="min-w-0">
          <h2 className="truncate text-[15px] font-semibold tracking-[-0.005em] text-slate-900">
            {title}
          </h2>
          {subtitle && (
            <p className="mt-0.5 truncate text-xs text-slate-500">{subtitle}</p>
          )}
        </div>
      </div>

      {action}
    </div>
  );
}

export function CardBody({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("p-5 sm:p-6", className)}>{children}</div>;
}
