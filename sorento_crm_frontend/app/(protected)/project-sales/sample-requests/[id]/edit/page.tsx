'use client';

import { use } from 'react';
import { Container } from '@/components/common/container';
import SampleRequestForm from '../../components/SampleRequestForm';
import { SampleRequestPageHeader } from '../../components/SampleRequestPageHeader';

export default function EditSampleRequestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <Container>
      <SampleRequestPageHeader
        title="Edit Sample Request"
        mode="cancel"
        fallbackHref={`/project-sales/sample-requests/${id}`}
      />
      <div className="mt-6">
        <SampleRequestForm requestId={id} />
      </div>
    </Container>
  );
}
