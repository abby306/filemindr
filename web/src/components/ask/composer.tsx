"use client";

/**
 * Composer — the question input. Enter sends, Shift+Enter for a newline;
 * disabled while an answer streams.
 *
 * Two ways to point a question at specific files: type `@` and pick from the
 * inline document list (the token is replaced by a chip), or use the paperclip
 * to open the same picker. Picked documents show as chips above the input and
 * pin the answer's retrieval to them (server-side `document_ids`).
 */

import { useMemo, useRef, useState } from "react";
import { ArrowUp, AtSign, FileText, Paperclip, X } from "lucide-react";
import clsx from "clsx";

import {
  useMentionableDocuments,
  type MentionableDocument,
} from "@/features/ask/queries";
import { useDismiss } from "@/lib/use-dismiss";

interface AtToken {
  start: number; // index of the "@" in the value
  filter: string;
}

/** The @token immediately before the cursor, if any. */
function activeToken(value: string, cursor: number | null): AtToken | null {
  if (cursor == null) return null;
  const upto = value.slice(0, cursor);
  const match = /(^|\s)@([^\s@]{0,60})$/.exec(upto);
  if (!match) return null;
  return { start: upto.length - match[2].length - 1, filter: match[2] };
}

export function Composer({
  onSend,
  disabled,
}: {
  onSend: (text: string, documentIds: string[]) => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");
  const [mentions, setMentions] = useState<MentionableDocument[]>([]);
  const [token, setToken] = useState<AtToken | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false); // paperclip mode
  const [highlight, setHighlight] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const { data: documents } = useMentionableDocuments();

  const open = pickerOpen || token !== null;
  const filter = (token?.filter ?? "").toLowerCase();
  useDismiss(rootRef, () => {
    setPickerOpen(false);
    setToken(null);
  }, open);

  const options = useMemo(() => {
    const taken = new Set(mentions.map((m) => m.id));
    return (documents ?? [])
      .filter((d) => !taken.has(d.id))
      .filter(
        (d) =>
          !filter ||
          d.title.toLowerCase().includes(filter) ||
          d.filename.toLowerCase().includes(filter),
      )
      .slice(0, 8);
  }, [documents, mentions, filter]);

  const syncToken = (nextValue: string) => {
    setValue(nextValue);
    const cursor = textareaRef.current?.selectionStart ?? nextValue.length;
    setToken(activeToken(nextValue, cursor));
    setHighlight(0);
  };

  const pick = (doc: MentionableDocument) => {
    setMentions((prev) => [...prev, doc]);
    if (token) {
      // Remove the "@partial" the user typed; the chip replaces it.
      const cursor = textareaRef.current?.selectionStart ?? value.length;
      setValue(value.slice(0, token.start) + value.slice(cursor));
    }
    setToken(null);
    setPickerOpen(false);
    setHighlight(0);
    textareaRef.current?.focus();
  };

  const submit = () => {
    const text = value.trim();
    if ((!text && mentions.length === 0) || !text || disabled) return;
    onSend(text, mentions.map((m) => m.id));
    setValue("");
    setMentions([]);
    setToken(null);
    setPickerOpen(false);
  };

  return (
    <div ref={rootRef} className="relative">
      {open && options.length > 0 ? (
        <div className="absolute bottom-full left-0 z-30 mb-2 w-full max-w-md overflow-hidden rounded-lg border border-border bg-surface shadow-e2">
          <p className="flex items-center gap-1.5 border-b border-border px-3 py-1.5 type-caption uppercase text-text-3">
            <AtSign aria-hidden className="size-3" />
            Ask about a document
          </p>
          <ul className="max-h-64 overflow-y-auto p-1">
            {options.map((doc, i) => (
              <li key={doc.id}>
                <button
                  type="button"
                  onClick={() => pick(doc)}
                  onMouseEnter={() => setHighlight(i)}
                  className={clsx(
                    "flex min-h-10 w-full items-center gap-2.5 rounded-md px-2.5 text-left transition-colors",
                    highlight === i ? "bg-accent-50" : "hover:bg-surface-2",
                  )}
                >
                  <FileText aria-hidden className="size-4 shrink-0 text-text-3" strokeWidth={1.75} />
                  <span className="min-w-0">
                    <span className="block truncate type-subhead text-text-1">{doc.title}</span>
                    <span className="block truncate type-data text-text-3">{doc.filename}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {mentions.length > 0 ? (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {mentions.map((doc) => (
            <span
              key={doc.id}
              className="inline-flex max-w-72 items-center gap-1.5 rounded-full border border-accent-300 bg-accent-50 py-1 pl-2.5 pr-1"
            >
              <FileText aria-hidden className="size-3.5 shrink-0 text-accent-text" />
              <span className="truncate type-caption text-accent-text">{doc.title}</span>
              <button
                type="button"
                aria-label={`Remove ${doc.title}`}
                onClick={() =>
                  setMentions((prev) => prev.filter((m) => m.id !== doc.id))
                }
                className="flex size-5 items-center justify-center rounded-full text-accent-text hover:bg-accent-100"
              >
                <X aria-hidden className="size-3" />
              </button>
            </span>
          ))}
        </div>
      ) : null}

      <div className="flex items-end gap-2 rounded-xl border border-border bg-surface p-2 shadow-e1 focus-within:border-accent-300">
        <button
          type="button"
          aria-label="Ask about a specific document"
          aria-expanded={open}
          onClick={() => {
            setPickerOpen((v) => !v);
            setToken(null);
          }}
          className={clsx(
            "flex size-9 shrink-0 items-center justify-center rounded-lg transition-colors",
            open ? "bg-accent-50 text-accent-text" : "text-text-3 hover:bg-surface-2 hover:text-text-1",
          )}
        >
          <Paperclip aria-hidden className="size-4" />
        </button>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => syncToken(e.target.value)}
          onClick={(e) => setToken(activeToken(value, e.currentTarget.selectionStart))}
          onKeyDown={(e) => {
            if (open && options.length > 0) {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setHighlight((h) => Math.min(h + 1, options.length - 1));
                return;
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setHighlight((h) => Math.max(h - 1, 0));
                return;
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                pick(options[highlight]);
                return;
              }
              if (e.key === "Escape") {
                setToken(null);
                setPickerOpen(false);
                return;
              }
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder="Ask anything — type @ to point at a document…"
          aria-label="Ask a question"
          className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 type-body text-text-1 outline-none placeholder:text-text-3"
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !value.trim()}
          aria-label="Send"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-40"
        >
          <ArrowUp aria-hidden className="size-4" />
        </button>
      </div>
    </div>
  );
}
