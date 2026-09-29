/** AC-ST208: Sales > Customer asks sits right after Opportunities, gated by its own slug. */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from './menu.config';
import type { MenuConfig } from './types';

function salesChildren(menu: MenuConfig) {
  return menu.find((item) => !item.heading && item.title === 'Sales')!.children!;
}

describe('MENU_SIDEBAR - Customer asks entry', () => {
  const menu = MENU_SIDEBAR;
  it('is Customer asks -> /sales/customer-asks, after Opportunities', () => {
    const children = salesChildren(menu);
    const at = children.findIndex((c) => c.title === 'Customer asks');
    expect(at).toBeGreaterThan(-1);
    expect(children[at - 1].title).toBe('Opportunities');
    expect(children[at]).toMatchObject({
      path: '/sales/customer-asks',
      permission: 'sales.customer_asks.view',
      moduleKey: 'sales',
    });
  });
});
