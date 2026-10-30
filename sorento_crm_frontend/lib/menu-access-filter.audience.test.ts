/**
 * PORTAL-P3-ROLE-MENU P3-10..P3-12: `audience` and `portalKind` on a MenuItem, read by
 * `applyMenuAccess` before the existing superadmin / permission / module / heading steps.
 */
import { describe, expect, it } from 'vitest';
import type { MenuConfig } from '@/config/types';
import { applyMenuAccess, type MenuAccess } from '@/lib/menu-access-filter';

const MENU = [
  { heading: 'MY WORK', audience: 'salesperson' },
  { title: 'Mine', path: '/mine', audience: 'salesperson' },
  { heading: 'MY REQUESTS', audience: 'salesperson' },
  { title: 'Stock', path: '/my-requests?type=stock_inquiry', audience: 'salesperson', portalKind: 'stock_inquiry' },
  { title: 'Sample', path: '/my-requests?type=sample_request', audience: 'salesperson', portalKind: 'sample_request' },
  { heading: 'STAFF' },
  { title: 'Staff only', path: '/staff', audience: 'staff' },
  { title: 'Everyone', path: '/everyone' },
] as unknown as MenuConfig;

function access(over: Partial<MenuAccess> & { salesperson?: { portalKinds: string[] } | null }): MenuAccess {
  return {
    isSuperadmin: false,
    permissionSet: new Set<string>(),
    isLoading: false,
    enabledModuleKeys: null,
    modulesLoading: false,
    salesperson: null,
    ...over,
  } as MenuAccess;
}

const labels = (m: MenuConfig) => m.map((i) => i.heading ?? i.title);

describe('applyMenuAccess - audience', () => {
  it('salesperson: audience staff is dropped, audience salesperson kept', () => {
    const out = applyMenuAccess(MENU, access({ salesperson: { portalKinds: ['stock_inquiry', 'sample_request'] } }));
    expect(labels(out)).toEqual(['MY WORK', 'Mine', 'MY REQUESTS', 'Stock', 'Sample', 'STAFF', 'Everyone']);
  });

  it('staff (salesperson null): audience salesperson is dropped, staff and untagged kept', () => {
    const out = applyMenuAccess(MENU, access({ salesperson: null }));
    expect(labels(out)).toEqual(['STAFF', 'Staff only', 'Everyone']);
  });

  it('portalKind is kept only when the contact may use that kind', () => {
    const out = applyMenuAccess(MENU, access({ salesperson: { portalKinds: ['sample_request'] } }));
    expect(labels(out)).toContain('Sample');
    expect(labels(out)).not.toContain('Stock');
  });

  it('a heading left with no item is not rendered', () => {
    const out = applyMenuAccess(MENU, access({ salesperson: { portalKinds: [] } }));
    expect(labels(out)).not.toContain('MY REQUESTS');
    expect(labels(out)).toContain('MY WORK');
  });

  it('applies while permissions are still loading too', () => {
    const sp = applyMenuAccess(MENU, access({ isLoading: true, salesperson: { portalKinds: ['stock_inquiry'] } }));
    expect(labels(sp)).not.toContain('Staff only');
    expect(labels(sp)).toContain('Stock');
    const staff = applyMenuAccess(MENU, access({ isLoading: true, salesperson: null }));
    expect(labels(staff)).not.toContain('Mine');
    expect(labels(staff)).toContain('Staff only');
  });
});
