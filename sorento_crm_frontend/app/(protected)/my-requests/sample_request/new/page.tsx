'use client';

import { MY_REQUEST_STAFF_PAGES } from '@/lib/my-requests-staff-pages';
import { StaffPageRedirect } from '../../StaffPageRedirect';

/** A salesperson's new sample request is the staff /new page (PORTAL-P4-REQUESTS S4). */
export default function MyRequestsSampleRequestNewPage() {
  return <StaffPageRedirect to={`${MY_REQUEST_STAFF_PAGES.sample_request.path}/new`} />;
}
