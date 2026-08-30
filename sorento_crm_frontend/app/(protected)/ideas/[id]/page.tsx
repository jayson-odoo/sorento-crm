import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { IdeationEmbed } from '@/components/ideas/IdeationEmbed';

export const metadata: Metadata = {
  title: 'Idea',
  description: 'View an idea.',
};

// The `{id}` param is opaque plumbing (the product-domain deep-link shape, §5.3);
// it is NOT rendered as visible UI text - the human-readable content is the iframe's (AC-41/D-8).
export default async function IdeaDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <>
      <Container>
        <PageHeader title="Idea" />
      </Container>

      <Container>
        <IdeationEmbed ideaId={id} title="Idea detail" />
      </Container>
    </>
  );
}
