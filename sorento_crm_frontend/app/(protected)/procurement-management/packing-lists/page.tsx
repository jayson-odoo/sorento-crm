import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PackingListsList from './components/PackingListsList';

export const metadata: Metadata = {
  title: 'Packing Lists',
  description: 'Manage inbound shipments and packing lists',
};

export default function PackingListsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Packing Lists" />
      </Container>

      <Container>
        <PackingListsList />
      </Container>
    </>
  );
}
