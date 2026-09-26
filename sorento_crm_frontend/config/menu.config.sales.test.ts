/**
 * The Sales menu group (UAC S1-17, S6-9; owner rulings 26 Sep (Lavish) L1 and
 * 26 Sep 06:01 (Lavish) N1: "need to move under Sales, not under Master Data anymore").
 *
 * The group carries NO moduleKey of its own; each child carries the module that owns its
 * route, so Sales Agents (module `product`) stays visible when `sales` is switched off.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR, MENU_SIDEBAR_COMPACT } from './menu.config';
import { filterMenuByModule } from '@/lib/menu-module-filter';
import type { MenuConfig, MenuItem } from './types';

const SALES_AGENTS_PATH = '/master-data-management/sales-agents';

function countPath(items: MenuConfig, path: string): number {
  let n = 0;
  for (const item of items) {
    if (item.path === path) n += 1;
    if (item.children) n += countPath(item.children, path);
  }
  return n;
}

function salesGroup(menu: MenuConfig): MenuItem | undefined {
  return menu.find((item) => !item.heading && item.title === 'Sales');
}

describe.each([
  ['MENU_SIDEBAR', MENU_SIDEBAR],
  ['MENU_SIDEBAR_COMPACT', MENU_SIDEBAR_COMPACT],
] as const)('%s - Sales group', (_name, menu) => {
  it('holds Targets first, then Sales Teams, then Sales Agents, each gated by its own module (S1)', () => {
    const group = salesGroup(menu);
    expect(group).toBeDefined();
    expect(group!.moduleKey).toBeUndefined();
    expect(group!.children).toEqual([
      {
        title: 'Targets',
        path: '/sales/targets',
        permission: 'sales.targets.view',
        moduleKey: 'sales',
      },
      {
        title: 'Sales Teams',
        path: '/sales/teams',
        permission: 'sales.teams.view',
        moduleKey: 'sales',
      },
      {
        title: 'Sales Agents',
        path: SALES_AGENTS_PATH,
        permission: 'master_data.sales_agents.view',
        moduleKey: 'product',
      },
    ]);
  });

  it('lists Sales Agents exactly once, so it is gone from Users & Access', () => {
    expect(countPath(menu, SALES_AGENTS_PATH)).toBe(1);
  });
});

describe('MENU_SIDEBAR - Sales group placement', () => {
  it('is the first group under the SALES heading', () => {
    const at = MENU_SIDEBAR.findIndex((item) => item.heading === 'SALES');
    expect(at).toBeGreaterThanOrEqual(0);
    expect(MENU_SIDEBAR[at + 1].title).toBe('Sales');
  });
});

describe('filterMenuByModule - Sales group', () => {
  const group = salesGroup(MENU_SIDEBAR)!;

  it('keeps Sales Agents when the sales module is off but product is on', () => {
    const [kept] = filterMenuByModule([group], new Set(['base', 'product']));
    expect(kept.children!.map((c) => c.title)).toEqual(['Sales Agents']);
  });

  it('shows Targets and Sales Teams once the sales module is installed (S1)', () => {
    const [kept] = filterMenuByModule([group], new Set(['base', 'product', 'sales']));
    expect(kept.children!.map((c) => c.title)).toEqual(['Targets', 'Sales Teams', 'Sales Agents']);
  });
});
