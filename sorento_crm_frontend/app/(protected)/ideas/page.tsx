import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { IdeationEmbed } from '@/components/ideas/IdeationEmbed';

export const metadata: Metadata = {
  title: 'Ideas',
  description: 'Share and explore product ideas.',
};

export default function IdeasBoardPage() {
  // No outer toolbar/breadcrumb — the embedded Ideas workspace renders its own
  // heading; a second "Ideas" title above the iframe was redundant.
  return (
    <Container width="fluid">
      <IdeationEmbed title="Ideas board" />
    </Container>
  );
}
