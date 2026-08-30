import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import BackToList from '@/components/common/BackToList';
import { LeadDetailClient } from './components/LeadDetailClient';

export const metadata: Metadata = {
  title: 'Lead',
  description: 'A recorded sighting, who told us, and what it became.',
};

export default async function ProjectLeadDetailPage({
  params,
}: {
  params: Promise<{ leadId: string }>;
}) {
  const { leadId } = await params;
  return (
    <RequireAccess permission="projects.projects.view">
      <Container className="space-y-6">
        {/* Crumbs left, one Back right (D6, S3-01). The Back carries the list's
            query string, so it returns to the page the reader left. */}
        <PageHeader
          title="Lead"
          actions={
            <BackToList listPath="/project-sales/leads" label="Back to leads" />
          }
        />
        <LeadDetailClient leadId={leadId} />
      </Container>
    </RequireAccess>
  );
}
