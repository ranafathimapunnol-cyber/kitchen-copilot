/**
 * Chart design tokens.
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
  /** Categorical slot 1 — headcount. */
  blue: "#2a78d6",
  /** Categorical slot 2 — waste cost. */
  orange: "#eb6834",
} as const;

export type SeriesHue = (typeof SERIES)[keyof typeof SERIES];

export const CHROME = {
  /** The card surface these charts render on. */
  surface: "#ffffff",
  /** Hairline gridline, one step off surface. */
  grid: "#e1e0d9",
  /** Baseline / axis rule. */
  axis: "#c3c2b7",
} as const;

export const INK = {
  primary: "#0b0b0b",
  secondary: "#52514e",
  /** Axis ticks and labels. */
  muted: "#898781",
  /** Positive delta, when up is good. */
  positive: "#006300",
  /** Negative delta, when up is good. */
  negative: "#d03b3b",
} as const;

/** Area wash opacity — a wash, never a saturated block. */
export const AREA_OPACITY = 0.1;

/** Line weight, in viewBox units. */
export const LINE_WIDTH = 2;

/** End-marker radius. Diameter >= 8px. */
export const MARKER_RADIUS = 4;

/** Surface ring around markers, so they stay legible over the line. */
export const RING_WIDTH = 2;
