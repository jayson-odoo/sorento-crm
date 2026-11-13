/**
 * SPARE-PART-ORDER-REQUEST hand-test round (owner 13 Nov), red-first (Phase 2). UAC G3.
 *
 * F6 every "Spare Part Requests" menu entry opens the request's own list,
 * /procurement-management/spare-part-requests, no longer the Order Inquiries list filtered to
 * the type. Crew ruling (mirrors Purchase Requests): the Procurement entry is gated by the view
 * grant, the salesperson's MY REQUESTS entry by the create grant.
 */
import { describe, expect, it } from 'vitest';
import * as menus from './menu.config';
import type { MenuConfig, MenuItem } from './types';

function leaves(items: MenuConfig | undefined, title: string, out: MenuItem[] = []): MenuItem[] {
  for (const item of items ?? []) {
    if (item.title === title) out.push(item);
    leaves(item.children as MenuConfig | undefined, title, out);
  }
  return out;
}

describe('F6 (G3): Spare Part Requests opens its own list', () => {
  it('the sidebar entry points at /procurement-management/spare-part-requests', () => {
    const found = leaves(menus.MENU_SIDEBAR, 'Order Requests');
    expect(found.length).toBeGreaterThan(0);
    for (const item of found) {
      expect(item).toMatchObject({
        path: '/procurement-management/spare-part-requests',
        permission:
          item.audience === 'salesperson'
            ? 'procurement.spare_part_requests.create'
            : 'procurement.spare_part_requests.view',
      });
    }
  });

  it('no menu still sends Spare Part Requests to the Order Inquiries list', () => {
    const all = Object.values(menus).filter(Array.isArray) as MenuConfig[];
    const found = all.flatMap((menu) => leaves(menu, 'Order Requests'));
    expect(found.length).toBeGreaterThan(0);
    for (const item of found) {
      expect(item.path).toBe('/procurement-management/spare-part-requests');
    }
  });
});
