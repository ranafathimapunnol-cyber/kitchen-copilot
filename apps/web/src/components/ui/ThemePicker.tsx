"use client";

import { Check } from "lucide-react";

import { THEMES, setTheme, useTheme } from "@/lib/theme";
import { cn } from "./cn";

/** Choose a colour theme. `compact` is the account-menu row of swatches. */
export default function ThemePicker({ compact = false }: { compact?: boolean }) {
  const theme = useTheme();

  if (compact) {
    return (
      <div role="radiogroup" aria-label="Colour theme" className="flex items-center gap-1.5">
        {THEMES.map((t) => (
          <button key={t.id} type="button" role="radio" aria-checked={theme === t.id} title={`${t.name} — ${t.description}`}
            aria-label={t.name} onClick={() => setTheme(t.id)}
            className={cn("relative h-7 w-7 overflow-hidden rounded-full ring-1 ring-slate-300 transition-transform hover:scale-110",
              theme === t.id && "ring-2 ring-brand-600 ring-offset-2 ring-offset-white")}
            style={{ background: `linear-gradient(135deg, ${t.swatch[0]} 0 50%, ${t.swatch[1]} 50% 100%)` }} />
        ))}
      </div>
    );
  }

  return (
    <div role="radiogroup" aria-label="Colour theme" className="grid grid-cols-1 gap-3 min-[460px]:grid-cols-2 lg:grid-cols-5">
      {THEMES.map((t) => {
        const active = theme === t.id;
        return (
          <button key={t.id} type="button" role="radio" aria-checked={active} onClick={() => setTheme(t.id)}
            className={cn("group overflow-hidden rounded-2xl border bg-white text-left transition-[border-color,box-shadow] duration-200",
              active ? "border-brand-600 shadow-raised ring-1 ring-brand-600" : "border-slate-200 hover:border-brand-300 hover:shadow-card")}>
            <span aria-hidden className="flex h-16 items-stretch" style={{ background: t.swatch[0] }}>
              <span className="m-2.5 w-8 rounded-md" style={{ background: t.swatch[2], opacity: 0.9 }} />
              <span className="my-2.5 flex flex-1 flex-col gap-1.5 pr-2.5">
                <span className="h-2.5 w-3/4 rounded-full" style={{ background: t.swatch[2], opacity: 0.35 }} />
                <span className="h-2.5 w-1/2 rounded-full" style={{ background: t.swatch[1] }} />
                <span className="mt-auto h-4 w-12 rounded" style={{ background: t.swatch[1] }} />
              </span>
            </span>
            <span className="flex items-center justify-between gap-2 px-3.5 py-2.5">
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-slate-900">{t.name}</span>
                <span className="block truncate text-xs text-slate-500">{t.description}</span>
              </span>
              {active && <Check size={16} aria-hidden className="shrink-0 text-brand-700" />}
            </span>
          </button>
        );
      })}
    </div>
  );
}
