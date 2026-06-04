'use client';

import { use } from 'react';
import { notFound } from 'next/navigation';
import { SubmissionForm } from '../../../../components/SubmissionForm';
import { PortalSubmissionKind, isSubmissionKind } from '../../../../lib/portal-client';

export default function PortalSlugEditSubmissionPage({
  params,
}: {
  params: Promise<{ slug: string; type: string; id: string }>;
}) {
  const { type, id } = use(params);
  if (!isSubmissionKind(type)) {
    notFound();
  }
  return <SubmissionForm kind={type as PortalSubmissionKind} submissionId={id} />;
}
