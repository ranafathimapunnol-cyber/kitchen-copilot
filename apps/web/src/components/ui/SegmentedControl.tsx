"use client";

import { cn } from "./cn";

type Option<T extends string> = { value: T; label: string; count?: number };

/** A small single-choice filter, e.g. All / Active / Inactive. */
export default function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (value: T) => void;
  options: Option<T>[];
  /** Accessible name for the group. */
  label: string;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex max-w-full shrink-0 overflow-x-auto rounded-[10px] border border-slate-200/80 bg-slate-100/80 p-0.5"
    >
      {options.map((option) => {
        const active = option.value === value;

        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-3 text-xs font-medium transition-[background-color,color,box-shadow] duration-200",
              active
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            )}
          >
            {option.label}
            {option.count !== undefined && (
              <span className="text-slate-500 tabular-nums">
                {option.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
