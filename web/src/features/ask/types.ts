import type { CitationGroup } from "@/lib/api/types";

export interface TraceStep {
  type: string;
  data: Record<string, unknown>;
}

export interface AssistantTurn {
  role: "assistant";
  status: "streaming" | "done" | "error";
  steps: TraceStep[];
  answer?: string;
  supported?: boolean;
  escalated?: boolean;
  model?: string;
  citationGroups?: CitationGroup[];
  messageId?: string;
  elapsedMs?: number;
}

export interface UserTurn {
  role: "user";
  content: string;
}

export type Turn = UserTurn | AssistantTurn;
