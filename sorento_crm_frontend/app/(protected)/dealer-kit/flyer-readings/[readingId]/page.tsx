import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { FlyerReviewScreen } from './components/FlyerReviewScreen';

export const metadata: Metadata = {
  title: 'Review Flyer',
  description: 'Check what the system read off a flyer, then seed a draft brochure from it.',
};

export default async function DealerKitFlyerReviewRoute({
  params,
}: {
  params: Promise<{ readingId: string }>;
}) {
  const { readingId } = await params;

  return (
    <Container width="fluid">
      <PageHeader title="Review Flyer" />

      <FlyerReviewScreen readingId={readingId} />
    </Container>
  );
}
