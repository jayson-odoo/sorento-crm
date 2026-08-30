import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import MarketSegmentsAdmin from './components/MarketSegmentsAdmin';

export const metadata: Metadata = {
  title: 'Market Segments',
  description: 'Manage market segments used for customer-service routing.',
};

export default async function Page() {
  return (
    <>
      <Container>
        <PageHeader title="Market Segments" />
      </Container>
      <Container>
        <MarketSegmentsAdmin />
      </Container>
    </>
  );
}
