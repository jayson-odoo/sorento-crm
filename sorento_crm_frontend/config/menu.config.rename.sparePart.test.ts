/**
 * SPARE-PART-ORDER-REQUEST owner rename (13 Nov), red-first (Phase 2). F4.
 * The user-facing name is "Order Requests": both Procurement menus and the MY REQUESTS item.
 * The route path stays /procurement-management/spare-part-requests (internal key, not asserted
 * beyond identifying the entries).
 */
import { describe, expect, it } from 'vitest';
import * as menus from './menu.config';
import type { MenuConfig, MenuItem } from './types';

const PATH = '/procurement-management/spare-part-requests';

function entries(items: MenuConfig | undefined, out: MenuItem[] = []): MenuItem[] {
  for (const item of items ?? []) {
    if (item.path === PATH) out.push(item);
    entries(item.children as MenuConfig | undefined, out);
  }
  return out;
}

const all = (Object.values(menus).filter((v) => Array.isArray(v)) as MenuConfig[]).flatMap((m) =>
  entries(m),
);

describe('F4: the menu entries are titled "Order Requests"', () => {
  it('finds the three entries (two Procurement menus and MY REQUESTS)', () => {
    expect(all.length).toBeGreaterThanOrEqual(3);
  });

  it('every entry is titled "Order Requests"', () => {
    expect(all.map((i) => i.title)).toEqual(all.map(() => 'Order Requests'));
  });

  it('no menu item still says Spare Part Requests', () => {
    expect(all.filter((i) => /spare part/i.test(String(i.title)))).toEqual([]);
  });
});
