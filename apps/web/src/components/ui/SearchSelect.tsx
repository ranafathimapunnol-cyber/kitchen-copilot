"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { ChevronDown, X } from "lucide-react";

import { edgeIndex, filterOptions, labelFor, stepIndex, type SearchOption } from "@/lib/searchSelect";
import { controlClass } from "./Field";
import { cn } from "./cn";

export type { SearchOption };

type Props = {
  /** From <Field>: ties the visible label to the input. */
  id?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
  /** The chosen option's value ("" for none), exactly as the old <select> held it. */
  value: string;
  onChange: (value: string) => void;
  options: SearchOption[];
  /** Shown while nothing is chosen, e.g. "Choose an item…". */
  placeholder?: string;
  /**
   * For filters: an option meaning "no filter" (value ""), e.g. "All
   * items", listed first and shown while nothing is chosen.
   */
  emptyLabel?: string;
  /** Plural used in messages and as the list's name, e.g. "items". */
  noun?: string;
  loading?: boolean;
  loadingText?: string;
  disabled?: boolean;
  /** Blocks native form submission while nothing is chosen. */
  required?: boolean;
  requiredMessage?: string;
  /** Show the clear button when something is chosen (default true). */
  clearable?: boolean;
  /** Most options rendered at once; typing narrows the rest. */
  maxResults?: number;
  className?: string;
  "data-autofocus"?: boolean;
};

/**
 * A search-as-you-type selection list (PROPOSAL §5.7; Stage 7 S7-A),
 * following the WAI-ARIA combobox pattern with a list popup. It filters
 * the options the form has already loaded; it never calls the API and
 * holds the same value the old <select> held, so payloads, validation and
 * permissions are unchanged.
 *
 * Keyboard: typing filters; ↓/↑ (Alt+↓ opens) move through the list,
 * Home/End jump to the ends, Enter chooses, Escape closes without
 * changing anything, Tab moves on. Typing never changes the chosen value
 * until an option is chosen; the clear button chooses nothing.
 */
export default function SearchSelect({
  id,
  value,
  onChange,
  options,
  placeholder,
  emptyLabel,
  noun = "options",
  loading = false,
  loadingText = "Loading…",
  disabled = false,
  required = false,
  requiredMessage,
  clearable = true,
  maxResults = 200,
  className,
  ...aria
}: Props) {
  const generated = useId();
  const inputId = id ?? `search-select-${generated}`;
  const listId = `${inputId}-listbox`;
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(-1);

  const selectedLabel = labelFor(options, value);
  const shown: SearchOption[] = useMemo(() => {
    const matches = filterOptions(options, typed ? query : "", maxResults);
    return emptyLabel && !(typed && query.trim()) ? [{ value: "", label: emptyLabel }, ...matches] : matches;
  }, [options, typed, query, maxResults, emptyLabel]);
  const inactive = disabled || loading;

  // Native validation (forms that rely on `required`) sees "nothing chosen".
  useEffect(() => {
    inputRef.current?.setCustomValidity(
      required && !value ? requiredMessage ?? `Choose one of the ${noun}.` : ""
    );
  }, [required, value, requiredMessage, noun]);

  useEffect(() => {
    if (!open || active < 0) return;
    const node = listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`);
    node?.scrollIntoView?.({ block: "nearest" });
  }, [open, active]);

  function openList() {
    if (inactive) return;
    setOpen(true);
    setTyped(false);
    setQuery("");
    const current = shown.findIndex((option) => option.value === value);
    setActive(current >= 0 ? current : -1);
  }

  function close() {
    setOpen(false);
    setTyped(false);
    setQuery("");
    setActive(-1);
  }

  /** Keep focus with the shown text selected, so further typing starts a new search. */
  function selectShownText() {
    setTimeout(() => {
      if (inputRef.current && document.activeElement === inputRef.current) inputRef.current.select();
    }, 0);
  }

  function choose(option: SearchOption) {
    if (option.disabled) return;
    if (option.value !== value) onChange(option.value);
    close();
    selectShownText();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (inactive) return;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (!open) {
          openList();
          return;
        }
        setActive((index) => stepIndex(shown, index, 1));
        return;
      case "ArrowUp":
        event.preventDefault();
        if (!open) {
          openList();
          return;
        }
        setActive((index) => stepIndex(shown, index, -1));
        return;
      case "Home":
      case "End":
        if (!open) return;
        event.preventDefault();
        setActive(edgeIndex(shown, event.key === "Home" ? "first" : "last"));
        return;
      case "Enter":
        if (!open) return;
        event.preventDefault();
        if (active >= 0 && shown[active]) choose(shown[active]);
        return;
      case "Escape":
        if (!open) return;
        // Close the list only, not a dialog the picker sits in.
        event.preventDefault();
        event.stopPropagation();
        close();
        selectShownText();
        return;
      case "Tab":
        if (open) close();
        return;
      default:
        return;
    }
  }

  const showClear = clearable && Boolean(value) && !inactive;
  const display = open && typed ? query : selectedLabel;

  return (
    <div className="relative">
      <input
        ref={inputRef}
        id={inputId}
        type="text"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
        aria-required={required || undefined}
        aria-describedby={aria["aria-describedby"]}
        aria-invalid={aria["aria-invalid"] || undefined}
        data-autofocus={aria["data-autofocus"] || undefined}
        data-search-select=""
        autoComplete="off"
        spellCheck={false}
        disabled={inactive}
        placeholder={loading ? loadingText : value ? undefined : emptyLabel ?? placeholder}
        value={display}
        className={cn(controlClass, "h-10", showClear ? "pr-16" : "pr-9", className)}
        onFocus={(event) => {
          event.currentTarget.select();
        }}
        onClick={() => {
          if (!open) openList();
        }}
        onChange={(event) => {
          let next = event.target.value;
          // Letters typed after a chosen name start a new search instead of
          // extending the name.
          if (!typed && selectedLabel && next.length > selectedLabel.length && next.startsWith(selectedLabel)) {
            next = next.slice(selectedLabel.length);
          }
          if (!open) setOpen(true);
          setTyped(true);
          setQuery(next);
          setActive(-1);
        }}
        onKeyDown={onKeyDown}
        onBlur={close}
      />
      {showClear && (
        <button
          type="button"
          tabIndex={-1}
          aria-label={`Clear the chosen ${noun.replace(/s$/, "")}`}
          className="absolute top-1/2 right-8 -translate-y-1/2 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => {
            onChange("");
            close();
            inputRef.current?.focus();
          }}
        >
          <X size={14} aria-hidden />
        </button>
      )}
      <ChevronDown
        size={16}
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-slate-400"
      />
      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          aria-label={noun.charAt(0).toUpperCase() + noun.slice(1)}
          className="absolute z-30 mt-1 max-h-64 w-full min-w-48 overflow-auto rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg"
        >
          {shown.length === 0 ? (
            <li role="option" aria-selected={false} aria-disabled="true" className="px-3 py-2 text-slate-500">
              No {noun} match &ldquo;{query.trim()}&rdquo;
            </li>
          ) : (
            shown.map((option, index) => (
              <li
                key={option.value || "__empty"}
                id={`${listId}-${index}`}
                data-index={index}
                data-value={option.value}
                role="option"
                aria-selected={option.value === value}
                aria-disabled={option.disabled || undefined}
                className={cn(
                  "cursor-pointer px-3 py-2",
                  option.disabled && "cursor-not-allowed text-slate-400",
                  index === active && "bg-brand-50 text-brand-800",
                  option.value === value && "font-semibold"
                )}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => !option.disabled && setActive(index)}
                onClick={() => choose(option)}
              >
                {option.label}
                {option.detail && <span className="ml-1 text-xs text-slate-500">· {option.detail}</span>}
              </li>
            ))
          )}
        </ul>
      )}
      <span className="sr-only" aria-live="polite">
        {open ? (shown.length ? `${shown.length} ${noun} shown` : `No ${noun} match`) : ""}
      </span>
    </div>
  );
}
