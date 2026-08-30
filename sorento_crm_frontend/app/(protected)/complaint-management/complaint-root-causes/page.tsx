import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ComplaintRootCausesList from './components/ComplaintRootCausesList';

export const metadata: Metadata = {
  title: 'Complaint Root Causes',
  description: 'Manage complaint root cause master data.',
};

export default async function ComplaintRootCausesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Root Causes" />
      </Container>

      <Container>
        <ComplaintRootCausesList />
      </Container>
    </>
  );
}
