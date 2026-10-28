/**
 * PORTAL-P4-REQUESTS S4 + S6 (v1.2): for a salesperson the Sample Request and Sales Opportunity items under
 * MY REQUESTS open the STAFF pages (server-side "only theirs"), gated by the kind's `view_own`. Staff untouched.
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

const SALES = [
  'projects.projects.view_own',
  'sales.customer_asks.view',
  'projects.sample_requests.view_own',
  'sales.opportunities.view_own',
];

function myRequests(out: Slim[]): Slim[] {
  const at = out.findIndex((i) => i.heading === 'MY REQUESTS');
  return at < 0 ? [] : out.slice(at + 1).filter((i) => !i.heading);
}

describe('MY REQUESTS Sample Request + Sales Opportunity open the staff pages', () => {
  const items = () =>
    myRequests(flat(applyMenuAccess(MENU_SIDEBAR, access(SALES, { portalKinds: [...LANDING_KINDS] as string[] }))));

  it.each([
    ['sample_request', '/project-sales/sample-requests'],
    ['sales_opportunity', '/sales/opportunities'],
  ])('%s opens %s, not /my-requests', (kind, path) => {
    const item = items().find((i) => i.title === LANDING_LABELS[kind as keyof typeof LANDING_LABELS]);
    expect(item, `no MY REQUESTS item for ${kind}`).toBeDefined();
    expect(item?.path).toBe(path);
  });

  it('the staff-page map names both kinds with their view_own slug', () => {
    expect(MY_REQUEST_STAFF_PAGES.sample_request).toEqual({
      path: '/project-sales/sample-requests',
      permission: 'projects.sample_requests.view_own',
    });
    expect(MY_REQUEST_STAFF_PAGES.sales_opportunity).toEqual({
      path: '/sales/opportunities',
      permission: 'sales.opportunities.view_own',
    });
    expect(myRequestStaffPath('sample_request')).toBe('/project-sales/sample-requests');
    expect(myRequestStaffPath('sales_opportunity')).toBe('/sales/opportunities');
  });

  it('without the kind\'s view_own the item is not shown', () => {
    const out = myRequests(
      flat(
        applyMenuAccess(
          MENU_SIDEBAR,
          access(['projects.projects.view_own', 'sales.customer_asks.view'], { portalKinds: [...LANDING_KINDS] as string[] }),
        ),
      ),
    );
    expect(out.map((i) => i.title)).not.toContain(LANDING_LABELS.sample_request);
    expect(out.map((i) => i.title)).not.toContain(LANDING_LABELS.sales_opportunity);
  });
});

describe('staff menu is unchanged', () => {
  it('a staff user keeps the staff entries and sees no MY REQUESTS', () => {
    const out = flat(
      applyMenuAccess(
        MENU_SIDEBAR,
        access(['projects.sample_requests.view', 'projects.sample_requests.create', 'sales.opportunities.view'], null),
      ),
    );
    expect(out.map((i) => i.heading).filter(Boolean)).not.toContain('MY REQUESTS');
    expect(JSON.stringify(out)).not.toContain('/my-requests');
  });
});
