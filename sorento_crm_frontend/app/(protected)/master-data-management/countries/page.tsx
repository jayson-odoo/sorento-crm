import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import CountryList from './components/CountryList';

export const metadata: Metadata = {
  title: 'Countries',
  description: 'Manage countries.',
};

export default async function CountriesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Countries" />
      </Container>

      <Container>
        <CountryList />
      </Container>
    </>
  );
}
