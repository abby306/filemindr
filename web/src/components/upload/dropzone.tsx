"use client";

/**
 * Dropzone — the single intake surface: drag-and-drop, click-to-browse, and
 * paste all funnel into `uploadFiles`. Keyboard-operable (Enter/Space opens the
 * picker) and announces its accepted types. Highlights on drag-over.
 */

import { useEffect, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import clsx from "clsx";

import { useUpload } from "@/features/upload/upload-context";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.docx";

export function Dropzone() {
  const { uploadFiles } = useUpload();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  // Paste-to-upload (images/files from the clipboard) while this screen is open.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const files = e.clipboardData?.files;
      if (files && files.length > 0) uploadFiles(files);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [uploadFiles]);

  const openPicker = () => inputRef.current?.click();

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Upload documents: drop files, or activate to browse"
      onClick={openPicker}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openPicker();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (e.dataTransfer.files?.length) uploadFiles(e.dataTransfer.files);
      }}
      className={clsx(
        "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors duration-[var(--dur-base)]",
        dragging
          ? "border-accent bg-accent-50"
          : "border-border-strong bg-card/60 hover:border-accent-300 hover:bg-card",
      )}
    >
      <span
        className={clsx(
          "flex size-14 items-center justify-center rounded-full transition-colors",
          dragging ? "bg-accent text-p-0" : "bg-surface-2 text-accent",
        )}
      >
        <UploadCloud aria-hidden className="size-7" strokeWidth={1.5} />
      </span>
      <div>
        <p className="type-title3 text-text-1">
          {dragging ? "Drop to file them" : "Drop files here"}
        </p>
        <p className="mt-1 type-callout text-text-2">
          or click to browse · paste works too
        </p>
      </div>
      <p className="type-caption text-text-3">PDF, PNG, JPG, DOCX · up to 50 MB</p>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="sr-only"
        onChange={(e) => {
          if (e.target.files?.length) uploadFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
