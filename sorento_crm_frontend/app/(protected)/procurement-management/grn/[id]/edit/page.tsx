'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import GRNForm from '../../components/GRNForm';

type EditGRNPageProps = {
  params: Promise<{ id: string }>;
};

export default function EditGRNPage({ params }: EditGRNPageProps) {
  const { id } = use(params);

  return (
    <Container>
      <PageHeader title="Edit Goods Receipt Note" eyebrow="GRN" />
      <Container>
        <GRNForm grnId={id} />
      </Container>
    </Container>
  );
}
