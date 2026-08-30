import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import CustomersList from './components/CustomersList';

export const metadata: Metadata = {
  title: 'Customers',
  description: 'Manage customers.',
};

export default async function CustomersPage() {
  return (
    <>
      <Container>
        <PageHeader title="Customers" />
      </Container>

      <Container>
        <CustomersList />
      </Container>
    </>
  );
}
