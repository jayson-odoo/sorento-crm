'use client';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SPOAllocationForm from '../components/SPOAllocationForm';

export default function NewSPOAllocationPage() {
  return (
    <Container>
      <PageHeader title="Create SPO Allocation" />
      <Container>
        <SPOAllocationForm />
      </Container>
    </Container>
  );
}
