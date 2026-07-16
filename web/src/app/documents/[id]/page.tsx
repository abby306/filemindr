import { DocumentScreen } from "@/components/documents/document-screen";

/** Document view — split source ⇄ card. `?p=N` lands on a page (from a citation).
 *  `params`/`searchParams` are async in Next 16. */
export default async function DocumentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ p?: string; fact?: string }>;
}) {
  const { id } = await params;
  const { p, fact } = await searchParams;
  const parsed = p ? Number.parseInt(p, 10) : NaN;
  return (
    <DocumentScreen
      documentId={id}
      initialPage={Number.isFinite(parsed) ? parsed : undefined}
      initialFact={fact}
    />
  );
}
