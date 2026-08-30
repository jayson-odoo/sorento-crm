import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { TagTemplatesList } from './components/TagTemplatesList';

export const metadata: Metadata = {
  title: 'Tag Templates',
  description: 'Manage price tag templates for different product families.',
};

export default function TagTemplatesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Tag Templates" />
      </Container>

      <Container>
        <TagTemplatesList />
      </Container>
    </>
  );
}
