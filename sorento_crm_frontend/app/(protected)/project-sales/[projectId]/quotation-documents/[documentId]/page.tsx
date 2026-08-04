import { Metadata } from 'next';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { QuotationDocumentClient } from './components/QuotationDocumentClient';
import { QuotationDocumentCrumb } from './components/QuotationDocumentCrumb';

export const metadata: Metadata = {
  title: 'Quotation document',
  description: 'One letterhead, the scopes priced under it, and the revisions issued from it.',
};

/**
 * A page, not a panel under the list.
 *
 * The Quotations tab lists what the project has; this answers what is in ONE of them. The
 * client's words: "please don't make quotation list and form in 1 page, click on the list, then
 * go to another page to view it".
 */
export default async function ProjectQuotationDocumentPage({
  params,
}: {
  params: Promise<{ projectId: string; documentId: string }>;
}) {
  const { projectId, documentId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6 pb-64">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink href="/">Home</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink href="/project-sales/pipeline">Project Sales</BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink href={`/project-sales/${projectId}?tab=quotations`}>
                Quotations
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <QuotationDocumentCrumb projectId={projectId} documentId={documentId} />
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <QuotationDocumentClient projectId={projectId} documentId={documentId} />
      </Container>
    </RequireAccess>
  );
}
