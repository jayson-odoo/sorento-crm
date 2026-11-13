/**
 * OCN-ORDER-CHANGE-NOTICE round 15 (crew rule a): a salesperson reaches Order Change Notices from
 * MY REQUESTS, holding the notice's `view_own` (the staff groups stay hidden from them), as the
 * request forms do (`MY_REQUEST_STAFF_PAGES`). Staff keep the Project Sales Admin entry.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from '@/config/menu.config';
import { applyMenuAccess, type MenuAccess } from '@/lib/menu-access-filter';
import type { MenuConfig } from '@/config/types';

const OCN_PATH = '/procurement-management/order-change-notices';

function access(over: Partial<MenuAccess>): MenuAccess {
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

/** Every item, flattened, with the heading it sits under. */
function flat(menu: MenuConfig): { heading: string | null; title?: string; path?: string }[] {
  const out: { heading: string | null; title?: string; path?: string }[] = [];
  let heading: string | null = null;
  const walk = (items: MenuConfig) => {
    for (const item of items) {
      if (item.heading) {
        heading = item.heading;
        continue;
      }
      out.push({ heading, title: item.title, path: item.path });
      if (item.children) walk(item.children);
    }
  };
  walk(menu);
  return out;
}

describe('Order Change Notices for a salesperson', () => {
  it('sits under MY REQUESTS for a view_own salesperson, with no staff group', () => {
    const menu = applyMenuAccess(
      MENU_SIDEBAR,
      access({
        // Round 20 (UAC I4): the item comes from the shared MY REQUESTS list, so it needs the kind.
        salesperson: { portalKinds: ['order_change_notice'] },
        permissionSet: new Set([
          'procurement.order_change_notices.view_own',
          'procurement.order_change_notices.create',
        ]),
      }),
    );
    const items = flat(menu);
    const ocn = items.find((i) => i.path === OCN_PATH);
    expect(ocn).toBeTruthy();
    expect(ocn?.heading).toBe('MY REQUESTS');
    expect(ocn?.title).toBe('Order Change Notice');
    expect(items.some((i) => i.title === 'Project Sales Admin')).toBe(false);
  });

  it('is not offered to a salesperson without the notice grant', () => {
    const menu = applyMenuAccess(MENU_SIDEBAR, access({ salesperson: { portalKinds: [] } }));
    expect(flat(menu).some((i) => i.path === OCN_PATH)).toBe(false);
  });

  it('staff keep it under Project Sales Admin, not under MY REQUESTS', () => {
    const menu = applyMenuAccess(
      MENU_SIDEBAR,
      access({ permissionSet: new Set(['procurement.order_change_notices.view']) }),
    );
    const hits = flat(menu).filter((i) => i.path === OCN_PATH);
    expect(hits.length).toBe(1);
    expect(hits[0].heading).not.toBe('MY REQUESTS');
  });
});
