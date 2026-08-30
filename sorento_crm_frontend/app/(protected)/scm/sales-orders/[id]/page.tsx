import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { SalesOrderDetail } from './components/SalesOrderDetail';

export const metadata: Metadata = {
  title: 'Sales Order',
  description: 'Sales order detail - header, lines and delivery.',
};

export default async function SalesOrderDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <>
      <Container>
        <PageHeader
          title="Sales Order"
          actions={
            <BackToList listPath="/scm/sales-orders" label="Back to sales orders" />
          }
        />
      </Container>

      <Container>
        <SalesOrderDetail id={id} />
      </Container>
    </>
  );
}
