/**
 * SPARE-PART-ORDER-REQUEST review round 2 (review S5), red-first (Phase 2).
 *
 * R8 an approver who holds projects.projects.view but NOT the create grant can open the list
 *    (page.tsx RequireAccess anyPermission [view, create]; the list route's read dependency
 *    accepts either, tests/test_spare_part_request_review2.py R8), so the sidebar must let
 *    them find it: every "Spare Part Requests" leaf accepts either grant (permissionsAny
 *    [create, view]), through the same filter the sidebar renders from
 *    (lib/menu-access-filter.filterMenuByPermission). A requester with the create grant only
 *    still sees it; a user with neither does not.
 *
 * Note for the coder: config/menu.config.handtest.sparePart.test.ts (F6) asserts
 * `permission: 'procurement.spare_part_requests.create'` on the leaf; a leaf that keeps that
 * `permission` AND adds `permissionsAny` satisfies both (permissionsAny wins in the filter).
 */
import { describe, expect, it } from 'vitest';
import * as menus from './menu.config';
import type { MenuConfig, MenuItem } from './types';
import { filterMenuByPermission } from '@/lib/menu-access-filter';

const TITLE = 'Spare Part Requests';
const CREATE = 'procurement.spare_part_requests.create';
const VIEW = 'projects.projects.view';

function leaves(items: MenuConfig | undefined, out: MenuItem[] = []): MenuItem[] {
  for (const item of items ?? []) {
    if (item.title === TITLE) out.push(item);
    leaves(item.children as MenuConfig | undefined, out);
  }
  return out;
}

const visibleTo = (menu: MenuConfig, slugs: string[]) =>
  leaves(filterMenuByPermission(menu, new Set(slugs)));

describe('R8 (S5): the Spare Part Requests entry is there for an approver', () => {
  it('a view-only approver sees it in the sidebar', () => {
    expect(leaves(menus.MENU_SIDEBAR).length, 'precondition: the sidebar has the leaf').toBeGreaterThan(0);
    expect(visibleTo(menus.MENU_SIDEBAR, [VIEW]).length, 'visible with projects.projects.view only').toBeGreaterThan(0);
  });

  it('every menu that carries the entry shows it to a view-only approver', () => {
    const all = Object.entries(menus).filter(([, v]) => Array.isArray(v)) as [string, MenuConfig][];
    const carrying = all.filter(([, menu]) => leaves(menu).length > 0);
    expect(carrying.length).toBeGreaterThan(0);
    const hidden = carrying.filter(([, menu]) => visibleTo(menu, [VIEW]).length === 0).map(([n]) => n);
    expect(hidden, `menus that hide it from a view-only approver: ${hidden.join(', ')}`).toEqual([]);
  });

  it('a create-only requester still sees it; someone with neither grant does not (guard)', () => {
    expect(visibleTo(menus.MENU_SIDEBAR, [CREATE]).length).toBeGreaterThan(0);
    expect(visibleTo(menus.MENU_SIDEBAR, ['zzt.unrelated.view']).length).toBe(0);
  });
});
