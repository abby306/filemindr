"use client";

/**
 * UploadScreen — intake surface + a live "Recent" shelf. Optimistic uploading /
 * error cards sit ahead of the real documents feed; freshly-uploaded documents
 * appear as manila cards that animate through Pipeline fill as the backend
 * processes them. Fully never-wait: navigate away any time; the dock persists.
 */

import { PageScaffold } from "@/components/page-scaffold";
import { Skeleton } from "@/components/ui/skeleton";
import { DocumentCard } from "@/components/archive/document-card";
import { Dropzone } from "@/components/upload/dropzone";
import { UploadingCard } from "@/components/upload/uploading-card";
import { useDocumentsFeed } from "@/features/upload/queries";
import { useUpload } from "@/features/upload/upload-context";
import { isProcessing } from "@/features/archive/taxonomy";

export function UploadScreen() {
  const { pending, retry, dismiss } = useUpload();
  const { data: docs, isPending, isError } = useDocumentsFeed();

  const filed = (docs ?? []).filter((d) => d.status === "indexed").length;
  const working =
    pending.filter((p) => p.state === "uploading").length +
    (docs ?? []).filter((d) => isProcessing(d.status)).length;

  return (
    <PageScaffold
      eyebrow="Intake"
      title="Upload"
      lede="Drop files here — they file themselves. Keep working while they process."
    >
      <Dropzone />

      <section className="mt-10">
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="type-title2 text-text-1">Recent</h2>
          <p className="type-caption text-text-3">
            {working > 0 ? `${working} processing · ` : ""}
            {filed} filed
          </p>
        </div>

        {isPending ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-40 w-full" />
            ))}
          </div>
        ) : isError && pending.length === 0 ? (
          <p className="type-callout text-text-3">
            Couldn&apos;t load recent documents.
          </p>
        ) : pending.length === 0 && (docs?.length ?? 0) === 0 ? (
          <p className="type-callout text-text-3">
            Nothing yet — your uploads will show up here.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {pending.map((entry) => (
              <UploadingCard
                key={entry.id}
                entry={entry}
                onRetry={retry}
                onDismiss={dismiss}
              />
            ))}
            {(docs ?? []).map((doc) => (
              <DocumentCard key={doc.id} doc={doc} />
            ))}
          </div>
        )}
      </section>
    </PageScaffold>
  );
}
