/**
 * AFTER-SALES-P2 red tests (UAC P1, F3): the Warranty Configuration sidebar item.
 * It sits under After-Sales Service as "Warranty Configuration" -> /after-sales/warranty, flagged
 * `superadminOnly: true` (the repo's admin-only gate: the sidebar filter `filterMenuBySuperadmin`
 * hides it for everyone else), in both MENU_SIDEBAR and MENU_SIDEBAR_COMPACT.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR, MENU_SIDEBAR_COMPACT } from './menu.config';
import { filterMenuBySuperadmin } from '@/lib/menu-access-filter';
import type { MenuConfig, MenuItem } from './types';

const section = (menu: MenuConfig) => menu.find((i) => i.title === 'After-Sales Service' && i.children) as MenuItem;
const item = (menu: MenuConfig) => section(menu).children!.find((c) => c.title === 'Warranty Configuration');

describe('Warranty Configuration menu item', () => {
  it.each([['MENU_SIDEBAR', MENU_SIDEBAR], ['MENU_SIDEBAR_COMPACT', MENU_SIDEBAR_COMPACT]])('%s lists it last under After-Sales Service', (_n, menu) => {
    expect(item(menu)?.path).toBe('/after-sales/warranty');
    expect(section(menu).children!.at(-1)?.title).toBe('Warranty Configuration');
  });

  it.each([['MENU_SIDEBAR', MENU_SIDEBAR], ['MENU_SIDEBAR_COMPACT', MENU_SIDEBAR_COMPACT]])('%s marks it admin-only', (_n, menu) => {
    expect(item(menu)?.superadminOnly).toBe(true);
  });

  it('is hidden from a non-admin and shown to an admin', () => {
    const titles = (isAdmin: boolean) =>
      section(filterMenuBySuperadmin(MENU_SIDEBAR, isAdmin)).children!.map((c) => c.title);
    expect(titles(false)).not.toContain('Warranty Configuration');
    expect(titles(false)).toContain('Service Jobs');
    expect(titles(true)).toContain('Warranty Configuration');
  });
});
