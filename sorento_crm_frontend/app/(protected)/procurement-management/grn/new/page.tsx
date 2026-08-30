'use client';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import GRNForm from '../components/GRNForm';

export default function NewGRNPage() {
  return (
    <Container>
      <PageHeader title="Create Goods Receipt Note" eyebrow="GRN" />
      <Container>
        <GRNForm />
      </Container>
    </Container>
  );
}
