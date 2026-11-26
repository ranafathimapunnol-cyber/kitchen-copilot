/**
 * Search-as-you-type selection lists (PROPOSAL §5.7; Stage 7 S7-A): the
 * filtering and keyboard-step rules behind SearchSelect. They filter the
 * options a form has already loaded under its own permission; nothing here
 * calls the API.
 *
 * No imports: tested directly with node --test.
 */

export type SearchOption = {
  value: string;
  label: string;
  /** Extra text that is searched and shown in smaller type (optional). */
  detail?: string;
  disabled?: boolean;
};

/** Lower case, accents removed, runs of spaces collapsed, trimmed. */
export function normalise(text: string | null | undefined): string {
  return String(text ?? "")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Options whose label (or detail) contains every word of the query, in any
 * order. Labels that start with the query come first, then labels with a
 * word starting with it, then the rest; the original order is kept within
 * each group. An empty query returns every option.
 */
export function filterOptions<T extends SearchOption>(options: T[], query: string, limit = Infinity): T[] {
  const needle = normalise(query);
  if (!needle) return options.slice(0, limit);
  const words = needle.split(" ");
  const ranked: { option: T; rank: number; index: number }[] = [];
  options.forEach((option, index) => {
    const label = normalise(option.label);
    const haystack = `${label} ${normalise(option.detail)}`;
    if (!words.every((word) => haystack.includes(word))) return;
    const rank = label.startsWith(needle) ? 0 : label.split(" ").some((part) => part.startsWith(words[0])) ? 1 : 2;
    ranked.push({ option, rank, index });
  });
  ranked.sort((a, b) => a.rank - b.rank || a.index - b.index);
  return ranked.slice(0, limit).map((entry) => entry.option);
}

/**
 * The next option to highlight when moving by `step` (+1 down, −1 up),
 * skipping disabled options and wrapping at the ends; −1 when none can be
 * highlighted. From −1, moving down starts at the first option and moving
 * up at the last.
 */
export function stepIndex(options: SearchOption[], current: number, step: 1 | -1): number {
  const count = options.length;
  if (!count) return -1;
  let index = current < 0 ? (step === 1 ? -1 : count) : current;
  for (let tries = 0; tries < count; tries += 1) {
    index = (index + step + count) % count;
    if (!options[index].disabled) return index;
  }
  return -1;
}

/** The first or last option that can be highlighted (Home / End). */
export function edgeIndex(options: SearchOption[], which: "first" | "last"): number {
  return stepIndex(options, -1, which === "first" ? 1 : -1);
}

/** The label shown for the chosen value, or "" when nothing is chosen. */
export function labelFor(options: SearchOption[], value: string): string {
  if (!value) return "";
  return options.find((option) => option.value === value)?.label ?? "";
}
