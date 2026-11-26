import type { ElementType, ReactNode } from "react";

type Props = {
  title: string;
  description?: ReactNode;
  /** Section the page belongs to, shown above the title. */
  eyebrow?: string;
  icon?: ElementType;
  /** Buttons, right-aligned on wide screens and wrapped below on narrow. */
  actions?: ReactNode;
  /** A line of chips or metadata under the description. */
  meta?: ReactNode;
};

export default function PageHeader({
  title,
  description,
  eyebrow,
  icon: Icon,
  actions,
  meta,
}: Props) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex min-w-0 items-start gap-4">
        {Icon && (
          <div className="hidden h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-brand-100 bg-brand-50 text-brand-600 sm:flex">
            <Icon size={21} aria-hidden />
          </div>
        )}

        <div className="min-w-0">
          {eyebrow && (
            <p className="mb-1 text-xs font-semibold tracking-wide text-brand-600 uppercase">
              {eyebrow}
            </p>
          )}

          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            {title}
          </h1>

          {description && (
            <p className="mt-1 max-w-2xl text-sm text-slate-500">
              {description}
            </p>
          )}

          {meta && (
            <div className="mt-3 flex flex-wrap items-center gap-2">{meta}</div>
          )}
        </div>
      </div>

      {actions && (
        <div className="flex flex-wrap items-center gap-2 sm:shrink-0 sm:justify-end">
          {actions}
        </div>
      )}
    </header>
  );
}
