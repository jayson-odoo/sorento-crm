/**
 * AC-PI-42 (RED): Project Sales > Configuration > "Project import", in both menu trees,
 * gated by `projects.import.view`, next to Setup / Series / Price Floors.
 *
 * MENU_SIDEBAR nests it under Project Sales > Configuration. MENU_SIDEBAR_COMPACT has no
 * Configuration group (Series sits straight under Project Sales), so there the entry is a
 * sibling of Series, which is "the same place" in that tree.
 */
import { describe, expect, it } from 'vitest';

import { PROJECT_VIEW_PERMISSIONS } from '@/app/(protected)/project-sales/_shared/projectViewPermissions';

import { MENU_SIDEBAR, MENU_SIDEBAR_COMPACT } from './menu.config';
import type { MenuConfig, MenuItem } from './types';

type Found = { item: MenuItem; parents: MenuItem[] };

function find(menu: MenuConfig, path: string): Found[] {
  const out: Found[] = [];
  const walk = (items: MenuItem[] | undefined, parents: MenuItem[]) => {
    for (const item of items ?? []) {
      if (item.path === path) out.push({ item, parents });
      walk(item.children as MenuItem[] | undefined, [...parents, item]);
    }
  };
  walk(menu as MenuItem[], []);
  return out;
}

const ENTRY = {
  title: 'Project import',
  path: '/project-sales/import',
  permission: 'projects.import.view',
};

describe.each([
  ['MENU_SIDEBAR', MENU_SIDEBAR],
  ['MENU_SIDEBAR_COMPACT', MENU_SIDEBAR_COMPACT],
])('%s - Project import entry', (_name, menu) => {
  it('exists once, at /project-sales/import, gated by projects.import.view', () => {
    const found = find(menu, ENTRY.path);
    expect(found).toHaveLength(1);
    expect(found[0].item).toMatchObject(ENTRY);
  });

  it('sits under Project Sales, in the same group as Series', () => {
    const [entry] = find(menu, ENTRY.path);
    const [series] = find(menu, '/project-sales/series');
    expect(entry.parents[0]?.title).toBe('Project Sales');
    expect(entry.parents.map((p) => p.title)).toEqual(series.parents.map((p) => p.title));
  });
});

describe('MENU_SIDEBAR nesting', () => {
  it('is Project Sales > Configuration > Project import', () => {
    const [entry] = find(MENU_SIDEBAR, ENTRY.path);
    expect(entry.parents.map((p) => p.title)).toEqual(['Project Sales', 'Configuration']);
  });
});

describe('projectViewPermissions', () => {
  it('lets a user holding only projects.import.view reach the page', () => {
    expect(PROJECT_VIEW_PERMISSIONS).toContain('projects.import.view');
  });
});
