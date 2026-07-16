"use client";

/**
 * PageThumb — a document's first page at thumbnail size. The pages endpoint
 * needs auth headers, so the image is fetched as a blob through the API seam
 * and shown via an object URL, cached per document for the session (object URLs
 * are deliberately never revoked — that's the cache). Types with no page image
 * (docx → 415) and hard failures fall back to a neutral file glyph; transient
 * errors are not cached so a retry can succeed on the next mount.
 */

import { useEffect, useState } from "react";
import { FileText } from "lucide-react";
import clsx from "clsx";

import { useAccount } from "@/lib/account/account-context";
import { ApiError, apiRequest } from "@/lib/api/client";

const DPI = 72;

/** document id → object URL, or "none" when the type has no page image. */
const thumbCache = new Map<string, string | "none">();

function isRenderable(mime: string | null): boolean {
  return mime === "application/pdf" || (!!mime && mime.startsWith("image/"));
}

export function PageThumb({
  documentId,
  mimeType,
  className,
}: {
  documentId: string;
  mimeType: string | null;
  /** Sizing comes from the caller; the thumb fills it with object-cover. */
  className?: string;
}) {
  const { account } = useAccount();
  const [state, setState] = useState<string | "none" | "loading">(
    () => thumbCache.get(documentId) ?? (isRenderable(mimeType) ? "loading" : "none"),
  );

  useEffect(() => {
    if (!isRenderable(mimeType) || thumbCache.has(documentId)) return;
    let active = true;
    apiRequest(`/api/v1/documents/${documentId}/pages/1?dpi=${DPI}`, {
      accountId: account.id,
    })
      .then((res) => res.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        thumbCache.set(documentId, url);
        if (active) setState(url);
      })
      .catch((err) => {
        // 415 (no page image) / 404 (file gone) are permanent for this doc.
        if (err instanceof ApiError && (err.status === 415 || err.status === 404)) {
          thumbCache.set(documentId, "none");
        }
        if (active) setState("none");
      });
    return () => {
      active = false;
    };
  }, [documentId, mimeType, account.id]);

  return (
    <span
      aria-hidden
      className={clsx(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-[4px] border border-border bg-surface-2",
        className,
      )}
    >
      {state === "loading" ? (
        <span className="animate-skeleton size-full" />
      ) : state === "none" ? (
        <FileText className="size-4 text-text-3" strokeWidth={1.5} />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={state} alt="" className="size-full object-cover object-top" />
      )}
    </span>
  );
}
