/**
 * SORENTO-TOWN Phase 1: the Town entry (plan "Phase 1 screen": a menu entry for every signed-in
 * staff user, no permission, in the existing menu config).
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

  it('is open to every signed-in staff user: no permission, no module, no admin gate', () => {
    const [town] = entries(MENU_SIDEBAR, '/town');
    expect(town).toBeDefined();
    expect(town.permission).toBeUndefined();
    expect(town.permissionsAny).toBeUndefined();
    expect(town.moduleKey).toBeUndefined();
    expect(town.superadminOnly).toBeFalsy();
  });

  it('has an icon so the sidebar does not render a blank slot', () => {
    const [town] = entries(MENU_SIDEBAR, '/town');
    expect(town?.icon).toBeDefined();
  });
});
