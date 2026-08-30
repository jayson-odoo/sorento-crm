'use client';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SPOAllocationForm from '../components/SPOAllocationForm';

export default function NewSPOAllocationPage() {
  return (
    <Container>
      <PageHeader title="Create Supplier PO Allocation" eyebrow="SPO" />
      <Container>
        <SPOAllocationForm />
      </Container>
    </Container>
  );
}
