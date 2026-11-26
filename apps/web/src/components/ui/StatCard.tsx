"use client";

import type { ElementType } from "react";
import { Minus, TrendingDown, TrendingUp } from "lucide-react";

import Sparkline from "@/components/charts/Sparkline";
import { INK, SERIES } from "@/components/charts/tokens";

type Props = {
  label: string;
  value: string;
  description?: string;
  icon: ElementType;
  /** Recent values, oldest first, for the sparkline. */
  trend?: number[];
  /** Percent change against the previous period. */
  delta?: number | null;
  /** What the delta is measured against, e.g. "vs yesterday". */
  deltaLabel?: string;
  /**
   * Decides the delta's colour. False for measures where a rise is bad
   * (waste cost), so an increase reads red rather than green.
   */
  upIsGood?: boolean;
  accent?: string;
};

/**
 * Stat card: label · value · delta · sparkline. Direction is carried by an
 * icon and a signed number as well as by colour, never by colour alone.
 */
export default function StatCard({
  label,
  value,
  description,
  icon: Icon,
  trend,
  delta,
  deltaLabel = "vs yesterday",
  upIsGood = true,
  accent = SERIES.blue,
}: Props) {
  const hasDelta = delta != null && Number.isFinite(delta);
  const flat = hasDelta && Math.abs(delta) < 0.5;
  const rising = hasDelta && delta > 0;

  const good = rising === upIsGood;
  const DeltaIcon = flat ? Minus : rising ? TrendingUp : TrendingDown;
  const deltaColor = flat ? INK.muted : good ? INK.positive : INK.negative;

  return (
    <div className="min-w-0 rounded-xl border border-slate-200 bg-white p-5 shadow-card transition-shadow hover:shadow-raised">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-slate-500">{label}</p>

        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
          style={{ background: `${accent}14`, color: accent }}
        >
          <Icon size={16} aria-hidden />
        </div>
      </div>

      {/* Proportional figures; tabular-nums would read loose at this size. */}
      <p className="mt-2 text-[1.75rem] leading-tight font-bold tracking-tight wrap-break-word text-slate-900">
        {value}
      </p>

      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="min-w-0">
          {hasDelta && (
            <p
              className="flex items-center gap-1 text-xs font-semibold"
              style={{ color: deltaColor }}
            >
              <DeltaIcon size={13} aria-hidden />
              {flat ? "No change" : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}%`}
              <span className="font-normal text-slate-500">{deltaLabel}</span>
            </p>
          )}

          {description && (
            <p className="mt-1 truncate text-xs text-slate-500">
              {description}
            </p>
          )}
        </div>

        {trend && trend.length > 1 && (
          <Sparkline
            values={trend}
            color={accent}
            className="h-8 w-[88px] shrink-0"
          />
        )}
      </div>
    </div>
  );
}
