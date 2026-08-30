'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import PromotionDetail from '../components/PromotionDetail';

export default function PromotionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <>
      <Container>
        <PageHeader
          title="Promotion"
          actions={
            <BackToList
              listPath="/marketing-management/promotions"
              label="Back to promotions"
            />
          }
        />
      </Container>
      <Container>
        <PromotionDetail promotionId={id} />
      </Container>
    </>
  );
}
