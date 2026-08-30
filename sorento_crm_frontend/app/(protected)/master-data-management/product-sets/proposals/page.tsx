import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ProductSetProposals from '../components/ProductSetProposals';

export const metadata: Metadata = {
  title: 'Propose Product Sets',
  description: 'Candidate sets derived from the catalogue, for a person to accept.',
};

export default async function ProductSetProposalsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Propose Product Sets" />
      </Container>

      <Container>
        <ProductSetProposals />
      </Container>
    </>
  );
}
