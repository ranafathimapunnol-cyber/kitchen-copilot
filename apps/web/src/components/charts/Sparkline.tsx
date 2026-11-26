"use client";

import { useId } from "react";

import { CHROME, LINE_WIDTH, RING_WIDTH } from "./tokens";

type Props = {
  values: number[];
  /** Series colour. The end point wears it; the line is de-emphasised. */
  color: string;
  /** Hidden from assistive tech — the tile's value and delta carry meaning. */
  className?: string;
};

const VB_WIDTH = 120;
const VB_HEIGHT = 32;
const INSET = 3;

/**
 * A stat-tile sparkline: shape only, no axes and no labels. The line sits in
 * a de-emphasised wash of the series hue and the current period carries the
 * accent, so the eye lands on "now" rather than on the whole run.
 */
export default function Sparkline({ values, color, className }: Props) {
  const gradientId = useId();

  if (values.length < 2) return null;

  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;

  const stepX = (VB_WIDTH - INSET * 2) / (values.length - 1);

  const coords = values.map((value, index) => ({
    x: INSET + index * stepX,
    y:
      VB_HEIGHT -
      INSET -
      ((value - min) / span) * (VB_HEIGHT - INSET * 2),
  }));

  const line = coords
    .map((coord, index) => `${index === 0 ? "M" : "L"}${coord.x} ${coord.y}`)
    .join(" ");

  const area =
    `${line} L${coords[coords.length - 1].x} ${VB_HEIGHT}` +
    ` L${coords[0].x} ${VB_HEIGHT} Z`;

  const end = coords[coords.length - 1];

  return (
    <svg
      viewBox={`0 0 ${VB_WIDTH} ${VB_HEIGHT}`}
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.18} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>

      <path d={area} fill={`url(#${gradientId})`} />

      <path
        d={line}
        fill="none"
        stroke={color}
        strokeOpacity={0.45}
        strokeWidth={LINE_WIDTH}
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      <circle
        cx={end.x}
        cy={end.y}
        r={3}
        fill={color}
        stroke={CHROME.surface}
        strokeWidth={RING_WIDTH}
      />
    </svg>
  );
}
