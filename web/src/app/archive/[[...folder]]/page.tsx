import { ArchiveScreen } from "@/components/archive/archive-screen";

/**
 * Archive route — optional catch-all so /archive (All), /archive/needs-review,
 * and /archive/{class-slug} all resolve here. Only the first segment selects a
 * folder. `params` is async in Next 16.
 */
export default async function ArchivePage({
  params,
}: {
  params: Promise<{ folder?: string[] }>;
}) {
  const { folder } = await params;
  return <ArchiveScreen folderSegment={folder?.[0]} />;
}
