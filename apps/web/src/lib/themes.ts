/**
 * Kitchen Copilot appearance themes.
 * Theme tokens are defined centrally in globals.css.
 */
export const THEMES = [
  {
    id: "light",
    name: "Light",
    description: "Clean ivory, charcoal and lime",
    swatch: ["#F0F0EB", "#D9F18D", "#202522"],
  },
  {
    id: "dark",
    name: "Dark",
    description: "Deep charcoal and soft white",
    swatch: ["#171A18", "#D9F18D", "#F0F0EB"],
  },
] as const;

export type ThemeId = (typeof THEMES)[number]["id"];

export const THEME_KEY = "kc.theme";
export const DEFAULT_THEME: ThemeId = "light";

/**
 * Applies the saved theme before the first page paint.
 * Old theme IDs are safely migrated to Light.
 */
export const THEME_BOOT_SCRIPT = `
try {
  var t = localStorage.getItem(${JSON.stringify(THEME_KEY)});
  if (t === "dark" || t === "espresso") {
    document.documentElement.dataset.theme = "dark";
  } else {
    document.documentElement.dataset.theme = "light";
    if (t && t !== "light") {
      localStorage.setItem(${JSON.stringify(THEME_KEY)}, "light");
    }
  }
} catch (e) {}
`;
