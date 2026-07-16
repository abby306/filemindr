"use client";

/**
 * Theme state, driven by `data-theme` on <html>. A blocking inline script
 * (in the root layout) sets the attribute before paint (stored pref → system
 * preference) so there's no flash; this module reads/writes it after mount.
 */

export type Theme = "light" | "dark";

const KEY = "filemindr.theme";
const EVENT = "filemindr:theme-change";

/** Inline script string for the layout — runs before first paint. */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem('${KEY}');var d=window.matchMedia('(prefers-color-scheme: dark)').matches;document.documentElement.dataset.theme=(t==='light'||t==='dark')?t:(d?'dark':'light');}catch(e){}})();`;

export function getTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  window.localStorage.setItem(KEY, theme);
  window.dispatchEvent(new Event(EVENT));
}

export function subscribeTheme(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}
