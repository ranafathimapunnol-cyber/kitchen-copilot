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
  /** Categorical slot 1 — coffee (the brand's primary). 4.57:1 on cream. */
  coffee: "#8b6f50",
  /** Categorical slot 2 — dusk blue, opposite coffee on the blue–yellow
   *  axis so the pair stays apart for colour-blind readers. 5.1:1 on cream. */
  dusk: "#4f7088",
  /** Older slot names, kept so existing charts follow the theme. */
  blue: "#8b6f50",
  orange: "#4f7088",
} as const;

export type SeriesHue = (typeof SERIES)[keyof typeof SERIES];

export const CHROME = {
  /** The card surface these charts render on. */
  surface: "#fffcf6",
  /** Hairline gridline, one step off surface. */
  grid: "#ebe2d3",
  /** Baseline / axis rule. */
  axis: "#d5c7b1",
} as const;

export const INK = {
  primary: "#382d25",
  secondary: "#5f5246",
  /** Axis ticks and labels. */
  muted: "#8a7d6f",
  /** Positive delta, when up is good. */
  positive: "#33694a",
  /** Negative delta, when up is good. */
  negative: "#a8432f",
} as const;

/** Area wash opacity — a wash, never a saturated block. */
export const AREA_OPACITY = 0.1;

/** Line weight, in viewBox units. */
export const LINE_WIDTH = 2;

/** End-marker radius. Diameter >= 8px. */
export const MARKER_RADIUS = 4;

/** Surface ring around markers, so they stay legible over the line. */
export const RING_WIDTH = 2;
