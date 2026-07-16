import Link from "next/link";
import { FileQuestion } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex min-h-full flex-col items-center justify-center px-6 py-16 text-center">
      <span className="flex size-12 items-center justify-center rounded-lg bg-surface-2 text-text-3">
        <FileQuestion aria-hidden className="size-6" strokeWidth={1.5} />
      </span>
      <h1 className="mt-4 type-title2 text-text-1">Page not found</h1>
      <p className="mt-1 max-w-sm type-callout text-text-2">
        That page doesn&apos;t exist — or hasn&apos;t been built yet.
      </p>
      <Link
        href="/"
        className="mt-5 flex min-h-11 items-center rounded-md bg-accent px-4 type-subhead text-on-accent transition-colors hover:bg-accent-hover"
      >
        Back to Upload
      </Link>
    </div>
  );
}
