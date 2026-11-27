/**
 * Chart design tokens. Values are CSS variables, so charts follow the
 * selected colour theme (each theme sets --color-chart-* in globals.css).
 *
 *
 * The two series hues are a validated categorical pair: on the white card
 * surface these clear the lightness band, the chroma floor, CVD separation
 * (worst adjacent dE 24.7 protan), the normal-vision floor (dE 33.6) and the
 * 3:1 contrast gate. Do not substitute hues without re-validating — a hue
 * that looks fine can still be invisible to a colourblind reader.
 *
 * Ink and chrome values are deliberately recessive: the data is the only
 * thing allowed to be loud.
 */

export const SERIES = {
  /** Categorical slot 1 — coffee (the brand's primary). 4.57:1 on cream. */
  coffee: "var(--color-chart-1)",
  /** Categorical slot 2 — dusk blue, opposite coffee on the blue–yellow
   *  axis so the pair stays apart for colour-blind readers. 5.1:1 on cream. */
  dusk: "var(--color-chart-2)",
  /** Older slot names, kept so existing charts follow the theme. */
  blue: "var(--color-chart-1)",
  orange: "var(--color-chart-2)",
} as const;

export type SeriesHue = (typeof SERIES)[keyof typeof SERIES];

export const CHROME = {
  /** The card surface these charts render on. */
  surface: "var(--color-white)",
  /** Hairline gridline, one step off surface. */
  grid: "var(--color-chart-grid)",
  /** Baseline / axis rule. */
  axis: "var(--color-chart-axis)",
} as const;

export const INK = {
  primary: "var(--color-slate-900)",
  secondary: "var(--color-slate-600)",
  /** Axis ticks and labels. */
  muted: "var(--color-slate-500)",
  /** Positive delta, when up is good. */
  positive: "var(--color-emerald-700)",
  /** Negative delta, when up is good. */
  negative: "var(--color-red-600)",
} as const;

/** Area wash opacity — a wash, never a saturated block. */
export const AREA_OPACITY = 0.1;

/** Line weight, in viewBox units. */
export const LINE_WIDTH = 2;

/** End-marker radius. Diameter >= 8px. */
export const MARKER_RADIUS = 4;

/** Surface ring around markers, so they stay legible over the line. */
export const RING_WIDTH = 2;
