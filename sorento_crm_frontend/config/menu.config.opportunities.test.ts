/**
 * Sales > Opportunities in the sidebar (UAC S2-12; plan section 16: "both sidebars, above
 * Sales Teams").
 *
 * NOTE for the coder: `menu.config.sales.test.ts` currently asserts the Sales group's
 * `children` with an exact `toEqual([Sales Teams, Sales Agents])` - adding Opportunities above
 * Sales Teams means that file's exact-equality assertion needs updating too (flagged in the
 * tester's report; not duplicated here).
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR, MENU_SIDEBAR_COMPACT } from './menu.config';
import { filterMenuByModule } from '@/lib/menu-module-filter';
import type { MenuConfig, MenuItem } from './types';

function salesGroup(menu: MenuConfig): MenuItem | undefined {
  return menu.find((item) => !item.heading && item.title === 'Sales');
}

describe.each([
  ['MENU_SIDEBAR', MENU_SIDEBAR],
  ['MENU_SIDEBAR_COMPACT', MENU_SIDEBAR_COMPACT],
] as const)('%s - Sales group holds Opportunities', (_name, menu) => {
  it('lists Opportunities before Sales Teams, gated by its own module and permission', () => {
    const group = salesGroup(menu);
    expect(group).toBeDefined();
    const children = group!.children ?? [];
    const opportunitiesAt = children.findIndex((c) => c.title === 'Opportunities');
    const teamsAt = children.findIndex((c) => c.title === 'Sales Teams');
    expect(opportunitiesAt).toBeGreaterThanOrEqual(0);
    expect(teamsAt).toBeGreaterThanOrEqual(0);
    expect(opportunitiesAt).toBeLessThan(teamsAt);

    const opportunities = children[opportunitiesAt];
    expect(opportunities.path).toBe('/sales/opportunities');
    expect(opportunities.permission).toBe('sales.opportunities.view');
    expect(opportunities.moduleKey).toBe('sales');
  });
});

describe('filterMenuByModule - Opportunities hides with the sales module off', () => {
  it('drops Opportunities and Sales Teams together when sales is off', () => {
    const group = salesGroup(MENU_SIDEBAR)!;
    // A precondition, not just the post-filter assertion below: without it, this test would
    // pass vacuously today (Opportunities does not exist yet, so it is trivially "not shown").
    expect((group.children ?? []).some((c) => c.title === 'Opportunities')).toBe(true);

    const [kept] = filterMenuByModule([group], new Set(['base', 'product']));
    const titles = (kept.children ?? []).map((c) => c.title);
    expect(titles).not.toContain('Opportunities');
    expect(titles).not.toContain('Sales Teams');
  });

  it('shows Opportunities once the sales module is installed', () => {
    const group = salesGroup(MENU_SIDEBAR)!;
    const [kept] = filterMenuByModule([group], new Set(['base', 'product', 'sales']));
    const titles = (kept.children ?? []).map((c) => c.title);
    expect(titles).toContain('Opportunities');
  });
});
