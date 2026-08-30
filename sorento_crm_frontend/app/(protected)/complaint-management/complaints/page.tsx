import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ComplaintsList from './components/ComplaintsList';

export const metadata: Metadata = {
  title: 'Complaints',
  description: 'Manage customer complaints',
};

export default function ComplaintsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Complaints" />
      </Container>

      <Container>
        <ComplaintsList />
      </Container>
    </>
  );
}
