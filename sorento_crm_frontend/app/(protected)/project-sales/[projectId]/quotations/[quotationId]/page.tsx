import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import BackToList from '@/components/common/BackToList';
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
        {/* Crumbs left, one Back right (D6, S3-01). The Back carries the query
            string the list handed over, so it returns to the tab and page the
            reader left. */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <PageHeader title="Quotation" />
          <BackToList
            listPath={`/project-sales/${projectId}?tab=quotations`}
            label="Back to quotations"
            // The path already names the tab; the pager's own params would only
            // fight it, so nothing is appended.
            appendListState={false}
          />
        </div>
        <QuotationDetailClient projectId={projectId} quotationId={quotationId} />
      </Container>
    </RequireAccess>
  );
}
