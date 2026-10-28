'use client';

import { MY_REQUEST_STAFF_PAGES } from '@/lib/my-requests-staff-pages';
import { StaffPageRedirect } from '../../StaffPageRedirect';

/** A salesperson's new price tag request is the request page in create mode (PORTAL-P4-REQUESTS S7). */
export default function MyRequestsPriceTagNewPage() {
  return <StaffPageRedirect to={`${MY_REQUEST_STAFF_PAGES.price_tag_request.path}/new`} />;
}
