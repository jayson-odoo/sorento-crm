import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ItemClassList from './components/ItemClassList';

export const metadata: Metadata = {
  title: 'Item Classes',
  description: 'Manage item classes.',
};

export default async function ItemClassesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Item Classes" />
      </Container>

      <Container>
        <ItemClassList />
      </Container>
    </>
  );
}
