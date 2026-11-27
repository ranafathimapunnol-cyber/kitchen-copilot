/**
 * Colour themes (data only, usable from server and client code). The
 * store and hook are in lib/theme.ts; the tokens are in globals.css.
 */
export const THEMES = [
  { id: "ivory", name: "Ivory", description: "Warm ivory and coffee", swatch: ["#f5f0e6", "#8b6f50", "#382d25"] },
  { id: "harbor", name: "Harbor", description: "Porcelain and navy", swatch: ["#eef1f4", "#3d6385", "#1f2a36"] },
  { id: "sage", name: "Sage", description: "Mist and eucalyptus", swatch: ["#eef2ee", "#4f7566", "#22302a"] },
  { id: "plum", name: "Plum", description: "Blush and aubergine", swatch: ["#f5eff1", "#7b4f6e", "#352530"] },
  { id: "espresso", name: "Espresso", description: "Dark, for low light", swatch: ["#15110e", "#c9a47d", "#f2eadf"] },
] as const;

export type ThemeId = (typeof THEMES)[number]["id"];
export const THEME_KEY = "kc.theme";
export const DEFAULT_THEME: ThemeId = "ivory";
/** Runs in <head> before the page paints, so a saved theme never flashes. */
export const THEME_BOOT_SCRIPT = `try{var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});if(t&&t!=="ivory"&&${JSON.stringify(THEMES.map((t) => t.id))}.indexOf(t)>-1)document.documentElement.dataset.theme=t}catch(e){}`;
