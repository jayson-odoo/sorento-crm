import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SuppliersList from './components/SuppliersList';

export const metadata: Metadata = {
  title: 'Suppliers',
  description: 'Manage suppliers.',
};

export default async function SuppliersPage() {
  return (
    <>
      <Container>
        <PageHeader title="Suppliers" />
      </Container>

      <Container>
        <SuppliersList />
      </Container>
    </>
  );
}
