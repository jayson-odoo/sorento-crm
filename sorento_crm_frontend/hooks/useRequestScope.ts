'use client';

import { useHasPermission } from '@/hooks/usePermissions';

/** The request forms a salesperson sees "only theirs" of (PORTAL-P4-REQUESTS). */
const BASE: Record<string, string> = {
  stock_inquiry: 'procurement.stock_inquiries',
  complaint: 'complaint_management.complaints',
  purchase_request: 'procurement.purchase_requests',
  sponsorship_form: 'procurement.sponsorship_forms',
  sample_request: 'projects.sample_requests',
  sales_opportunity: 'sales.opportunities',
};

/**
 * `limited` = holds the form's `view_own` and not its `view`: the server narrows every staff route
 * to their own rows, and they write through My Requests (the portal's own rules). The rule the
 * server applies (`own_scope.request_access`); any other kind is never limited.
 */
export function useRequestScope(kind: string): { limited: boolean } {
  const base = BASE[kind] ?? '';
  // Both reads every render (hook order); an unknown kind asks for slugs nobody holds.
  const viewOwn = useHasPermission(base ? `${base}.view_own` : 'request_scope.none');
  const view = useHasPermission(base ? `${base}.view` : 'request_scope.none');
  return { limited: Boolean(base) && viewOwn && !view };
}
