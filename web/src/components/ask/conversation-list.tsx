"use client";

/** ConversationList — the chat rail: start a new chat, continue any past one,
 *  or delete one (hover/touch trash; deleting the open chat returns to /chat). */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus, MessageSquareText, Trash2 } from "lucide-react";
import clsx from "clsx";

import { Skeleton } from "@/components/ui/skeleton";
import { useConversations, useDeleteConversation } from "@/features/ask/queries";

export function ConversationList({
  activeId,
  onNavigate,
}: {
  activeId: string | null;
  onNavigate?: () => void;
}) {
  const router = useRouter();
  const { data, isPending } = useConversations();
  const deleteConversation = useDeleteConversation();

  const onDelete = (id: string, title: string | null) => {
    if (!window.confirm(`Delete “${title || "this chat"}”? Its messages are removed for good.`)) {
      return;
    }
    deleteConversation.mutate(id, {
      onSuccess: () => {
        if (id === activeId) {
          onNavigate?.();
          router.replace("/chat");
        }
      },
    });
  };

  return (
    <div className="flex h-full flex-col p-3">
      <Link
        href="/chat"
        onClick={onNavigate}
        className="mb-3 flex min-h-11 items-center gap-2 rounded-md border border-border bg-surface px-3 type-subhead text-text-1 transition-colors hover:border-accent-300 hover:bg-accent-50"
      >
        <Plus aria-hidden className="size-4 text-accent" />
        New chat
      </Link>

      <p className="px-2 pb-1 type-caption uppercase text-text-3">Recent</p>

      {isPending ? (
        <div className="flex flex-col gap-1.5 px-1">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-11 w-full" />
          ))}
        </div>
      ) : (data?.length ?? 0) === 0 ? (
        <p className="px-2 type-callout text-text-3">No chats yet.</p>
      ) : (
        <nav className="flex flex-col gap-0.5 overflow-y-auto">
          {data!.map((c) => {
            const active = c.id === activeId;
            return (
              <div key={c.id} className="group/chat relative">
                <Link
                  href={`/chat/${c.id}`}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={clsx(
                    "flex flex-col gap-0.5 rounded-md px-2.5 py-2 pr-9 transition-colors",
                    active ? "bg-accent-50" : "hover:bg-surface-2",
                  )}
                >
                  <span className="flex items-center gap-2">
                    <MessageSquareText
                      aria-hidden
                      className={clsx("size-3.5 shrink-0", active ? "text-accent" : "text-text-3")}
                    />
                    <span
                      className={clsx(
                        "truncate type-subhead",
                        active ? "text-accent" : "text-text-1",
                      )}
                    >
                      {c.title || "New chat"}
                    </span>
                  </span>
                  {c.preview ? (
                    <span className="truncate pl-5 type-caption text-text-3">
                      {c.preview}
                    </span>
                  ) : null}
                </Link>
                <button
                  type="button"
                  aria-label={`Delete chat: ${c.title || "New chat"}`}
                  onClick={() => onDelete(c.id, c.title)}
                  className="absolute right-1 top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-md text-text-3 opacity-100 transition-opacity hover:bg-danger/10 hover:text-danger lg:opacity-0 lg:group-hover/chat:opacity-100 lg:focus-visible:opacity-100"
                >
                  <Trash2 aria-hidden className="size-3.5" />
                </button>
              </div>
            );
          })}
        </nav>
      )}
    </div>
  );
}
