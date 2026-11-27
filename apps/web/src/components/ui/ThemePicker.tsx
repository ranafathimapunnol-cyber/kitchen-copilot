"use client";

import { Check, Moon, Sun } from "lucide-react";

import { THEMES, setTheme, useTheme } from "@/lib/theme";
import { cn } from "./cn";

const THEME_ICONS = {
  light: Sun,
  dark: Moon,
} as const;

/** Choose between the Light and Dark application themes. */
export default function ThemePicker({
  compact = false,
}: {
  compact?: boolean;
}) {
  const theme = useTheme();

  if (compact) {
    return (
      <div
        role="radiogroup"
        aria-label="Appearance"
        className="flex items-center gap-2"
      >
        {THEMES.map((t) => {
          const Icon = THEME_ICONS[t.id];
          const active = theme === t.id;

          return (
            <button
              key={t.id}
              type="button"
              role="radio"
              aria-checked={active}
              aria-label={`${t.name} theme`}
              title={`${t.name} theme`}
              onClick={() => setTheme(t.id)}
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-xl border transition-all",
                active
                  ? "border-brand-600 bg-brand-100 text-slate-950 ring-2 ring-brand-500/30"
                  : "border-slate-200 bg-white text-slate-600 hover:border-brand-400 hover:text-slate-900",
              )}
            >
              <Icon size={17} aria-hidden />
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div
      role="radiogroup"
      aria-label="Appearance"
      className="grid grid-cols-1 gap-4 sm:grid-cols-2"
    >
      {THEMES.map((t) => {
        const Icon = THEME_ICONS[t.id];
        const active = theme === t.id;

        return (
          <button
            key={t.id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setTheme(t.id)}
            className={cn(
              "group overflow-hidden rounded-2xl border text-left transition-all duration-200",
              active
                ? "border-brand-600 ring-2 ring-brand-500/30"
                : "border-slate-200 hover:border-brand-400",
            )}
          >
            <span
              aria-hidden
              className="flex h-28 items-center justify-center gap-3"
              style={{ background: t.swatch[0] }}
            >
              <span
                className="flex h-12 w-12 items-center justify-center rounded-xl"
                style={{
                  background: t.swatch[1],
                  color: "#202522",
                }}
              >
                <Icon size={23} />
              </span>
              <span className="flex flex-col gap-2">
                <span
                  className="h-2.5 w-24 rounded-full"
                  style={{ background: t.swatch[2], opacity: 0.8 }}
                />
                <span
                  className="h-2 w-16 rounded-full"
                  style={{ background: t.swatch[2], opacity: 0.4 }}
                />
                <span
                  className="h-5 w-14 rounded-md"
                  style={{ background: t.swatch[1] }}
                />
              </span>
            </span>

            <span className="flex items-center justify-between gap-3 bg-white px-4 py-3">
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-slate-900">
                  {t.name}
                </span>
                <span className="block text-xs text-slate-500">
                  {t.description}
                </span>
              </span>

              {active && (
                <Check
                  size={18}
                  aria-hidden
                  className="shrink-0 text-brand-700"
                />
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}
