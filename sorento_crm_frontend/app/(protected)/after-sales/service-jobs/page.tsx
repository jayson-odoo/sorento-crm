import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ServiceJobsList from './components/ServiceJobsList';

export const metadata: Metadata = {
  title: 'Service Jobs',
};

export default function ServiceJobsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Service Jobs" />
      </Container>
      <Container>
        <ServiceJobsList />
      </Container>
    </>
  );
}
