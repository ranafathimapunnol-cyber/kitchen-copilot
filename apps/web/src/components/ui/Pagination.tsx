"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "./cn";

type Props = {
  page: number;
  pageCount: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  /** Plural noun for the range text, e.g. "records". */
  noun?: string;
  pageSizeOptions?: number[];
  onPageSizeChange?: (size: number) => void;
};

/** 1 … 4 5 6 … 12 — current page with one neighbour each side. */
function pageList(page: number, count: number): Array<number | "gap"> {
  if (count <= 7) return Array.from({ length: count }, (_, i) => i + 1);

  const pages = new Set([1, count, page - 1, page, page + 1]);
  const sorted = [...pages]
    .filter((value) => value >= 1 && value <= count)
    .sort((a, b) => a - b);

  const result: Array<number | "gap"> = [];
  sorted.forEach((value, index) => {
    if (index > 0 && value - sorted[index - 1] > 1) result.push("gap");
    result.push(value);
  });
  return result;
}

const stepClass =
  "inline-flex h-8 min-w-8 items-center justify-center rounded-lg px-2 text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-40";

export default function Pagination({
  page,
  pageCount,
  total,
  pageSize,
  onPageChange,
  noun = "records",
  pageSizeOptions,
  onPageSizeChange,
}: Props) {
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  return (
    <nav
      aria-label="Pagination"
      className="flex flex-col gap-3 border-t border-slate-100 px-5 py-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-slate-500">
        <p>
          <span className="font-medium text-slate-700">
            {first}–{last}
          </span>{" "}
          of <span className="font-medium text-slate-700">{total}</span>{" "}
          {noun}
        </p>

        {pageSizeOptions && onPageSizeChange && (
          <label className="flex items-center gap-2">
            <span>Rows</span>
            <select
              value={pageSize}
              onChange={(event) => onPageSizeChange(Number(event.target.value))}
              className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-sm text-slate-700 focus:border-brand-500 focus:ring-3 focus:ring-brand-500/15 focus:outline-none"
            >
              {pageSizeOptions.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {pageCount > 1 && (
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            aria-label="Previous page"
            className={cn(stepClass, "text-slate-600 hover:bg-slate-100")}
          >
            <ChevronLeft size={16} />
          </button>

          {/* Page numbers on wider screens; a compact counter on phones. */}
          <span className="px-2 text-sm text-slate-600 sm:hidden">
            {page} / {pageCount}
          </span>

          <div className="hidden items-center gap-1 sm:flex">
            {pageList(page, pageCount).map((item, index) =>
              item === "gap" ? (
                <span
                  key={`gap-${index}`}
                  className="px-1 text-slate-400"
                  aria-hidden
                >
                  …
                </span>
              ) : (
                <button
                  key={item}
                  type="button"
                  onClick={() => onPageChange(item)}
                  aria-current={item === page ? "page" : undefined}
                  aria-label={`Page ${item}`}
                  className={cn(
                    stepClass,
                    item === page
                      ? "bg-brand-600 text-white"
                      : "text-slate-600 hover:bg-slate-100"
                  )}
                >
                  {item}
                </button>
              )
            )}
          </div>

          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= pageCount}
            aria-label="Next page"
            className={cn(stepClass, "text-slate-600 hover:bg-slate-100")}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}
    </nav>
  );
}
