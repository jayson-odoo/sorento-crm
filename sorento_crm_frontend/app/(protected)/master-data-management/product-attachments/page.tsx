import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ProductAttachmentsList from './components/ProductAttachmentsList';

export const metadata: Metadata = {
  title: 'Product Attachments',
  description: 'Manage product attachment relationships.',
};

export default function ProductAttachmentsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Product Attachments" />
      </Container>

      <Container>
        <ProductAttachmentsList />
      </Container>
    </>
  );
}
