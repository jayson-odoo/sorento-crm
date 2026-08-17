import { Metadata } from 'next';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Container } from '@/components/common/container';
import RequireAccess from '@/app/components/common/RequireAccess';
import { QuotationDetailClient } from './components/QuotationDetailClient';

export const metadata: Metadata = {
  title: 'Quotation',
  description: 'One priced scope, its revisions and the lines on each.',
};

/**
 * A page, not a panel under the list.
 *
 * The Quotations tab used to render the list AND the open scope's line editor on the same
 * screen. The client's words: "please don't make quotation list and form in 1 page, click on
 * the list, then go to another page to view it". A list answers "what do we have"; a form
 * answers "what is in this one", and stacking them makes both cramped.
 */
export default async function ProjectQuotationPage({
  params,
}: {
  params: Promise<{ projectId: string; quotationId: string }>;
}) {
  const { projectId, quotationId } = await params;
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
              <BreadcrumbPage>Scope</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <QuotationDetailClient projectId={projectId} quotationId={quotationId} />
      </Container>
    </RequireAccess>
  );
}
