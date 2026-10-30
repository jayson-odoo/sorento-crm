'use client';

import { use } from 'react';
import { myRequestStaffPath } from '@/lib/my-requests-staff-pages';
import { StaffPageRedirect } from '../../StaffPageRedirect';

export default function MyRequestsNewSubmissionPage({
  params,
}: {
  params: Promise<{ type: string }>;
}) {
  const { type } = use(params);
  const staffList = myRequestStaffPath(type);
  return <StaffPageRedirect to={staffList ? `${staffList}/new` : '/my-requests'} />;
}
