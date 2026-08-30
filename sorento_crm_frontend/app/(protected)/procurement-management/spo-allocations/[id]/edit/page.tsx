'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SPOAllocationForm from '../../components/SPOAllocationForm';

type EditSPOAllocationPageProps = {
  params: Promise<{ id: string }>;
};

export default function EditSPOAllocationPage({ params }: EditSPOAllocationPageProps) {
  const { id } = use(params);

  return (
    <Container>
      <PageHeader title="Edit Supplier PO Allocation" eyebrow="SPO" />
      <Container>
        <SPOAllocationForm spoAllocationId={id} />
      </Container>
    </Container>
  );
}
