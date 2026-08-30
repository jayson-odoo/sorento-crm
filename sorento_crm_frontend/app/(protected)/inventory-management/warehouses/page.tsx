import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import WarehousesList from './components/WarehousesList';

export const metadata: Metadata = {
  title: 'Warehouses',
  description: 'Manage warehouses.',
};

export default async function WarehousesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Warehouses" />
      </Container>

      <Container>
        <WarehousesList />
      </Container>
    </>
  );
}
