'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import AccessAgentDetail from '../components/AccessAgentDetail';

export default function AccessAgentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <>
      <Container>
        <PageHeader
          title="Access Agent"
          actions={
            <BackToList
              listPath="/user-management/access-agents"
              label="Back to access agents"
            />
          }
        />
      </Container>
      <Container>
        <AccessAgentDetail accessAgentId={id} />
      </Container>
    </>
  );
}
