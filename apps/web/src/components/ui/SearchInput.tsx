"use client";

import { Search, X } from "lucide-react";

import { controlClass } from "./Field";
import { cn } from "./cn";

type Props = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** Accessible name; the placeholder alone is not one. */
  label: string;
  className?: string;
};

export default function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  label,
  className,
}: Props) {
  return (
    <div className={cn("relative min-w-0", className)}>
      <Search
        size={16}
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slate-400"
      />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape" && value) {
            event.preventDefault();
            onChange("");
          }
        }}
        placeholder={placeholder}
        aria-label={label}
        className={cn(
          controlClass,
          "h-9 pr-9 pl-9 [&::-webkit-search-cancel-button]:hidden"
        )}
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute top-1/2 right-2 -translate-y-1/2 rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
