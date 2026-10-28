'use client';

import { MY_REQUEST_STAFF_PAGES } from '@/lib/my-requests-staff-pages';
import { StaffPageRedirect } from '../../StaffPageRedirect';

/** A new opportunity is logged from the staff list's modal (PORTAL-P4-REQUESTS S6). */
export default function MyRequestsSalesOpportunityNewPage() {
  return <StaffPageRedirect to={MY_REQUEST_STAFF_PAGES.sales_opportunity.path} />;
}
