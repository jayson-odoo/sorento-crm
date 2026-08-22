/**
 * Sidebar wiring for Planning changes (`PLAN-so-book-diff-replanning.md`, journey step 1: "A
 * sidebar entry (Project Sales -> Planning changes) lists the same thing later, for the
 * planner who was not the uploader.").
 *
 * The Project Sales branch is duplicated in `MENU_SIDEBAR` (the default/demo1/3/4/5/10
 * sidebar) and `MENU_SIDEBAR_COMPACT` (demo10's `sidebar-menu-primary`) - both drive a real
 * rendered sidebar depending on the layout in use, so an entry missing from either one is a
 * page nobody can navigate to from that layout. `MENU_SIDEBAR_CUSTOM` is a small, unrelated
 * demo array (`Store - Client`, used only for demo2's navbar dropdown) and carries no
 * Project Sales branch at all.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR, MENU_SIDEBAR_COMPACT } from './menu.config';
import type { MenuConfig, MenuItem } from './types';

function findProjectSalesChildren(menu: MenuConfig): MenuItem[] {
  const branch = menu.find((item) => item.title === 'Project Sales');
  if (!branch || !branch.children) {
    throw new Error('Project Sales branch not found');
  }
  return branch.children;
}

describe('menu.config - Planning changes entry', () => {
  it.each([
    ['MENU_SIDEBAR', MENU_SIDEBAR],
    ['MENU_SIDEBAR_COMPACT', MENU_SIDEBAR_COMPACT],
  ])('is present under Project Sales in %s', (_name, menu) => {
    const children = findProjectSalesChildren(menu);
    const entry = children.find((item) => item.title === 'Planning changes');
    expect(entry).toBeDefined();
    expect(entry).toMatchObject({
      title: 'Planning changes',
      path: '/project-sales/planning-changes',
      permission: 'projects.projects.view',
    });
  });

  it.each([
    ['MENU_SIDEBAR', MENU_SIDEBAR],
    ['MENU_SIDEBAR_COMPACT', MENU_SIDEBAR_COMPACT],
  ])('sits right after Order Inquiries in %s', (_name, menu) => {
    const children = findProjectSalesChildren(menu);
    const titles = children.map((item) => item.title);
    const orderInquiriesAt = titles.indexOf('Order Inquiries');
    expect(orderInquiriesAt).toBeGreaterThanOrEqual(0);
    expect(titles[orderInquiriesAt + 1]).toBe('Planning changes');
  });
});
