/**
 * PORTAL-P4-REQUESTS S-FE0 (P4-22..P4-26): `useRequestScope(kind)` -> `{ limited }`.
 * Limited = holds `<form>.view_own` and not `<form>.view` (the P2 rule, mirrored from the server).
 */
import { describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

import { useRequestScope } from './useRequestScope';

const limitedOf = (kind: Parameters<typeof useRequestScope>[0], slugs: string[]) => {
  held = new Set(slugs);
  return renderHook(() => useRequestScope(kind)).result.current.limited;
};

describe('useRequestScope', () => {
  it.each([
    ['stock_inquiry', 'procurement.stock_inquiries'],
    ['complaint', 'complaint_management.complaints'],
    ['purchase_request', 'procurement.purchase_requests'],
    ['sponsorship_form', 'procurement.sponsorship_forms'],
  ] as const)('%s: view_own alone is limited; view makes it staff', (kind, base) => {
    expect(limitedOf(kind, [`${base}.view_own`])).toBe(true);
    expect(limitedOf(kind, [`${base}.view_own`, `${base}.add`])).toBe(true);
    expect(limitedOf(kind, [`${base}.view`])).toBe(false);
    expect(limitedOf(kind, [`${base}.view`, `${base}.view_own`])).toBe(false);
    expect(limitedOf(kind, [])).toBe(false);
  });

  it('a slug of another form does not limit this one', () => {
    expect(limitedOf('stock_inquiry', ['complaint_management.complaints.view_own'])).toBe(false);
  });
});
