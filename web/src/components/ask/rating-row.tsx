"use client";

/** RatingRow — one-tap thumbs on an answer (writes to the answer's trace). The
 *  richer stars/reasons diagnostic is deferred; the control is shown now. */

import { useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import clsx from "clsx";

import { useRating } from "@/features/ask/queries";

export function RatingRow({ messageId }: { messageId: string }) {
  const rate = useRating();
  const [choice, setChoice] = useState<"up" | "down" | null>(null);

  const send = (rating: "up" | "down") => {
    setChoice(rating);
    rate.mutate({ messageId, rating });
  };

  return (
    <div className="mt-2 flex items-center gap-1">
      <button
        type="button"
        aria-label="Helpful"
        aria-pressed={choice === "up"}
        onClick={() => send("up")}
        className={clsx(
          "flex size-7 items-center justify-center rounded-md transition-colors",
          choice === "up" ? "bg-ok/12 text-ok" : "text-text-3 hover:bg-surface-2 hover:text-text-1",
        )}
      >
        <ThumbsUp aria-hidden className="size-3.5" />
      </button>
      <button
        type="button"
        aria-label="Not helpful"
        aria-pressed={choice === "down"}
        onClick={() => send("down")}
        className={clsx(
          "flex size-7 items-center justify-center rounded-md transition-colors",
          choice === "down" ? "bg-danger/12 text-danger" : "text-text-3 hover:bg-surface-2 hover:text-text-1",
        )}
      >
        <ThumbsDown aria-hidden className="size-3.5" />
      </button>
      {choice ? <span className="ml-1 type-caption text-text-3">Thanks</span> : null}
    </div>
  );
}
