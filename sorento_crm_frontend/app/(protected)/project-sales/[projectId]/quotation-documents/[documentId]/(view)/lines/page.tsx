import { redirect } from 'next/navigation';

/**
 * The Lines tab is gone (PROPOSAL-HEADER-LAYOUT, owner 5 Nov 2026): the lines sit on the Header
 * tab under the letterhead. An old link or bookmark to /lines lands there.
 */
export default async function ProjectQuotationLinesPage({
  params,
}: {
  params: Promise<{ projectId: string; documentId: string }>;
}) {
  const { projectId, documentId } = await params;
  redirect(`/project-sales/${projectId}/quotation-documents/${documentId}`);
}
