'use client';

import { use } from 'react';
import { MY_REQUEST_STAFF_PAGES } from '@/lib/my-requests-staff-pages';
import { sanitizeId } from '../../MySlug';
import { StaffPageRedirect } from '../../StaffPageRedirect';

/** A deep link to a salesperson's opportunity opens the staff detail (PORTAL-P4-REQUESTS S6). */
export default function MyRequestsSalesOpportunityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <StaffPageRedirect to={`${MY_REQUEST_STAFF_PAGES.sales_opportunity.path}/${sanitizeId(id)}`} />
  );
}
