import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import RequireAccess from '@/app/components/common/RequireAccess';
import { PriceFloorsListClient } from './components/PriceFloorsListClient';

/**
 * Price floors, on their own page.
 *
 * Split out of the old combined "Pricing policy" screen: floors are a different policy about
 * different products from a series, and sharing one page made both harder to read. No
 * explanatory subtitle, on the client's standing rule.
 */
export const metadata = { title: 'Price Floors' };

export default function Page() {
  return (
    <RequireAccess permission="projects.types.view">
      <Container>
        <PageHeader title="Price Floors" />
      </Container>

      <Container>
        <PriceFloorsListClient />
      </Container>
    </RequireAccess>
  );
}
