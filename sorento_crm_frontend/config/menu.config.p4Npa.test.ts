/**
 * PORTAL-P4-REQUESTS S5 (v1.2): for a salesperson the New Product Application item under MY REQUESTS opens the STAFF
 * list (server-side "only theirs"), gated by `procurement.new_product_applications.view_own`. Staff untouched.
 * The staff Procurement item's own gate (view / create / approve / open_code, no view_own) is not what feeds the
 * MY REQUESTS item.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from './menu.config';
import type { MenuConfig } from './types';
import { applyMenuAccess, type MenuAccess } from '@/lib/menu-access-filter';
import { LANDING_KINDS, LANDING_LABELS } from '@/lib/portal-form-kinds';
import { MY_REQUEST_STAFF_PAGES, myRequestStaffPath } from '@/lib/my-requests-staff-pages';

type Slim = { heading?: string; title?: string; path?: string };
const flat = (items: MenuConfig): Slim[] => items.map((i) => ({ heading: i.heading, title: i.title, path: i.path }));

function access(permissions: string[], salesperson: { portalKinds: string[] } | null): MenuAccess {
  return {
    isSuperadmin: false,
    permissionSet: new Set(permissions),
    isLoading: false,
    enabledModuleKeys: null,
    modulesLoading: false,
    salesperson,
  } as MenuAccess;
}

const NPA_PATH = '/procurement-management/new-product-applications';
const LIMITED = [
  'projects.projects.view_own',
  'procurement.new_product_applications.view_own',
  'procurement.new_product_applications.create',
];

function myRequests(out: Slim[]): Slim[] {
  const at = out.findIndex((i) => i.heading === 'MY REQUESTS');
  return at < 0 ? [] : out.slice(at + 1).filter((i) => !i.heading);
}

describe('MY REQUESTS New Product Application opens the staff pages', () => {
  it('opens the staff list, not /my-requests', () => {
    const out = myRequests(flat(applyMenuAccess(MENU_SIDEBAR, access(LIMITED, { portalKinds: [...LANDING_KINDS] as string[] }))));
    const item = out.find((i) => i.title === LANDING_LABELS.new_product_application);
    expect(item, 'no MY REQUESTS item for new_product_application').toBeDefined();
    expect(item?.path).toBe(NPA_PATH);
  });

  it('the staff-page map names the kind with its view_own slug', () => {
    expect(MY_REQUEST_STAFF_PAGES.new_product_application).toEqual({
      path: NPA_PATH,
      permission: 'procurement.new_product_applications.view_own',
    });
    expect(myRequestStaffPath('new_product_application')).toBe(NPA_PATH);
  });

  it('without view_own the item is not shown', () => {
    const out = myRequests(
      flat(
        applyMenuAccess(
          MENU_SIDEBAR,
          access(['projects.projects.view_own', 'procurement.new_product_applications.create'], {
            portalKinds: [...LANDING_KINDS] as string[],
          }),
        ),
      ),
    );
    expect(out.map((i) => i.title)).not.toContain(LANDING_LABELS.new_product_application);
  });
});

describe('staff menu is unchanged', () => {
  it('a staff user keeps the staff entry and sees no MY REQUESTS', () => {
    const out = flat(
      applyMenuAccess(
        MENU_SIDEBAR,
        access(['procurement.new_product_applications.view', 'procurement.new_product_applications.create'], null),
      ),
    );
    expect(out.map((i) => i.heading).filter(Boolean)).not.toContain('MY REQUESTS');
    expect(JSON.stringify(applyMenuAccess(MENU_SIDEBAR, access(['procurement.new_product_applications.view', 'procurement.new_product_applications.create'], null)))).toContain(NPA_PATH);
    expect(JSON.stringify(out)).not.toContain('/my-requests');
  });
});
