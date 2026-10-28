/**
 * PORTAL-P4-REQUESTS S7 (v1.2, Q8): for a salesperson the Price Tag Request item under MY REQUESTS opens the
 * STAFF table (Dealer Kit > Room Designer > Price Tag Requests, server-side "only theirs"), gated by
 * `dealer_kit.price_tag_requests.view_own`. Staff untouched.
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

const SALES = ['projects.projects.view_own', 'sales.customer_asks.view', 'dealer_kit.price_tag_requests.view_own'];

function myRequests(out: Slim[]): Slim[] {
  const at = out.findIndex((i) => i.heading === 'MY REQUESTS');
  return at < 0 ? [] : out.slice(at + 1).filter((i) => !i.heading);
}

describe('MY REQUESTS Price Tag Request opens the staff table', () => {
  it('the item points at /dealer-kit/price-tag-requests, not /my-requests', () => {
    const out = myRequests(
      flat(applyMenuAccess(MENU_SIDEBAR, access(SALES, { portalKinds: [...LANDING_KINDS] as string[] }))),
    );
    const item = out.find((i) => i.title === LANDING_LABELS.price_tag_request);
    expect(item, 'no MY REQUESTS item for price_tag_request').toBeDefined();
    expect(item?.path).toBe('/dealer-kit/price-tag-requests');
  });

  it('the staff-page map names the kind with its view_own slug', () => {
    expect(MY_REQUEST_STAFF_PAGES.price_tag_request).toEqual({
      path: '/dealer-kit/price-tag-requests',
      permission: 'dealer_kit.price_tag_requests.view_own',
    });
    expect(myRequestStaffPath('price_tag_request')).toBe('/dealer-kit/price-tag-requests');
  });

  it('without view_own the item is not shown', () => {
    const out = myRequests(
      flat(
        applyMenuAccess(
          MENU_SIDEBAR,
          access(['projects.projects.view_own', 'sales.customer_asks.view'], { portalKinds: [...LANDING_KINDS] as string[] }),
        ),
      ),
    );
    expect(out.map((i) => i.title)).not.toContain(LANDING_LABELS.price_tag_request);
  });
});

describe('staff menu is unchanged', () => {
  it('a staff user keeps Price Tag Requests under the Dealer Kit and sees no MY REQUESTS', () => {
    const out = flat(
      applyMenuAccess(
        MENU_SIDEBAR,
        access(['dealer_kit.price_tag_requests.view', 'dealer_kit.page.view'], null),
      ),
    );
    expect(out.map((i) => i.heading).filter(Boolean)).not.toContain('MY REQUESTS');
    expect(JSON.stringify(out)).not.toContain('/my-requests');
  });
});
