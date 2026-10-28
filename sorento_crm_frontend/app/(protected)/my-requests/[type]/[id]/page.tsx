'use client';

import { use } from 'react';
import { myRequestStaffPath, sanitizeId } from '@/lib/my-requests-staff-pages';
import { StaffPageRedirect } from '../../StaffPageRedirect';

export default function MyRequestsEditSubmissionPage({
  params,
}: {
  params: Promise<{ type: string; id: string }>;
}) {
  const { type, id } = use(params);
  const staffList = myRequestStaffPath(type);
  return <StaffPageRedirect to={staffList ? `${staffList}/${sanitizeId(id)}` : '/my-requests'} />;
}
