import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ContactsList from './components/ContactsList';

export const metadata: Metadata = {
  title: 'Internal Users',
  description: 'View internal users (respond contacts).',
};

export default async function ContactsPage() {
  return (
    <>
      <Container width="fluid">
        <PageHeader title="Internal Users" />
      </Container>

      <Container width="fluid">
        <ContactsList />
      </Container>
    </>
  );
}
