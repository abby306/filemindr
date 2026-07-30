"use client";

/**
 * FolderChat — "Ask this folder": the grounded chat, docked beside the folder
 * you're looking at and scoped to it. Retrieval is pinned server-side to the
 * folder's class *and its subclasses* (`scope: "folder"`), so asking inside
 * Financial ▸ Receipts can only be answered from receipts — the answer's
 * citations are all documents you can see in the current directory.
 *
 * Desktop docks it as a right-hand panel; below `lg` it's the standard bottom
 * sheet. Turn-taking is the shared `useChatSession`, so the thread, trace, and
 * citation rendering are identical to the full Ask screen.
 */

import { useEffect, useRef } from "react";
import Link from "next/link";
import { MessageSquareText, Sparkles, X } from "lucide-react";

import { Composer } from "@/components/ask/composer";
import { MessageThread } from "@/components/ask/message-thread";
import { Sheet } from "@/components/ui/sheet";
import { useChatSession } from "@/features/ask/use-chat-session";
import { useMedia } from "@/lib/use-media";

export function FolderChat({
  classSlug,
  folderName,
  open,
  onClose,
}: {
  classSlug: string;
  folderName: string;
  open: boolean;
  onClose: () => void;
}) {
  const docked = useMedia("(min-width: 1024px)");

  if (!open) return null;
  if (docked) {
    return (
      <aside
        role="complementary"
        aria-label={`Ask the ${folderName} folder`}
        className="animate-rise-in fixed bottom-4 right-4 top-20 z-30 flex w-[26rem] flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-e3"
      >
        <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
          <span className="flex min-w-0 items-center gap-2">
            <Sparkles aria-hidden className="size-4 shrink-0 text-accent" strokeWidth={1.75} />
            <span className="truncate type-subhead text-text-1">Ask {folderName}</span>
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close folder chat"
            className="pressable flex size-8 items-center justify-center rounded-md text-text-3 transition-colors hover:bg-surface-2 hover:text-text-1"
          >
            <X aria-hidden className="size-4" />
          </button>
        </header>
        <Conversation classSlug={classSlug} folderName={folderName} />
      </aside>
    );
  }

  return (
    <Sheet open={open} onClose={onClose} title={`Ask ${folderName}`} tall>
      <Conversation classSlug={classSlug} folderName={folderName} />
    </Sheet>
  );
}

/** The thread + composer. Each folder gets its own fresh conversation — the
 *  dock is a quick question about what's in front of you, not the chat rail. */
function Conversation({
  classSlug,
  folderName,
}: {
  classSlug: string;
  folderName: string;
}) {
  const { turns, streaming, send, activeId } = useChatSession({
    conversationId: null,
    scope: { classSlug },
  });
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  return (
    <>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {turns.length === 0 ? (
          <Empty folderName={folderName} />
        ) : (
          <>
            <MessageThread turns={turns} scopeLabel={folderName} />
            <div ref={bottomRef} />
          </>
        )}
      </div>
      <div className="border-t border-border px-4 pb-3 pt-3">
        <Composer onSend={send} disabled={streaming} />
        <p className="mt-1.5 flex items-center justify-between gap-2 type-caption text-text-3">
          <span>Scoped to {folderName} and its subfolders.</span>
          {activeId ? (
            <Link href={`/chat/${activeId}`} className="shrink-0 text-accent-text hover:underline">
              Open in Ask
            </Link>
          ) : null}
        </p>
      </div>
    </>
  );
}

function Empty({ folderName }: { folderName: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-2 text-center">
      <span className="flex size-10 items-center justify-center rounded-lg bg-surface-2 text-accent">
        <MessageSquareText aria-hidden className="size-5" strokeWidth={1.5} />
      </span>
      <p className="mt-3 type-title3 text-text-1">Ask about {folderName}</p>
      <p className="mt-1 type-callout text-text-2">
        Totals, dates, parties, terms — answered only from the documents filed
        here, with citations.
      </p>
    </div>
  );
}
