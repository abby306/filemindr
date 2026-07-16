"use client";

/**
 * SourcePane — the left half of the document view: the rendered source page(s).
 * Page images come from `GET /documents/{id}/pages/{n}`, which needs the auth
 * headers, so we fetch each page as a blob through the API seam and show it via
 * an object URL (a bare <img src> can't send headers). Provenance jumps flash a
 * highlighter wash over the page (bbox-level SourceGlow lands with the fact→bbox
 * endpoint). Types with no page image (docx) fall back to a download.
 */

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Download, FileText } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useAccount } from "@/lib/account/account-context";
import { apiRequest } from "@/lib/api/client";

const DPI = 150;

function isRenderable(mime: string | null): boolean {
  return mime === "application/pdf" || (!!mime && mime.startsWith("image/"));
}

export function SourcePane({
  documentId,
  filename,
  mimeType,
  pageCount,
  page,
  onPageChange,
  flashKey,
  highlightBbox,
}: {
  documentId: string;
  filename: string;
  mimeType: string | null;
  pageCount: number | null;
  page: number;
  onPageChange: (page: number) => void;
  flashKey: number;
  /** Normalized [x,y,w,h] to sweep a highlighter over on this page (SourceGlow). */
  highlightBbox?: number[] | null;
}) {
  const { account } = useAccount();
  const total = pageCount && pageCount > 0 ? pageCount : 1;
  const renderable = isRenderable(mimeType);

  // State is set only in async callbacks; loading is derived from "which page is
  // currently loaded" so there's no synchronous setState inside the effect.
  const [loaded, setLoaded] = useState<{ page: number; url: string } | null>(null);
  const [errorPage, setErrorPage] = useState<number | null>(null);

  useEffect(() => {
    if (!renderable) return;
    let active = true;
    let objectUrl: string | undefined;
    apiRequest(`/api/v1/documents/${documentId}/pages/${page}?dpi=${DPI}`, {
      accountId: account.id,
    })
      .then((res) => res.blob())
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setLoaded({ page, url: objectUrl });
      })
      .catch(() => active && setErrorPage(page));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId, page, account.id, renderable]);

  const state =
    errorPage === page ? "error" : loaded?.page === page ? "ready" : "loading";
  const url = loaded?.page === page ? loaded.url : null;

  if (!renderable) {
    return (
      <Fallback documentId={documentId} filename={filename} accountId={account.id} />
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="relative flex-1 overflow-auto rounded-lg border border-border bg-surface-2 p-4">
        {state === "loading" ? (
          <Skeleton className="mx-auto aspect-[3/4] w-full max-w-md" />
        ) : state === "error" ? (
          <p className="py-16 text-center type-callout text-text-3">
            Couldn’t render this page.
          </p>
        ) : (
          <div className="relative mx-auto w-fit">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={url ?? ""}
              alt={`${filename} — page ${page}`}
              className="mx-auto max-w-full rounded-md shadow-e1"
            />
            {/* SourceGlow: a highlighter sweep over the exact cited region, or a
                page-level wash when the bbox is unavailable. */}
            {highlightBbox ? (
              <span
                key={`${page}-${highlightBbox.join(",")}`}
                aria-hidden
                className="animate-source-sweep pointer-events-none absolute rounded-[2px] bg-hl-wash mix-blend-multiply"
                style={{
                  left: `${highlightBbox[0] * 100}%`,
                  top: `${highlightBbox[1] * 100}%`,
                  width: `${highlightBbox[2] * 100}%`,
                  height: `${highlightBbox[3] * 100}%`,
                }}
              />
            ) : flashKey > 0 ? (
              <span
                key={flashKey}
                aria-hidden
                className="animate-source-flash pointer-events-none absolute inset-0 rounded-md bg-hl-wash"
              />
            ) : null}
          </div>
        )}
      </div>

      {total > 1 ? (
        <div className="mt-3 flex items-center justify-center gap-4">
          <button
            type="button"
            aria-label="Previous page"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            className="flex size-11 items-center justify-center rounded-md border border-border bg-surface text-text-2 transition-colors hover:bg-surface-2 disabled:opacity-40 sm:size-9"
          >
            <ChevronLeft aria-hidden className="size-4" />
          </button>
          <span className="type-data text-text-3">
            {page} / {total}
          </span>
          <button
            type="button"
            aria-label="Next page"
            disabled={page >= total}
            onClick={() => onPageChange(page + 1)}
            className="flex size-11 items-center justify-center rounded-md border border-border bg-surface text-text-2 transition-colors hover:bg-surface-2 disabled:opacity-40 sm:size-9"
          >
            <ChevronRight aria-hidden className="size-4" />
          </button>
        </div>
      ) : null}
    </div>
  );
}

function Fallback({
  documentId,
  filename,
  accountId,
}: {
  documentId: string;
  filename: string;
  accountId: string;
}) {
  const download = async () => {
    const res = await apiRequest(`/api/v1/documents/${documentId}/file`, { accountId });
    const blob = await res.blob();
    const href = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = href;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(href);
  };

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-border-strong bg-surface-2 p-8 text-center">
      <span className="flex size-12 items-center justify-center rounded-lg bg-surface text-text-3">
        <FileText aria-hidden className="size-6" strokeWidth={1.5} />
      </span>
      <p className="type-callout text-text-2">No page preview for this file type.</p>
      <button
        type="button"
        onClick={download}
        className="flex min-h-10 items-center gap-2 rounded-md bg-accent px-4 type-subhead text-on-accent transition-colors hover:bg-accent-hover"
      >
        <Download aria-hidden className="size-4" />
        Download original
      </button>
    </div>
  );
}
