import { Metadata } from 'next';

import { Container } from '@/components/common/container';

import { WalkthroughScreen } from './components/WalkthroughScreen';

export const metadata: Metadata = {
  title: 'Showroom Walkthrough',
  description: 'Walk through a showroom, one panoramic stop at a time.',
};

export default async function DealerKitWalkthroughRoute({
  params,
}: {
  params: Promise<{ walkthroughId: string }>;
}) {
  const { walkthroughId } = await params;

  return (
    <Container width="fluid">
      <WalkthroughScreen walkthroughId={walkthroughId} />
    </Container>
  );
}
