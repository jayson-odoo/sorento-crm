import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SLAPoliciesList from './components/SLAPoliciesList';

export const metadata: Metadata = {
  title: 'SLA Policies',
  description: 'Manage SLA policies.',
};

export default async function SLAPoliciesPage() {
  return (
    <>
      <Container>
        <PageHeader title="SLA Policies" />
      </Container>

      <Container>
        <SLAPoliciesList />
      </Container>
    </>
  );
}
