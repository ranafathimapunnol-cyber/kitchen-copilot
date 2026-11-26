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
  accent = SERIES.coffee,
}: Props) {
  const hasDelta = delta != null && Number.isFinite(delta);
  const flat = hasDelta && Math.abs(delta) < 0.5;
  const rising = hasDelta && delta > 0;

  const good = rising === upIsGood;
  const DeltaIcon = flat ? Minus : rising ? TrendingUp : TrendingDown;
  const deltaColor = flat ? INK.muted : good ? INK.positive : INK.negative;

  return (
    <div className="group min-w-0 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card transition-[box-shadow,transform] duration-300 hover:-translate-y-0.5 hover:shadow-raised">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium text-slate-500">{label}</p>

        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
          style={{ background: `${accent}14`, color: accent }}
        >
          <Icon size={16} aria-hidden />
        </div>
      </div>

      {/* Proportional figures; tabular-nums would read loose at this size. */}
      <p className="font-display mt-3 text-[1.9rem] leading-none font-medium wrap-break-word text-slate-900">
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
