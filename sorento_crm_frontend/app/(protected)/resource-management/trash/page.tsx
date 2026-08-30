import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import TrashView from './components/TrashView';

export const metadata: Metadata = {
  title: 'Trash',
  description: 'View and restore deleted folders and attachments.',
};

export default function TrashPage() {
  return (
    <>
      <Container>
        <PageHeader title="Trash" />
      </Container>

      <Container className="flex flex-col flex-1 min-h-0">
        <TrashView />
      </Container>
    </>
  );
}
