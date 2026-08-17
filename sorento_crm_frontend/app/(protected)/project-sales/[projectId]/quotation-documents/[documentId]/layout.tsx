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
 *
 * A LAYOUT rather than a page because the document reads as four tabs - scopes, cover letter,
 * terms, signatures - and the client asked for each to be reachable without scrolling past fifty
 * priced lines. The tabs are routes under here, so the terms can be linked to directly and Back
 * walks through them. What sits above them - the refs, the recipient, the total, the CTA - is the
 * identity of the record, so it is rendered once here and stays on screen on every tab.
 */
export default async function ProjectQuotationDocumentLayout({
  params,
  children,
}: {
  params: Promise<{ projectId: string; documentId: string }>;
  children: React.ReactNode;
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
        <QuotationDocumentClient projectId={projectId} documentId={documentId}>
          {children}
        </QuotationDocumentClient>
      </Container>
    </RequireAccess>
  );
}
