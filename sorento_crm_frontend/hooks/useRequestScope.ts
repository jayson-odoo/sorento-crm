'use client';

import { useHasPermission } from '@/hooks/usePermissions';

/** The request forms a salesperson sees "only theirs" of (PORTAL-P4-REQUESTS). */
const BASE: Record<string, string> = {
  stock_inquiry: 'procurement.stock_inquiries',
  complaint: 'complaint_management.complaints',
  purchase_request: 'procurement.purchase_requests',
  sponsorship_form: 'procurement.sponsorship_forms',
  sample_request: 'projects.sample_requests',
  new_product_application: 'procurement.new_product_applications',
  sales_opportunity: 'sales.opportunities',
};

/** Grants that see every row of a kind besides its `view` (`own_scope.VIEW_ALL_ALSO`): a new
 *  product application's approvers and purchasing. At most two per kind. */
const VIEW_ALL_ALSO: Record<string, [string, string]> = {
  new_product_application: [
    'procurement.new_product_applications.approve',
    'procurement.new_product_applications.open_code',
  ],
};

const NONE = 'request_scope.none';

/**
 * `limited` = holds the form's `view_own` and none of its view-all grants (`view`, plus
 * `VIEW_ALL_ALSO`): the server narrows every staff route to their own rows, and they write
 * through My Requests (the portal's own rules). The rule the server applies
 * (`own_scope.request_access`); any other kind is never limited.
 */
export function useRequestScope(kind: string): { limited: boolean } {
  const base = BASE[kind] ?? '';
  const also = VIEW_ALL_ALSO[kind] ?? [NONE, NONE];
  // Every read every render (hook order); an unknown kind asks for slugs nobody holds.
  const viewOwn = useHasPermission(base ? `${base}.view_own` : NONE);
  const view = useHasPermission(base ? `${base}.view` : NONE);
  const alsoFirst = useHasPermission(also[0]);
  const alsoSecond = useHasPermission(also[1]);
  return { limited: Boolean(base) && viewOwn && !view && !alsoFirst && !alsoSecond };
}
