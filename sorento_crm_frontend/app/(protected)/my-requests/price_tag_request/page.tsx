'use client';

import { MY_REQUEST_STAFF_PAGES } from '@/lib/my-requests-staff-pages';
import { StaffPageRedirect } from '../StaffPageRedirect';

/** A salesperson's price tag requests are the Dealer Kit table (PORTAL-P4-REQUESTS S7). */
export default function MyRequestsPriceTagListPage() {
  return <StaffPageRedirect to={MY_REQUEST_STAFF_PAGES.price_tag_request.path} />;
}
