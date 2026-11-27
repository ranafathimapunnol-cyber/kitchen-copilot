"use client";

import { useState } from "react";

import { INK } from "./tokens";

export type BarRow = {
  id: string | number;
  label: string;
  /** Secondary line under the label — a date, a supplier, a unit. */
  meta?: string;
  value: number;
  /** Rendered at the bar tip. */
  display: string;
  /** Optional trailing slot, e.g. a status badge. */
  trailing?: React.ReactNode;
};

type Props = {
  rows: BarRow[];
  color: string;
  /** Names the measure, for the accessible description. */
  measureLabel: string;
};

/**
 * A bar list: table-like rows carrying a proportional bar, so magnitude is
 * visible at a glance without giving up the per-row detail a table shows.
 *
 * Each bar is its own hit target (no crosshair — that is for continuous x),
 * grows from a single baseline, and keeps its 4px rounded data-end with a
 * square start. Bars are capped well under 24px and the track's leftover is
 * left as air rather than filled.
 */
export default function BarList({ rows, color, measureLabel }: Props) {
  const [activeId, setActiveId] = useState<string | number | null>(null);

  if (!rows.length) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
        Nothing recorded yet.
      </div>
    );
  }

  const max = Math.max(...rows.map((row) => row.value), 1);

  return (
    <ul className="space-y-1">
      {rows.map((row) => {
        const share = Math.max(1.5, (row.value / max) * 100);
        const isActive = activeId === row.id;

        return (
          <li key={row.id}>
            {/* The row is the hit target, so it extends past the painted bar. */}
            <div
              className="rounded-lg px-2 py-2.5 transition-colors"
              style={{ background: isActive ? "var(--color-slate-50)" : "transparent" }}
              onPointerEnter={() => setActiveId(row.id)}
              onPointerLeave={() => setActiveId(null)}
              onFocus={() => setActiveId(row.id)}
              onBlur={() => setActiveId(null)}
              tabIndex={0}
              aria-label={`${row.label}. ${measureLabel}: ${row.display}${
                row.meta ? `. ${row.meta}` : ""
              }`}
            >
              <div className="flex items-baseline justify-between gap-3">
                <p
                  className="min-w-0 truncate text-sm font-semibold"
                  style={{ color: INK.primary }}
                >
                  {row.label}
                </p>

                <div className="flex shrink-0 items-center gap-2.5">
                  <span
                    className="text-sm font-semibold"
                    style={{
                      color: INK.primary,
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {row.display}
                  </span>
                  {row.trailing}
                </div>
              </div>

              <div className="mt-2 flex items-center gap-3">
                {/* Track left mostly as air; the bar is the only ink. */}
                <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-sm bg-slate-100">
                  <div
                    className="h-full transition-all duration-500"
                    style={{
                      width: `${share}%`,
                      background: color,
                      opacity: isActive ? 1 : 0.85,
                      // Square at the baseline, 4px rounded data-end.
                      borderRadius: "0 4px 4px 0",
                    }}
                  />
                </div>

                {row.meta && (
                  <span
                    className="shrink-0 text-[11px]"
                    style={{ color: INK.secondary }}
                  >
                    {row.meta}
                  </span>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
