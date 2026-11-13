/**
 * SPARE-PART-ORDER-REQUEST review round 2 (review S5), red-first (Phase 2).
 *
 * R8 an approver reaches the Spare Part Requests list from the sidebar. Crew ruling (mirrors
 *    Purchase Requests): the entry is gated by `procurement.spare_part_requests.view` alone, in
 *    every menu that carries it, through the same filter the sidebar renders from
 *    (lib/menu-access-filter.filterMenuByPermission). `projects.projects.view` alone no longer
 *    shows it, and neither does an unrelated grant.
 */
import { describe, expect, it } from 'vitest';
import * as menus from './menu.config';
import type { MenuConfig, MenuItem } from './types';
import { filterMenuByPermission } from '@/lib/menu-access-filter';

const TITLE = 'Order Requests';
const VIEW = 'procurement.spare_part_requests.view';
const PROJECTS_VIEW = 'projects.projects.view';

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
  it('a spare_part_requests.view approver sees it in the sidebar', () => {
    expect(leaves(menus.MENU_SIDEBAR).length, 'precondition: the sidebar has the leaf').toBeGreaterThan(0);
    expect(visibleTo(menus.MENU_SIDEBAR, [VIEW]).length, 'visible with the view grant only').toBeGreaterThan(0);
  });

  it('every menu that carries the entry shows it to a view-only approver', () => {
    const all = Object.entries(menus).filter(([, v]) => Array.isArray(v)) as [string, MenuConfig][];
    const carrying = all.filter(([, menu]) => leaves(menu).length > 0);
    expect(carrying.length).toBeGreaterThan(0);
    const hidden = carrying.filter(([, menu]) => visibleTo(menu, [VIEW]).length === 0).map(([n]) => n);
    expect(hidden, `menus that hide it from a view-only approver: ${hidden.join(', ')}`).toEqual([]);
  });

  it('projects.projects.view alone does not show it; neither does an unrelated grant (guard)', () => {
    expect(visibleTo(menus.MENU_SIDEBAR, [PROJECTS_VIEW]).length).toBe(0);
    expect(visibleTo(menus.MENU_SIDEBAR, ['zzt.unrelated.view']).length).toBe(0);
  });
});
