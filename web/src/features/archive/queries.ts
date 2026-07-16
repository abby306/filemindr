"use client";

/**
 * Archive data hooks over the account-bound request seam. Classes drive the
 * folder rail; documents are cursor-paginated via `useInfiniteQuery`. Query keys
 * include the active account id so switching accounts refetches cleanly.
 */

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useAccount } from "@/lib/account/account-context";
import type {
  ClassInfo,
  DocumentListResponse,
} from "@/lib/api/types";
import {
  buildFolderTree,
  isProcessing,
  type FolderFilter,
} from "@/features/archive/taxonomy";

const PAGE_SIZE = 30;

export function useClasses() {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["classes", account.id],
    queryFn: () => request<ClassInfo[]>("/api/v1/classes"),
    select: (classes) => ({ classes, tree: buildFolderTree(classes) }),
  });
}

function documentsPath(filter: FolderFilter, cursor: string | null): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (filter.kind === "needs_review") params.set("status", "needs_review");
  if (filter.kind === "class") {
    // Archive browse = primary folder only (one document → one folder).
    params.set("class", filter.slug);
    params.set("primary", "true");
  }
  if (cursor) params.set("cursor", cursor);
  return `/api/v1/documents?${params.toString()}`;
}

/**
 * Paginated documents for the selected folder. Polls at ~1s while any loaded
 * document is still processing (the never-wait model), then goes quiet.
 */
export function useArchiveDocuments(filter: FolderFilter) {
  const { account, request } = useAccount();

  return useInfiniteQuery({
    queryKey: ["documents", account.id, filterQueryKey(filter)],
    queryFn: ({ pageParam }) =>
      request<DocumentListResponse>(documentsPath(filter, pageParam)),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    refetchInterval: (query) => {
      const anyProcessing = query.state.data?.pages.some((p) =>
        p.items.some((d) => isProcessing(d.status)),
      );
      return anyProcessing ? 1000 : false;
    },
  });
}

function filterQueryKey(filter: FolderFilter): string {
  return filter.kind === "class" ? `class:${filter.slug}` : filter.kind;
}

/** Refile a document into a folder. `add` (drag) keeps other labels; `replace`
 *  (move) swaps them out — the server owns the semantics (backend gap #4). */
export function useRefile() {
  const { account, request } = useAccount();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      documentId,
      classId,
      mode = "add",
    }: {
      documentId: string;
      classId: string;
      mode?: "add" | "replace" | "set_primary";
    }) =>
      request(`/api/v1/documents/${documentId}/classes`, {
        method: "POST",
        json: { class_ids: [classId], mode },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents", account.id] });
      qc.invalidateQueries({ queryKey: ["classes", account.id] });
    },
  });
}

export function useCreateFolder() {
  const { account, request } = useAccount();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      request<ClassInfo>("/api/v1/classes", { method: "POST", json: { name } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["classes", account.id] }),
  });
}

export function useRenameFolder() {
  const { account, request } = useAccount();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ classId, name }: { classId: string; name: string }) =>
      request(`/api/v1/classes/${classId}`, { method: "PATCH", json: { name } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["classes", account.id] }),
  });
}

export function useDeleteFolder() {
  const { account, request } = useAccount();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (classId: string) =>
      request(`/api/v1/classes/${classId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["classes", account.id] });
      qc.invalidateQueries({ queryKey: ["documents", account.id] });
    },
  });
}
