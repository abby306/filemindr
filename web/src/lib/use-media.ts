"use client";

/** SSR-safe media query hook (useSyncExternalStore over matchMedia). */

import { useSyncExternalStore } from "react";

export function useMedia(query: string, serverDefault = false): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => serverDefault,
  );
}
