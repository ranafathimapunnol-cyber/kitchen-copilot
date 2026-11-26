import { api } from "./client";

/** The master-data list endpoints' maximum page_size. */
export const FETCH_PAGE_SIZE = 100;

/** Safety cap: 50 × 100 = 5,000 rows, far beyond any campus's master data. */
export const MAX_FETCH_PAGES = 50;

type PaginatedResponse = {
  total_pages?: number;
};

/** Accepts a bare array or an {items | results | data} envelope. */
export function normalizeList<T = Record<string, unknown>>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];

  if (data && typeof data === "object") {
    const object = data as Record<string, unknown>;

    for (const key of ["items", "results", "data"]) {
      if (Array.isArray(object[key])) {
        return object[key] as T[];
      }
    }
  }

  return [];
}

function pageUrl(endpoint: string, page: number, pageSize: number): string {
  const separator = endpoint.includes("?") ? "&" : "?";
  return `${endpoint}${separator}page=${page}&page_size=${pageSize}`;
}

/**
 * Loads every page of a paginated list endpoint.
 *
 * Without page parameters the master-data endpoints return only their
 * default 10 rows, which silently truncated dropdowns. The list APIs also
 * accept no search parameter, so search runs over the full set client-side.
 */
export async function fetchAllRecords<T = Record<string, unknown>>(
  endpoint: string
): Promise<{ rows: T[]; truncated: boolean }> {
  const first = await api.get<unknown>(pageUrl(endpoint, 1, FETCH_PAGE_SIZE));
  const rows = normalizeList<T>(first);

  const meta = (
    first && typeof first === "object" && !Array.isArray(first) ? first : {}
  ) as PaginatedResponse;

  const totalPages = meta.total_pages ?? 1;
  const pagesToFetch = Math.min(totalPages, MAX_FETCH_PAGES);

  if (pagesToFetch > 1) {
    const rest = await Promise.all(
      Array.from({ length: pagesToFetch - 1 }, (_, index) =>
        api.get<unknown>(pageUrl(endpoint, index + 2, FETCH_PAGE_SIZE))
      )
    );
    rest.forEach((page) => rows.push(...normalizeList<T>(page)));
  }

  // A record created between page requests shifts rows across pages;
  // drop the duplicates that can cause.
  const seen = new Set<string>();
  const unique = rows.filter((row) => {
    const id = (row as { id?: unknown }).id;
    const key = String(id ?? JSON.stringify(row));
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return { rows: unique, truncated: totalPages > MAX_FETCH_PAGES };
}
