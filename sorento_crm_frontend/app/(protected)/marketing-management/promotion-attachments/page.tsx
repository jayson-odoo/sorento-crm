import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PromotionAttachmentsList from './components/PromotionAttachmentsList';

export const metadata: Metadata = {
  title: 'Promotion Attachments | Sorento CRM',
};

export default function PromotionAttachmentsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Promotion Attachments" />
      </Container>

      <Container>
        <PromotionAttachmentsList />
      </Container>
    </>
  );
}
