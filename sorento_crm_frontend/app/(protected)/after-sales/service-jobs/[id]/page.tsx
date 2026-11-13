import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import ServiceJobDetail from '../components/ServiceJobDetail';

export const metadata: Metadata = {
  title: 'Service Job',
};

export default async function ServiceJobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Container>
      <PageHeader
        title="Service Job"
        actions={<BackToList listPath="/after-sales/service-jobs" label="Back to service jobs" />}
      />
      <div className="mt-6">
        <ServiceJobDetail jobId={id} />
      </div>
    </Container>
  );
}
