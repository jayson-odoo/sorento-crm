import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import FormsList from './components/FormsList';

export const metadata: Metadata = {
  title: 'Forms',
  description: 'Manage forms.',
};

export default async function FormsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Forms" />
      </Container>

      <Container>
        <FormsList />
      </Container>
    </>
  );
}
