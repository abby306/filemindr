/**
 * The single fetch seam over the FastAPI JSON API.
 *
 * Thin-client rule: no business logic here — this only attaches auth/scoping
 * headers and normalizes errors. In dev, `API_ORIGIN` is empty so requests go
 * same-origin to `/api/*` and Next's rewrite proxies them to the backend; in
 * prod set `NEXT_PUBLIC_API_ORIGIN` to the backend URL (CORS-enabled) and the
 * exact same paths work with no code change.
 */

import { authHeaders } from "@/lib/auth/dev-auth";

/** Empty in dev (same-origin + rewrite); absolute backend URL in prod. */
export const API_ORIGIN = process.env.NEXT_PUBLIC_API_ORIGIN ?? "";

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  /** Active account UUID → `X-Account-Id`. */
  accountId: string;
  /** JSON-serializable body; sets Content-Type automatically. */
  json?: unknown;
  /** Raw body (e.g. FormData for uploads); Content-Type left to the browser. */
  body?: BodyInit;
}

/**
 * Perform an authenticated request against a `/api/v1/...` path and return the
 * raw {@link Response} (so callers can read the status, e.g. dedup 200 vs 201).
 * Throws {@link ApiError} on non-2xx, unwrapping the backend's
 * `{ detail: { code, message } }` envelope into a readable message.
 */
export async function apiRequest(
  path: string,
  { accountId, json, body, headers, ...init }: RequestOptions,
): Promise<Response> {
  const res = await fetch(`${API_ORIGIN}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...authHeaders(accountId),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : body,
  });

  if (!res.ok) {
    throw await toApiError(res);
  }
  return res;
}

/** As {@link apiRequest}, but parses and returns the JSON body (204 → undefined). */
export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions,
): Promise<T> {
  const res = await apiRequest(path, options);
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

async function toApiError(res: Response): Promise<ApiError> {
  let message = res.statusText || `Request failed (${res.status})`;
  let code: string | undefined;
  try {
    const data = await res.json();
    const detail = data?.detail ?? data?.error;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      message = detail.message ?? message;
      code = detail.code;
    }
  } catch {
    // non-JSON error body — keep the status-derived message
  }
  return new ApiError(res.status, message, code);
}
