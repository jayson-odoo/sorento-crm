'use client';

import { use } from 'react';
import { notFound } from 'next/navigation';
import { SubmissionForm } from '@/app/(auth)/portal/components/SubmissionForm';
import { PortalSubmissionKind, isSubmissionKind } from '@/app/(auth)/portal/lib/portal-client';
import { MySlug } from '../../MySlug';

export default function MyRequestsNewSubmissionPage({
  params,
}: {
  params: Promise<{ type: string }>;
}) {
  const { type } = use(params);
  if (!isSubmissionKind(type)) {
    notFound();
  }
  return <MySlug>{() => <SubmissionForm kind={type as PortalSubmissionKind} />}</MySlug>;
}
