import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import LookupSetsList from './components/LookupSetsList';

export const metadata: Metadata = {
  title: 'Lookup Sets',
  description: 'Configure dropdown master data, options, and keyword mappings.',
};

export default function LookupSetsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Lookup Sets" />
      </Container>
      <Container>
        <LookupSetsList />
      </Container>
    </>
  );
}
