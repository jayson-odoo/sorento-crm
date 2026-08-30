import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ContactAccessTypesAdmin from './components/ContactAccessTypesAdmin';

export const metadata: Metadata = {
  title: 'Contact Access Types',
  description: 'Configure contact access types and Respond.io mappings.',
};

export default async function Page() {
  return (
    <>
      <Container>
        <PageHeader title="Contact Access Types" />
      </Container>
      <Container>
        <ContactAccessTypesAdmin />
      </Container>
    </>
  );
}
