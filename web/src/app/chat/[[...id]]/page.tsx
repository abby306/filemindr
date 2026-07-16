import { AskScreen } from "@/components/ask/ask-screen";

/** Ask route — /chat (new), /chat/{id} (continue), ?doc={id} (scope to a document).
 *  `params`/`searchParams` are async in Next 16. */
export default async function ChatPage({
  params,
  searchParams,
}: {
  params: Promise<{ id?: string[] }>;
  searchParams: Promise<{ doc?: string }>;
}) {
  const { id } = await params;
  const { doc } = await searchParams;
  return (
    <AskScreen conversationId={id?.[0] ?? null} scopedDocumentId={doc ?? null} />
  );
}
