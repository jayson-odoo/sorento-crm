import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { FlyerReadingsList } from './components/FlyerReadingsList';

export const metadata: Metadata = {
  title: 'Flyers',
  description: 'Turn a printed flyer into a draft brochure.',
};

export default function DealerKitFlyerReadingsPage() {
  return (
    <Container width="fluid">
      <PageHeader title="Flyers" />

      <FlyerReadingsList />
    </Container>
  );
}
