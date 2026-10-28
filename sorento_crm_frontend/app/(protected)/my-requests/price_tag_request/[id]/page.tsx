'use client';

import { use } from 'react';
import { MY_REQUEST_STAFF_PAGES, sanitizeId } from '@/lib/my-requests-staff-pages';
import { StaffPageRedirect } from '../../StaffPageRedirect';

/** A deep link to a salesperson's price tag request opens the request page (PORTAL-P4-REQUESTS S7). */
export default function MyRequestsPriceTagDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <StaffPageRedirect to={`${MY_REQUEST_STAFF_PAGES.price_tag_request.path}/${sanitizeId(id)}`} />;
}
