import { redirect } from 'next/navigation';

/**
 * The separate Edit page screen is gone: the reader is the editor. An old link (the reader used to
 * link here with the page's key) lands on the reader, scrolled to that page.
 */
export default async function EditProjectQuotationSpecSheetPage({
  params,
}: {
  params: Promise<{ projectId: string; documentId: string; sheetId: string; key: string }>;
}) {
  const { projectId, documentId, sheetId, key } = await params;
  // A server page receives the segment still encoded; decode it once, then encode it for the query.
  let pageKey = key;
  try {
    pageKey = decodeURIComponent(key);
  } catch {
    // A malformed escape is passed on as it is; the reader finds no such page and stays at the top.
  }
  redirect(
    `/project-sales/${projectId}/quotation-documents/${documentId}/spec-sheet/${sheetId}?page=${encodeURIComponent(pageKey)}`,
  );
}
