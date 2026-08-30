import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import AttachmentBrowser from './components/AttachmentBrowser';

export const metadata: Metadata = {
  title: 'Attachments',
  description: 'Manage attachments.',
};

export default async function AttachmentsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Attachments" />
      </Container>

      <Container>
        <AttachmentBrowser />
      </Container>
    </>
  );
}
