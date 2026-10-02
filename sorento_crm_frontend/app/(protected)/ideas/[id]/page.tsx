import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { IdeaDetail } from '@/components/ideas/IdeaDetail';

export const metadata: Metadata = {
  title: 'Idea',
  description: 'View an idea.',
};

export default async function IdeaDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <Container>
        <PageHeader title="Idea" actions={<BackToList listPath="/ideas" label="Back to ideas" />} />
      </Container>
      <Container>
        <IdeaDetail id={id} />
      </Container>
    </>
  );
}
