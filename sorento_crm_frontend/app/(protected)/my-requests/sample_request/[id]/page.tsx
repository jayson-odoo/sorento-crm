'use client';

import { use } from 'react';
import { MY_REQUEST_STAFF_PAGES, sanitizeId } from '@/lib/my-requests-staff-pages';
import { StaffPageRedirect } from '../../StaffPageRedirect';

/** A deep link to a salesperson's sample request opens the staff detail (PORTAL-P4-REQUESTS S4). */
export default function MyRequestsSampleRequestDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <StaffPageRedirect to={`${MY_REQUEST_STAFF_PAGES.sample_request.path}/${sanitizeId(id)}`} />;
}
