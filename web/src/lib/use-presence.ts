"use client";

/**
 * usePresence — keep a conditionally-rendered overlay mounted while it animates
 * out. Returns `mounted` (render while true) and `state` ("open" | "closing")
 * so the element can pick its enter vs. exit animation. When `open` flips to
 * false, the element stays mounted for `ms` (the exit duration) before it goes.
 *
 *   const { mounted, state } = usePresence(open, 180);
 *   if (!mounted) return null;
 *   <div className={state === "open" ? "animate-sheet-up" : "animate-sheet-down"} />
 *
 * Enter animations run on mount (the element mounts with its enter keyframe
 * class), so no next-frame flip is needed — this assumes CSS keyframe
 * animations, not transitions.
 */

import { useEffect, useState } from "react";

export function usePresence(open: boolean, ms = 180) {
  const [rendered, setRendered] = useState(open);

  // Adjust state during render (React-approved) rather than in an effect:
  // as soon as `open` goes true, mount immediately so the enter keyframe plays.
  if (open && !rendered) setRendered(true);

  useEffect(() => {
    if (open) return;
    const t = window.setTimeout(() => setRendered(false), ms);
    return () => window.clearTimeout(t);
  }, [open, ms]);

  return { mounted: rendered, state: open ? ("open" as const) : ("closing" as const) };
}
