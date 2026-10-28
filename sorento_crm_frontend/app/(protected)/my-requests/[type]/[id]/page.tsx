'use client';

import { use } from 'react';
import { notFound } from 'next/navigation';
import { SubmissionForm } from '@/app/(auth)/portal/components/SubmissionForm';
import { PortalSubmissionKind, isSubmissionKind } from '@/app/(auth)/portal/lib/portal-client';
import { MySlug, sanitizeId } from '../../MySlug';

export default function MyRequestsEditSubmissionPage({
  params,
}: {
  params: Promise<{ type: string; id: string }>;
}) {
  const { type, id } = use(params);
  if (!isSubmissionKind(type)) {
    notFound();
  }
  return (
    <MySlug>
      {(slug) => (
        <SubmissionForm
          kind={type as PortalSubmissionKind}
          submissionId={sanitizeId(id)}
          slug={slug}
        />
      )}
    </MySlug>
  );
}
