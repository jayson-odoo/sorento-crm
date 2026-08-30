'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import FormDetail from './components/FormDetail';

export default function FormDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <>
      <Container>
        <PageHeader
          title="Form"
          actions={
            <BackToList
              listPath="/forms-management/forms"
              label="Back to forms"
            />
          }
        />
      </Container>

      <Container>
        <FormDetail formId={id} />
      </Container>
    </>
  );
}
