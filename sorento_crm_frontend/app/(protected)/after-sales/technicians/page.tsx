import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import TechniciansList from './components/TechniciansList';

export const metadata: Metadata = {
  title: 'Technicians',
};

export default function TechniciansPage() {
  return (
    <>
      <Container>
        <PageHeader title="Technicians" />
      </Container>
      <Container>
        <TechniciansList />
      </Container>
    </>
  );
}
