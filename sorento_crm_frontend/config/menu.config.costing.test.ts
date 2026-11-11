/**
 * Lane PRODUCT-COSTING (AC-CG-01): Products > Costing is a menu leaf under the Products group,
 * visible only with products.cost.view, at /master-data-management/costing.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from './menu.config';
import type { MenuConfig, MenuItem } from './types';

function trail(items: MenuConfig, path: string, parents: MenuItem[] = []): MenuItem[] | undefined {
  for (const item of items) {
    if (item.path === path) return [...parents, item];
    if (item.children) {
      const found = trail(item.children, path, [...parents, item]);
      if (found) return found;
    }
  }
  return undefined;
}

describe('MENU_SIDEBAR - Costing entry', () => {
  it('is Costing -> /master-data-management/costing gated by products.cost.view', () => {
    const found = trail(MENU_SIDEBAR, '/master-data-management/costing');
    expect(found).toBeDefined();
    const leaf = found![found!.length - 1];
    expect(leaf).toMatchObject({
      title: 'Costing',
      path: '/master-data-management/costing',
      permission: 'products.cost.view',
    });
  });

  it('sits under the top-level Products group', () => {
    const found = trail(MENU_SIDEBAR, '/master-data-management/costing');
    expect(found).toBeDefined();
    expect(found![0].title).toBe('Products');
  });

  it('appears once', () => {
    const count = JSON.stringify(MENU_SIDEBAR).split('/master-data-management/costing"').length - 1;
    expect(count).toBe(1);
  });
});
