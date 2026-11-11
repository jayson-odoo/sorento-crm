import { Metadata } from 'next';
import Link from 'next/link';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { Button } from '@/components/ui/button';
import SampleRequestForm from '../components/SampleRequestForm';

export const metadata: Metadata = {
  title: 'New Sample Request',
  description: 'Create a sample request',
};

export default async function NewSampleRequestPage({
  searchParams,
}: {
  searchParams: Promise<{ project_id?: string }>;
}) {
  const { project_id } = await searchParams;
  // Opened from a project's Sample Submission stage button: Cancel goes back to that project's
  // Samples Request tab (PROJECT-STAGE-ACTIONS).
  const backHref = project_id
    ? `/project-sales/${encodeURIComponent(project_id)}?tab=sample-requests`
    : '/project-sales/sample-requests';
  return (
    <Container>
      <PageHeader
        title="New Sample Request"
        actions={
          <Button variant="outline" asChild>
            <Link href={backHref}>Cancel</Link>
          </Button>
        }
      />
      <div className="mt-6">
        <SampleRequestForm projectId={project_id} />
      </div>
    </Container>
  );
}
