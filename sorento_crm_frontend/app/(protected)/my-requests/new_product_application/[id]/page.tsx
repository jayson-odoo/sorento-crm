'use client';

import { use } from 'react';
import { MY_REQUEST_STAFF_PAGES, sanitizeId } from '@/lib/my-requests-staff-pages';
import { StaffPageRedirect } from '../../StaffPageRedirect';

/** A deep link to a salesperson's application opens the staff detail (PORTAL-P4-REQUESTS S5). */
export default function MyRequestsNewProductApplicationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <StaffPageRedirect
      to={`${MY_REQUEST_STAFF_PAGES.new_product_application.path}/${sanitizeId(id)}`}
    />
  );
}
