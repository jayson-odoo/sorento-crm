/**
 * SPARE-PART-ORDER-REQUEST crew ruling: the Spare Part Requests entry mirrors Purchase Requests,
 * red-first (Phase 2).
 *
 * a. a salesperson holding create but NOT view: no Procurement entry; one under MY REQUESTS
 *    at /procurement-management/spare-part-requests.
 * b. a staff user holding procurement.spare_part_requests.view sees the Procurement entry in
 *    every menu that carries it.
 * c. a user holding only projects.projects.view sees no Spare Part Requests entry anywhere.
 */
import { describe, expect, it } from 'vitest';
import * as menus from './menu.config';
import { MENU_SIDEBAR } from './menu.config';
import type { MenuConfig, MenuItem } from './types';
import {
  applyMenuAccess,
  filterMenuByAudience,
  filterMenuByPermission,
  type MenuAccess,
} from '@/lib/menu-access-filter';
import { LANDING_KINDS } from '@/lib/portal-form-kinds';

const TITLE = 'Order Requests';
const PATH = '/procurement-management/spare-part-requests';
const CREATE = 'procurement.spare_part_requests.create';
const VIEW = 'procurement.spare_part_requests.view';
const PROJECTS_VIEW = 'projects.projects.view';

function leaves(items: MenuConfig | undefined, out: MenuItem[] = []): MenuItem[] {
  for (const item of items ?? []) {
    if (item.title === TITLE) out.push(item);
    leaves(item.children as MenuConfig | undefined, out);
  }
  return out;
}

// A staff user (not a salesperson): the salesperson-only MY REQUESTS items never reach them.
const staffMenu = (menu: MenuConfig) => filterMenuByAudience(menu, null);
const staffVisible = (menu: MenuConfig, slugs: string[]) =>
  leaves(filterMenuByPermission(staffMenu(menu), new Set(slugs)));

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

const carrying = () =>
  (Object.entries(menus).filter(([, v]) => Array.isArray(v)) as [string, MenuConfig][]).filter(
    ([, m]) => leaves(m).length > 0,
  );

describe('a. a salesperson with create but not view', () => {
  const rendered = applyMenuAccess(
    MENU_SIDEBAR,
    access(['projects.projects.view_own', 'procurement.purchase_requests.view_own', CREATE], { portalKinds: [...LANDING_KINDS] as string[] }),
  );

  it('has one Spare Part Requests item, under MY REQUESTS', () => {
    const headingAt = rendered.findIndex((i) => i.heading === 'MY REQUESTS');
    expect(headingAt, 'MY REQUESTS heading renders').toBeGreaterThanOrEqual(0);
    const found = rendered.map((i, idx) => ({ i, idx })).filter(({ i }) => i.title === TITLE);
    expect(found.length, 'one top-level item under MY REQUESTS').toBe(1);
    expect(found[0].idx).toBeGreaterThan(headingAt);
    expect(found[0].i.path).toBe(PATH);
  });

  it('has no Procurement entry', () => {
    const procurement = rendered.filter((i) => !i.heading && i.title !== TITLE && i.children?.length);
    expect(leaves(procurement as MenuConfig)).toEqual([]);
  });

  it('a salesperson without create sees no item', () => {
    const none = applyMenuAccess(
      MENU_SIDEBAR,
      access(['projects.projects.view_own', 'procurement.purchase_requests.view_own'], { portalKinds: [...LANDING_KINDS] as string[] }),
    );
    expect(leaves(none)).toEqual([]);
  });
});

describe('a. staff with create only (not view) have no Procurement entry', () => {
  it('create alone shows no entry in the staff menus', () => {
    expect(carrying().length).toBeGreaterThan(0);
    const shown = carrying()
      .filter(([, m]) => staffVisible(m, [CREATE]).length > 0)
      .map(([n]) => n);
    expect(shown, `menus showing it to a create-only user: ${shown.join(', ')}`).toEqual([]);
  });
});

describe('b. a spare_part_requests.view approver sees the Procurement entry', () => {
  it('every menu that carries it shows it, gated by the view slug alone', () => {
    const hidden = carrying()
      .filter(([, m]) => staffVisible(m, [VIEW]).length === 0)
      .map(([n]) => n);
    expect(hidden, `menus hiding it from a view holder: ${hidden.join(', ')}`).toEqual([]);
    for (const [name, m] of carrying()) {
      for (const leaf of leaves(staffMenu(m))) {
        const slugs = [leaf.permission, ...(leaf.permissionsAny ?? [])].filter(Boolean);
        expect(slugs, `${name} leaf gate`).toEqual([VIEW]);
      }
    }
  });
});

describe('c. projects.projects.view alone shows no Spare Part Requests entry', () => {
  it('in any menu', () => {
    expect(carrying().length).toBeGreaterThan(0);
    const shown = carrying()
      .filter(([, m]) => staffVisible(m, [PROJECTS_VIEW]).length > 0)
      .map(([n]) => n);
    expect(shown, `menus showing it to a projects viewer: ${shown.join(', ')}`).toEqual([]);
  });
});
