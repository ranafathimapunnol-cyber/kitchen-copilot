"use client";

import { useId, useMemo, useRef, useState } from "react";
import { Table2 } from "lucide-react";

import {
  AREA_OPACITY,
  CHROME,
  INK,
  LINE_WIDTH,
  MARKER_RADIUS,
  RING_WIDTH,
} from "./tokens";

export type AreaPoint = {
  /** ISO date, used for the x label and the tooltip heading. */
  date: string;
  value: number;
};

type Props = {
  points: AreaPoint[];
  /** Series colour. One of the validated hues in `tokens.ts`. */
  color: string;
  /** Names what is plotted, so a single series needs no legend. */
  seriesLabel: string;
  /** Formats a value for the tooltip, the end label and the axis. */
  formatValue: (value: number) => string;
  /** Shorter form for axis ticks, when the full form is too wide. */
  formatTick?: (value: number) => string;
  /** Dims the plot while new data loads, holding the previous frame. */
  stale?: boolean;
};

const VB_WIDTH = 720;
const VB_HEIGHT = 240;
const PAD_LEFT = 52;
const PAD_RIGHT = 18;
const PAD_TOP = 18;
const PAD_BOTTOM = 30;

const PLOT_LEFT = PAD_LEFT;
const PLOT_RIGHT = VB_WIDTH - PAD_RIGHT;
const PLOT_TOP = PAD_TOP;
const PLOT_BOTTOM = VB_HEIGHT - PAD_BOTTOM;
const PLOT_WIDTH = PLOT_RIGHT - PLOT_LEFT;
const PLOT_HEIGHT = PLOT_BOTTOM - PLOT_TOP;

/** Rounds an axis maximum up to a clean number with a clean step. */
function niceScale(max: number): { max: number; ticks: number[] } {
  if (max <= 0) return { max: 1, ticks: [0, 1] };

  const target = 4;
  const rough = max / target;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / magnitude;

  let step = magnitude;
  if (normalized > 5) step = magnitude * 10;
  else if (normalized > 2.5) step = magnitude * 5;
  else if (normalized > 2) step = magnitude * 2.5;
  else if (normalized > 1) step = magnitude * 2;

  const niceMax = Math.ceil(max / step) * step;
  const ticks: number[] = [];

  for (let value = 0; value <= niceMax + step / 2; value += step) {
    ticks.push(Number(value.toFixed(6)));
  }

  return { max: niceMax, ticks };
}

function shortDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);

  if (Number.isNaN(date.getTime())) return iso;

  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
  });
}

function longDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);

  if (Number.isNaN(date.getTime())) return iso;

  return date.toLocaleDateString("en-IN", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  });
}

export default function AreaChart({
  points,
  color,
  seriesLabel,
  formatValue,
  formatTick,
  stale = false,
}: Props) {
  const gradientId = useId();
  const plotRef = useRef<SVGSVGElement | null>(null);

  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);

  const scale = useMemo(() => {
    const values = points.map((point) => point.value);
    return niceScale(values.length ? Math.max(...values) : 0);
  }, [points]);

  const geometry = useMemo(() => {
    if (!points.length) return null;

    const stepX =
      points.length === 1 ? 0 : PLOT_WIDTH / (points.length - 1);

    const coords = points.map((point, index) => {
      const x =
        points.length === 1
          ? PLOT_LEFT + PLOT_WIDTH / 2
          : PLOT_LEFT + index * stepX;

      const ratio = scale.max === 0 ? 0 : point.value / scale.max;
      const y = PLOT_BOTTOM - ratio * PLOT_HEIGHT;

      return { x, y };
    });

    const line = coords
      .map((coord, index) => `${index === 0 ? "M" : "L"}${coord.x} ${coord.y}`)
      .join(" ");

    const area =
      `${line} L${coords[coords.length - 1].x} ${PLOT_BOTTOM}` +
      ` L${coords[0].x} ${PLOT_BOTTOM} Z`;

    return { coords, line, area };
  }, [points, scale.max]);

  // The crosshair finds the X: the pointer only has to be nearest, never
  // dead-centre on a 2px line.
  function handlePointerMove(event: React.PointerEvent<SVGSVGElement>) {
    if (!points.length) return;

    const rect = plotRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;

    // Map client pixels back through the viewBox scaling.
    const vbX = ((event.clientX - rect.left) / rect.width) * VB_WIDTH;
    const ratio = (vbX - PLOT_LEFT) / PLOT_WIDTH;
    const index = Math.round(ratio * (points.length - 1));

    setActiveIndex(Math.min(points.length - 1, Math.max(0, index)));
  }

  function handleKeyDown(event: React.KeyboardEvent<SVGSVGElement>) {
    if (!points.length) return;

    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();

      const direction = event.key === "ArrowRight" ? 1 : -1;
      const current = activeIndex ?? (direction > 0 ? -1 : points.length);
      const next = Math.min(
        points.length - 1,
        Math.max(0, current + direction),
      );

      setActiveIndex(next);
    }

    if (event.key === "Escape") setActiveIndex(null);
  }

  if (!points.length) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-500">
        No trend data available yet.
      </div>
    );
  }

  const tick = formatTick ?? formatValue;
  const active = activeIndex === null ? null : points[activeIndex];
  const activeCoord =
    activeIndex === null || !geometry ? null : geometry.coords[activeIndex];

  const last = points[points.length - 1];
  const lastCoord = geometry?.coords[geometry.coords.length - 1];
  const summary = `${seriesLabel}. ${points
    .map((point) => `${longDate(point.date)}: ${formatValue(point.value)}`)
    .join(". ")}`;

  return (
    <div className="relative">
      <svg
        ref={plotRef}
        viewBox={`0 0 ${VB_WIDTH} ${VB_HEIGHT}`}
        className="w-full touch-none outline-none transition-opacity"
        style={{ opacity: stale ? 0.45 : 1 }}
        role="img"
        aria-label={summary}
        tabIndex={0}
        onPointerMove={handlePointerMove}
        onPointerLeave={() => setActiveIndex(null)}
        onBlur={() => setActiveIndex(null)}
        onKeyDown={handleKeyDown}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={AREA_OPACITY * 2} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>

        {/* Gridlines — hairline, solid, recessive. */}
        {scale.ticks.map((value) => {
          const ratio = scale.max === 0 ? 0 : value / scale.max;
          const y = PLOT_BOTTOM - ratio * PLOT_HEIGHT;

          return (
            <g key={value}>
              <line
                x1={PLOT_LEFT}
                y1={y}
                x2={PLOT_RIGHT}
                y2={y}
                stroke={value === 0 ? CHROME.axis : CHROME.grid}
                strokeWidth={1}
              />
              <text
                x={PLOT_LEFT - 10}
                y={y + 4}
                textAnchor="end"
                fontSize={11}
                fill={INK.muted}
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {tick(value)}
              </text>
            </g>
          );
        })}

        {/* X axis labels. First and last always; inner ones as room allows. */}
        {points.map((point, index) => {
          const coord = geometry?.coords[index];
          if (!coord) return null;

          const stride = Math.ceil(points.length / 7);
          const edge = index === 0 || index === points.length - 1;

          if (!edge && index % stride !== 0) return null;

          return (
            <text
              key={`${point.date}-${index}`}
              x={coord.x}
              y={PLOT_BOTTOM + 20}
              textAnchor={
                index === 0
                  ? "start"
                  : index === points.length - 1
                    ? "end"
                    : "middle"
              }
              fontSize={11}
              fill={INK.muted}
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {shortDate(point.date)}
            </text>
          );
        })}

        {geometry && (
          <>
            <path d={geometry.area} fill={`url(#${gradientId})`} />
            <path
              d={geometry.line}
              fill="none"
              stroke={color}
              strokeWidth={LINE_WIDTH}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </>
        )}

        {/* Crosshair — a hairline that snaps to the nearest data position. */}
        {activeCoord && (
          <line
            x1={activeCoord.x}
            y1={PLOT_TOP}
            x2={activeCoord.x}
            y2={PLOT_BOTTOM}
            stroke={CHROME.axis}
            strokeWidth={1}
          />
        )}

        {/* End marker, with a surface ring so it reads over the line. */}
        {lastCoord && (
          <circle
            cx={lastCoord.x}
            cy={lastCoord.y}
            r={MARKER_RADIUS}
            fill={color}
            stroke={CHROME.surface}
            strokeWidth={RING_WIDTH}
          />
        )}

        {activeCoord && (
          <circle
            cx={activeCoord.x}
            cy={activeCoord.y}
            r={MARKER_RADIUS + 1}
            fill={color}
            stroke={CHROME.surface}
            strokeWidth={RING_WIDTH}
          />
        )}
      </svg>

      {/* The one direct label: the endpoint. Never a number on every point. */}
      {lastCoord && activeIndex === null && (
        <div
          className="pointer-events-none absolute flex -translate-y-1/2 items-center gap-1.5"
          style={{
            left: `${((lastCoord.x + 10) / VB_WIDTH) * 100}%`,
            top: `${(lastCoord.y / VB_HEIGHT) * 100}%`,
          }}
        >
          <span
            className="text-xs font-semibold"
            style={{ color: INK.primary }}
          >
            {formatValue(last.value)}
          </span>
        </div>
      )}

      {/* Tooltip: the value leads, the series name follows. */}
      {active && activeCoord && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-lg"
          style={{
            left: `${Math.min(88, Math.max(12, (activeCoord.x / VB_WIDTH) * 100))}%`,
            top: `${(activeCoord.y / VB_HEIGHT) * 100 - 4}%`,
          }}
        >
          <p
            className="text-[11px] font-medium"
            style={{ color: INK.muted }}
          >
            {longDate(active.date)}
          </p>

          <p className="mt-1 flex items-center gap-2">
            <span
              aria-hidden
              className="inline-block h-0.5 w-3 rounded-full"
              style={{ background: color }}
            />
            <span
              className="text-sm font-bold"
              style={{ color: INK.primary }}
            >
              {formatValue(active.value)}
            </span>
          </p>

          <p className="mt-0.5 text-[11px]" style={{ color: INK.secondary }}>
            {seriesLabel}
          </p>
        </div>
      )}

      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={() => setShowTable((value) => !value)}
          aria-expanded={showTable}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium text-slate-500 transition hover:bg-slate-50 hover:text-slate-700"
        >
          <Table2 size={13} />
          {showTable ? "Hide values" : "View values"}
        </button>
      </div>

      {/* Table view — so no value is reachable only by hovering. */}
      {showTable && (
        <table className="mt-1 w-full text-left text-xs">
          <caption className="sr-only">{seriesLabel}</caption>
          <thead>
            <tr style={{ color: INK.muted }}>
              <th scope="col" className="py-1.5 font-medium">
                Date
              </th>
              <th scope="col" className="py-1.5 text-right font-medium">
                {seriesLabel}
              </th>
            </tr>
          </thead>
          <tbody>
            {points.map((point, index) => (
              <tr
                key={`${point.date}-${index}`}
                className="border-t border-slate-100"
              >
                <td className="py-1.5" style={{ color: INK.secondary }}>
                  {longDate(point.date)}
                </td>
                <td
                  className="py-1.5 text-right font-medium"
                  style={{
                    color: INK.primary,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {formatValue(point.value)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
