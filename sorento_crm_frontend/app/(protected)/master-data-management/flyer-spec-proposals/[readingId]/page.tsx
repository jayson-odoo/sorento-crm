import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { FlyerSpecReviewScreen } from '../components/FlyerSpecReviewScreen';

export const metadata: Metadata = {
  title: 'Review Flyer Specs',
  description:
    'Review what a flyer says about each product, then write the rows you tick.',
};

export default async function FlyerSpecProposalsReviewRoute({
  params,
}: {
  params: Promise<{ readingId: string }>;
}) {
  const { readingId } = await params;

  return (
    <Container width="fluid">
      <PageHeader title="Review Flyer Specs" />

      <FlyerSpecReviewScreen readingId={readingId} />
    </Container>
  );
}
