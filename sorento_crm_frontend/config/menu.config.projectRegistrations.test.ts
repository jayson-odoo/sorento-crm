/**
 * RW14: the Registrations queue is gone (PLAN R11). A pending registration is a project on the
 * pipeline, so no sidebar carries a Registrations entry any more.
 */
import { describe, expect, it } from 'vitest';
import { MENU_MEGA, MENU_SIDEBAR, MENU_SIDEBAR_COMPACT } from './menu.config';
import type { MenuConfig, MenuItem } from './types';

function walk(items: MenuConfig | MenuItem[] | undefined, out: MenuItem[] = []): MenuItem[] {
  for (const item of items ?? []) {
    out.push(item);
    walk(item.children, out);
  }
  return out;
}

describe.each([
  ['MENU_SIDEBAR', MENU_SIDEBAR],
  ['MENU_SIDEBAR_COMPACT', MENU_SIDEBAR_COMPACT],
  ['MENU_MEGA', MENU_MEGA],
] as const)('%s', (_name, menu) => {
  it('has no Registrations item and no entry on the removed path', () => {
    const all = walk(menu);
    expect(all.filter((i) => i.path === '/project-sales/registrations')).toEqual([]);
    expect(all.filter((i) => i.title === 'Registrations')).toEqual([]);
  });

  it('no item is gated on the approve permission (the header button is, not the menu)', () => {
    expect(walk(menu).filter((i) => i.permission === 'projects.registrations.approve')).toEqual([]);
  });

});

describe.each([
  ['MENU_SIDEBAR', MENU_SIDEBAR],
  ['MENU_SIDEBAR_COMPACT', MENU_SIDEBAR_COMPACT],
] as const)('%s', (_name, menu) => {
  // The mega menu never carried the pipeline entry; the sidebars do.
  it('keeps the Projects and Pipeline entries', () => {
    const paths = walk(menu).map((i) => i.path);
    expect(paths).toContain('/project-sales/pipeline');
  });
});
