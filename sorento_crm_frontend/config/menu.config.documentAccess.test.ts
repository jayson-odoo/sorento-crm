/** DAS-FE-1: Resource Management > Document Access sits right after Attachment Types, in both menus. */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR, MENU_SIDEBAR_COMPACT } from './menu.config';
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

describe('Document Access menu entry', () => {
  it('MENU_SIDEBAR: right after Attachment Types, gated by resource.attachment_types.view', () => {
    const siblings = findParentOf(MENU_SIDEBAR, '/resource-management/attachment-types');
    expect(siblings).toBeDefined();
    const at = siblings!.findIndex((c) => c.path === '/resource-management/attachment-types');
    expect(siblings![at + 1]).toMatchObject({
      title: 'Document Access',
      path: '/resource-management/document-access',
      permission: 'resource.attachment_types.view',
    });
  });

  it('MENU_SIDEBAR_COMPACT: right after Attachment Types too', () => {
    const siblings = findParentOf(MENU_SIDEBAR_COMPACT, '/resource-management/attachment-types');
    expect(siblings).toBeDefined();
    const at = siblings!.findIndex((c) => c.path === '/resource-management/attachment-types');
    expect(siblings![at + 1]).toMatchObject({
      title: 'Document Access',
      path: '/resource-management/document-access',
    });
  });
});
