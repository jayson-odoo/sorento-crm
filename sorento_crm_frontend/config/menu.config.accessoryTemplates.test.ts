/** PRICETAG-ACCESSORY-DESIGNER S5: Dealer Kit > Accessory Templates sits right after Tag Sizes, same permission. */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from './menu.config';
import type { MenuConfig, MenuItem } from './types';

function findParentOf(items: MenuConfig, path: string): MenuItem[] | undefined {
  for (const item of items) {
    if (item.children) {
      if (item.children.some((c) => c.path === path)) return item.children;
      const deeper = findParentOf(item.children, path);
      if (deeper) return deeper;
    }
  }
  return undefined;
}

describe('MENU_SIDEBAR - Accessory Templates entry', () => {
  it('is Accessory Templates -> /dealer-kit/accessory-templates, right after Tag Sizes', () => {
    const siblings = findParentOf(MENU_SIDEBAR, '/dealer-kit/tag-sizes');
    expect(siblings).toBeDefined();
    const tagSizes = siblings!.find((c) => c.path === '/dealer-kit/tag-sizes')!;
    const at = siblings!.indexOf(tagSizes);
    expect(siblings![at + 1]).toMatchObject({
      title: 'Accessory Templates',
      path: '/dealer-kit/accessory-templates',
      permission: tagSizes.permission,
    });
  });
});
