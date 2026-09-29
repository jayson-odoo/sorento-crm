import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BranchesList from './components/BranchesList';

export const metadata: Metadata = {
  title: 'Customer Branches',
  description: 'Customer branches from AutoCount.',
};

export default async function BranchesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Customer Branches" />
      </Container>

      <Container>
        <BranchesList />
      </Container>
    </>
  );
}
