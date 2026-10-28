'use client';

import { MY_REQUEST_STAFF_PAGES } from '@/lib/my-requests-staff-pages';
import { StaffPageRedirect } from '../../StaffPageRedirect';

/** A salesperson's new application is the staff /new page (PORTAL-P4-REQUESTS S5). */
export default function MyRequestsNewProductApplicationNewPage() {
  return <StaffPageRedirect to={`${MY_REQUEST_STAFF_PAGES.new_product_application.path}/new`} />;
}
