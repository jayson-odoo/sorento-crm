'use client';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PackingListForm from '../components/PackingListForm';

export default function NewPackingListPage() {
  return (
    <Container>
      <PageHeader title="Create Packing List" />
      <Container>
        <PackingListForm />
      </Container>
    </Container>
  );
}
