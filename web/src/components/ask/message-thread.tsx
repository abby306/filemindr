"use client";

/** MessageThread — the conversation: user turns as quiet bubbles, assistant
 *  turns as a trace + grounded answer + grouped citations + rating. */

import { AlertCircle, Loader2 } from "lucide-react";

import { CitationPill } from "@/components/ask/citation-pill";
import { RatingRow } from "@/components/ask/rating-row";
import { Trace } from "@/components/ask/trace";
import type { AssistantTurn, Turn } from "@/features/ask/types";

export function MessageThread({
  turns,
  scopeLabel,
}: {
  turns: Turn[];
  /** Set when the chat is scoped to one document (feeds the trace summary). */
  scopeLabel?: string;
}) {
  return (
    <div className="flex flex-col gap-6">
      {turns.map((turn, i) =>
        turn.role === "user" ? (
          <div key={i} className="flex justify-end">
            <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 type-body text-on-accent">
              {turn.content}
            </p>
          </div>
        ) : (
          <AssistantMessage key={i} turn={turn} scopeLabel={scopeLabel} />
        ),
      )}
    </div>
  );
}

function AssistantMessage({
  turn,
  scopeLabel,
}: {
  turn: AssistantTurn;
  scopeLabel?: string;
}) {
  return (
    <div className="flex flex-col">
      <Trace
        steps={turn.steps}
        streaming={turn.status === "streaming"}
        elapsedMs={turn.elapsedMs}
        sourceCount={turn.citationGroups?.length}
        scopeLabel={scopeLabel}
      />

      {turn.status === "error" ? (
        <p className="flex items-center gap-1.5 type-body text-danger">
          <AlertCircle aria-hidden className="size-4" />
          Something went wrong answering that. Try again.
        </p>
      ) : turn.answer ? (
        <>
          {turn.supported === false ? (
            <span className="mb-1.5 inline-flex w-fit items-center gap-1.5 rounded-full bg-surface-2 px-2 py-0.5 type-caption text-text-2">
              <AlertCircle aria-hidden className="size-3" />
              Not found in your documents
            </span>
          ) : null}
          <p className="whitespace-pre-wrap type-body text-text-1">{turn.answer}</p>

          {turn.citationGroups && turn.citationGroups.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {turn.citationGroups.map((g) => (
                <CitationPill key={g.document_id} group={g} />
              ))}
            </div>
          ) : null}

          {turn.messageId ? <RatingRow messageId={turn.messageId} /> : null}
        </>
      ) : turn.status === "streaming" ? (
        <p className="flex items-center gap-1.5 type-callout text-text-3">
          <Loader2 aria-hidden className="size-3.5 motion-safe:animate-spin" />
          Thinking…
        </p>
      ) : null}
    </div>
  );
}
