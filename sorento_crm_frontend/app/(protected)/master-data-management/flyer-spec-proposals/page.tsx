import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { FlyerSpecBatchesList } from './components/FlyerSpecBatchesList';

export const metadata: Metadata = {
  title: 'Flyer Spec Proposals',
  description:
    'What each flyer says about the product master, ready to review.',
};

export default function FlyerSpecProposalsPage() {
  return (
    <Container width="fluid">
      <PageHeader title="Flyer Spec Proposals" />

      <FlyerSpecBatchesList />
    </Container>
  );
}
