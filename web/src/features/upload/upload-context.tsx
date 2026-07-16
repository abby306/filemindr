"use client";

/**
 * UploadProvider — owns the never-wait upload flow. Files funnel here from the
 * dropzone, browse, or paste; each posts to `POST /documents` and, on success,
 * invalidates the documents feed so the new card appears (server status then
 * drives Pipeline fill). Optimistic "uploading" entries cover the brief POST
 * window; validation failures and errors stay as dismissible/retryable cards.
 * State is client-only presentation — no derived business logic lives here.
 */

import {
  createContext,
  useCallback,
  useContext,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useAccount } from "@/lib/account/account-context";
import { ApiError, apiRequest } from "@/lib/api/client";

const ALLOWED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".docx"];
const MAX_UPLOAD_MB = 50;

export interface PendingUpload {
  id: string;
  name: string;
  size: number;
  state: "uploading" | "error";
  error?: string;
  file?: File; // retained in memory for retry
}

interface UploadContextValue {
  pending: PendingUpload[];
  uploadFiles: (files: FileList | File[]) => void;
  retry: (id: string) => void;
  dismiss: (id: string) => void;
}

const UploadContext = createContext<UploadContextValue | null>(null);

function validate(file: File): string | null {
  const dot = file.name.lastIndexOf(".");
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return "Unsupported type — PDF, PNG, JPG, or DOCX only.";
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `Too large — ${MAX_UPLOAD_MB} MB max.`;
  }
  if (file.size === 0) {
    return "File is empty.";
  }
  return null;
}

export function UploadProvider({ children }: { children: React.ReactNode }) {
  const { account } = useAccount();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingUpload[]>([]);

  const update = useCallback(
    (id: string, patch: Partial<PendingUpload>) =>
      setPending((prev) =>
        prev.map((p) => (p.id === id ? { ...p, ...patch } : p)),
      ),
    [],
  );

  const send = useCallback(
    async (entry: PendingUpload) => {
      const file = entry.file;
      if (!file) return;

      const invalid = validate(file);
      if (invalid) {
        update(entry.id, { state: "error", error: invalid });
        return;
      }

      try {
        const form = new FormData();
        form.append("file", file);
        await apiRequest("/api/v1/documents", {
          accountId: account.id,
          method: "POST",
          body: form,
        });
        // Refetch the feed, then drop the optimistic entry (no flash).
        await queryClient.invalidateQueries({
          queryKey: ["documents", account.id],
        });
        setPending((prev) => prev.filter((p) => p.id !== entry.id));
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : "Upload failed — check your connection.";
        update(entry.id, { state: "error", error: message });
      }
    },
    [account.id, queryClient, update],
  );

  const uploadFiles = useCallback(
    (files: FileList | File[]) => {
      const list = Array.from(files);
      if (list.length === 0) return;
      const entries: PendingUpload[] = list.map((file) => ({
        id: crypto.randomUUID(),
        name: file.name,
        size: file.size,
        state: "uploading",
        file,
      }));
      setPending((prev) => [...entries, ...prev]);
      entries.forEach((entry) => void send(entry));
    },
    [send],
  );

  const retry = useCallback(
    (id: string) => {
      const entry = pending.find((p) => p.id === id);
      if (!entry) return;
      update(id, { state: "uploading", error: undefined });
      void send({ ...entry, state: "uploading", error: undefined });
    },
    [pending, send, update],
  );

  const dismiss = useCallback(
    (id: string) => setPending((prev) => prev.filter((p) => p.id !== id)),
    [],
  );

  return (
    <UploadContext.Provider value={{ pending, uploadFiles, retry, dismiss }}>
      {children}
    </UploadContext.Provider>
  );
}

export function useUpload(): UploadContextValue {
  const ctx = useContext(UploadContext);
  if (!ctx) throw new Error("useUpload must be used within an UploadProvider");
  return ctx;
}
