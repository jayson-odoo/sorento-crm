/**
 * OCN-ORDER-CHANGE-NOTICE UAC G1: "Order Change Notices" sits under Project Sales Admin, right after
 * Sponsorship Forms, in BOTH menu trees that carry that group, gated by the OCN view / view_own slugs.
 */
import { describe, expect, it } from 'vitest';
import * as menus from './menu.config';
import type { MenuConfig, MenuItem } from './types';
import { applyMenuAccess, type MenuAccess } from '@/lib/menu-access-filter';

const PATH = '/procurement-management/order-change-notices';
const VIEW = 'procurement.order_change_notices.view';
const VIEW_OWN = 'procurement.order_change_notices.view_own';

/** Every distinct "Project Sales Admin" group object reachable from any exported menu. */
function projectSalesAdminGroups(): MenuItem[] {
  const found = new Set<MenuItem>();
  const walk = (items: MenuConfig | undefined) => {
    for (const item of items ?? []) {
      if (item.title === 'Project Sales Admin') found.add(item);
      walk(item.children as MenuConfig | undefined);
    }
  };
  for (const value of Object.values(menus)) {
    if (Array.isArray(value)) walk(value as MenuConfig);
  }
  return [...found];
}

function access(permissions: string[]): MenuAccess {
  return {
    isSuperadmin: false,
    permissionSet: new Set(permissions),
    isLoading: false,
    enabledModuleKeys: null,
    modulesLoading: false,
    salesperson: null,
  } as MenuAccess;
}

function titlesUnderProjectSalesAdmin(config: MenuConfig, permissions: string[]): string[] {
  const out: string[] = [];
  const walk = (items: MenuConfig | undefined) => {
    for (const item of items ?? []) {
      if (item.title === 'Project Sales Admin') {
        out.push(...((item.children ?? []) as MenuConfig).map((c) => c.title ?? ''));
      }
      walk(item.children as MenuConfig | undefined);
    }
  };
  walk(applyMenuAccess(config, access(permissions)));
  return out;
}

describe('Order Change Notices menu entry (G1)', () => {
  it('Project Sales Admin exists in two menu trees', () => {
    expect(projectSalesAdminGroups().length).toBeGreaterThanOrEqual(2);
  });

  it('every Project Sales Admin group lists Order Change Notices right after Sponsorship Forms', () => {
    for (const group of projectSalesAdminGroups()) {
      const titles = (group.children ?? []).map((c) => c.title);
      const at = titles.indexOf('Sponsorship Forms');
      expect(at, 'Sponsorship Forms is in the group').toBeGreaterThanOrEqual(0);
      expect(titles[at + 1]).toBe('Order Change Notices');
    }
  });

  it('points at the OCN list and is gated by view or view_own', () => {
    for (const group of projectSalesAdminGroups()) {
      const entry = (group.children ?? []).find((c) => c.title === 'Order Change Notices');
      expect(entry, 'entry present').toBeDefined();
      expect(entry?.path).toBe(PATH);
      const gate = new Set<string>([
        ...(entry?.permission ? [entry.permission] : []),
        ...((entry as { permissionsAny?: string[] } | undefined)?.permissionsAny ?? []),
      ]);
      expect([...gate].sort()).toEqual([VIEW, VIEW_OWN].sort());
    }
  });

  it('shows the entry to someone with view, and to someone with only view_own', () => {
    for (const slug of [VIEW, VIEW_OWN]) {
      const titles = titlesUnderProjectSalesAdmin(menus.MENU_SIDEBAR, [slug, 'procurement.purchase_requests.view']);
      expect(titles, slug).toContain('Order Change Notices');
    }
  });

  it('hides the entry from someone with neither slug', () => {
    const titles = titlesUnderProjectSalesAdmin(menus.MENU_SIDEBAR, ['procurement.purchase_requests.view']);
    expect(titles).toContain('Purchase Requests');
    expect(titles).not.toContain('Order Change Notices');
  });
});
