import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PriceTagRequestsList from './components/PriceTagRequestsList';

export const metadata: Metadata = {
  title: 'Price Tag Requests',
  description: 'Manage price tag requests from salespersons',
};

export default function PriceTagRequestsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Price Tag Requests" />
      </Container>

      <Container>
        <PriceTagRequestsList />
      </Container>
    </>
  );
}
