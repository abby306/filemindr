"use client";

/**
 * Minimal Server-Sent Events client over a POST request. EventSource only does
 * GET (no body/headers), so the chat stream — which needs auth headers + a JSON
 * body — is consumed by reading the fetch response stream and parsing the
 * `event:`/`data:` frames the backend emits. Same auth seam as the rest.
 */

import { authHeaders } from "@/lib/auth/dev-auth";
import { API_ORIGIN } from "@/lib/api/client";

export interface SSEOptions {
  accountId: string;
  json: unknown;
  signal?: AbortSignal;
  onEvent: (type: string, data: Record<string, unknown>) => void;
}

export async function streamSSE(path: string, opts: SSEOptions): Promise<void> {
  const res = await fetch(`${API_ORIGIN}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...authHeaders(opts.accountId),
    },
    body: JSON.stringify(opts.json),
    signal: opts.signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Stream failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const parsed = parseFrame(frame);
      if (parsed) opts.onEvent(parsed.type, parsed.data);
    }
  }
}

function parseFrame(
  frame: string,
): { type: string; data: Record<string, unknown> } | null {
  let type = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) type = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { type, data: JSON.parse(data) as Record<string, unknown> };
  } catch {
    return { type, data: { raw: data } };
  }
}
