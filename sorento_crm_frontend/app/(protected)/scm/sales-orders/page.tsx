import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SalesOrdersList from './components/SalesOrdersList';

export const metadata: Metadata = {
  title: 'Sales Orders',
  description: 'Manage sales orders - the committed-demand business record.',
};

export default function SalesOrdersPage() {
  return (
    <>
      <Container>
        <PageHeader title="Sales Orders" />
      </Container>

      <Container>
        <SalesOrdersList />
      </Container>
    </>
  );
}
