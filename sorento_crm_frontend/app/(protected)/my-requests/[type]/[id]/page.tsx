'use client';

import { use } from 'react';
import { notFound } from 'next/navigation';
import { SubmissionForm } from '@/app/(auth)/portal/components/SubmissionForm';
import { PortalSubmissionKind, isSubmissionKind } from '@/app/(auth)/portal/lib/portal-client';
import { myRequestStaffPath } from '@/lib/my-requests-staff-pages';
import { MySlug, sanitizeId } from '../../MySlug';
import { StaffPageRedirect } from '../../StaffPageRedirect';

export default function MyRequestsEditSubmissionPage({
  params,
}: {
  params: Promise<{ type: string; id: string }>;
}) {
  const { type, id } = use(params);
  const staffList = myRequestStaffPath(type);
  if (staffList) return <StaffPageRedirect to={`${staffList}/${sanitizeId(id)}`} />;
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
