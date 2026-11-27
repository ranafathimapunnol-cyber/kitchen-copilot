"use client";

import { useSyncExternalStore } from "react";

import { DEFAULT_THEME as DEFAULT, THEMES, THEME_KEY, type ThemeId } from "./themes";

/*
 * Colour themes. Presentation only: stored in this browser (localStorage)
 * and applied as data-theme on <html>; globals.css holds the tokens.
 */

export { THEMES, type ThemeId };

const listeners = new Set<() => void>();

function isTheme(value: string | null | undefined): value is ThemeId {
  return THEMES.some((t) => t.id === value);
}

function current(): ThemeId {
  const value = typeof document === "undefined" ? null : document.documentElement.dataset.theme;
  return isTheme(value) ? value : DEFAULT;
}

export function setTheme(id: ThemeId) {
  const root = document.documentElement;
  if (id === DEFAULT) delete root.dataset.theme;
  else root.dataset.theme = id;
  try {
    window.localStorage.setItem(THEME_KEY, id);
  } catch {
    /* storage blocked: the theme lasts for this page view */
  }
  listeners.forEach((listener) => listener());
}

export function useTheme(): ThemeId {
  return useSyncExternalStore(
    (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    current,
    () => DEFAULT,
  );
}

