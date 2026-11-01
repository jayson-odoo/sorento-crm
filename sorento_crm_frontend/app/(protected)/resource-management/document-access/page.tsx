import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { DocumentAccessView } from './components/DocumentAccessView';

export const metadata: Metadata = {
  title: 'Document Access',
  description: 'Who the AI may read each document type for.',
};

export default function DocumentAccessPage() {
  return (
    <Container>
      <DocumentAccessView />
    </Container>
  );
}
