'use client';

import { use } from 'react';
import { notFound } from 'next/navigation';
import { SubmissionForm } from '../../components/SubmissionForm';
import { PortalSubmissionKind, isSubmissionKind } from '../../lib/portal-client';

export default function PortalNewSubmissionPage({
  params,
}: {
  params: Promise<{ type: string }>;
}) {
  const { type } = use(params);
  if (!isSubmissionKind(type)) {
    notFound();
  }
  return <SubmissionForm kind={type as PortalSubmissionKind} />;
}
