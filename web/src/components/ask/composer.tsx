"use client";

/** Composer — the question input. Enter sends, Shift+Enter for a newline;
 *  disabled while an answer streams. */

import { useState } from "react";
import { ArrowUp } from "lucide-react";

export function Composer({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
  };

  return (
    <div className="flex items-end gap-2 rounded-xl border border-border bg-surface p-2 shadow-e1 focus-within:border-accent-300">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        rows={1}
        placeholder="Ask anything about your documents…"
        aria-label="Ask a question"
        className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 type-body text-text-1 outline-none placeholder:text-text-3"
      />
      <button
        type="button"
        onClick={submit}
        disabled={disabled || !value.trim()}
        aria-label="Send"
        className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-p-0 transition-colors hover:bg-accent-hover disabled:opacity-40"
      >
        <ArrowUp aria-hidden className="size-4" />
      </button>
    </div>
  );
}
