/**
 * SORENTO-TOWN: the Town entry. Admin-only since TOWN-V2 (owner, 10 Nov 2026): gated on the dedicated
 * `dashboards.town.view` permission (granted to admin and superadmin), so the sidebar hides it from
 * everyone else; not a role-name check.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from './menu.config';
import type { MenuConfig, MenuItem } from './types';

function entries(items: MenuConfig, path: string): MenuItem[] {
  const found: MenuItem[] = [];
  for (const item of items) {
    if (item.path === path) found.push(item);
    if (item.children) found.push(...entries(item.children, path));
  }
  return found;
}

describe('MENU_SIDEBAR - Town', () => {
  it('has exactly one Town entry at /town', () => {
    const found = entries(MENU_SIDEBAR, '/town');
    expect(found).toHaveLength(1);
    expect(found[0].title).toBe('Town');
    expect(found[0].heading).toBeUndefined();
  });

  it('is gated on dashboards.town.view only, not on a role name', () => {
    const [town] = entries(MENU_SIDEBAR, '/town');
    expect(town).toBeDefined();
    expect(town.permission).toBe('dashboards.town.view');
    expect(town.permissionsAny).toBeUndefined();
    expect(town.superadminOnly).toBeFalsy();
  });

  it('has an icon so the sidebar does not render a blank slot', () => {
    const [town] = entries(MENU_SIDEBAR, '/town');
    expect(town?.icon).toBeDefined();
  });
});
