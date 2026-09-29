'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import { CostPriceChangeSetDetail } from './components/CostPriceChangeSetDetail';

export default function CostPriceChangeSetPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <Container>
      <CostPriceChangeSetDetail changeSetId={id} />
    </Container>
  );
}
