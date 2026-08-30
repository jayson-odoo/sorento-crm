import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import AttachmentTypesList from './components/AttachmentTypesList';

export const metadata: Metadata = {
  title: 'Attachment Types',
  description: 'Manage attachment types.',
};

export default async function AttachmentTypesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Attachment Types" />
      </Container>

      <Container>
        <AttachmentTypesList />
      </Container>
    </>
  );
}
