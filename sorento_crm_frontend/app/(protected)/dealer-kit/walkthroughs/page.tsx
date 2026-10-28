import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { WalkthroughsList } from './components/WalkthroughsList';

export const metadata: Metadata = {
  title: 'Showroom Walkthroughs',
  description: 'Panoramic showroom tours built from video or photos.',
};

export default function DealerKitWalkthroughsPage() {
  return (
    <Container width="fluid">
      <PageHeader title="Showroom Walkthroughs" />

      <WalkthroughsList />
    </Container>
  );
}
