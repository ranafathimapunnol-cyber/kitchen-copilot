/**
 * Report periods as inclusive YYYY-MM-DD ranges, in the browser's local
 * calendar. No imports, so `node --test` can run its tests directly.
 */

export type Period = { from: string; to: string };

export function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** The 1st of this month up to today (a month to date). */
export function monthToDate(today: Date): Period {
  return {
    from: isoDate(new Date(today.getFullYear(), today.getMonth(), 1)),
    to: isoDate(today),
  };
}

/** The whole previous calendar month. */
export function previousMonth(today: Date): Period {
  return {
    from: isoDate(new Date(today.getFullYear(), today.getMonth() - 1, 1)),
    // Day 0 of this month is the last day of the previous one.
    to: isoDate(new Date(today.getFullYear(), today.getMonth(), 0)),
  };
}

/** 1 April to today, or the previous 1 April in January to March: India's
 * financial year to date. */
export function financialYearToDate(today: Date): Period {
  const startYear = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
  return { from: isoDate(new Date(startYear, 3, 1)), to: isoDate(today) };
}

export function isValidPeriod(period: Period): boolean {
  const pattern = /^\d{4}-\d{2}-\d{2}$/;
  return pattern.test(period.from) && pattern.test(period.to) && period.from <= period.to;
}
