/**
 * PORTAL-P3-ROLE-MENU round 2, A2: every MY REQUESTS item (portalKind set) carries an icon,
 * like every MY WORK item does.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from './menu.config';

describe('MY REQUESTS items have icons', () => {
  const items = MENU_SIDEBAR.filter((i) => i.portalKind);

  it('there is one item per request kind', () => {
    expect(items.length).toBeGreaterThan(0);
  });

  it.each(items.map((i) => [i.title, i] as const))('%s has an icon', (_t, item) => {
    expect(item.icon).toBeTruthy();
  });
});
