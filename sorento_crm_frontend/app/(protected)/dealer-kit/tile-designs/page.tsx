import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { TileDesignsList } from './components/TileDesignsList';

export const metadata: Metadata = {
  title: 'Tile Designs',
  description: 'What each product card shows on a catalogue page.',
};

export default function DealerKitTileDesignsPage() {
  return (
    <Container width="fluid">
      <PageHeader title="Tile Designs" />

      <TileDesignsList />
    </Container>
  );
}
