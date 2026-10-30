/**
 * PORTAL-P3-ROLE-MENU round 3, T1: the breadcrumb a staff page shows is the one it showed before
 * the salesperson block was added (the most specific match wins, the first of equal length wins,
 * so the block must not sit ahead of the staff groups).
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from './menu.config';
import { useMenu } from '@/hooks/use-menu';

const trail = (pathname: string) =>
  useMenu(pathname)
    .getBreadcrumb(MENU_SIDEBAR)
    .map((i) => i.title);

describe('staff breadcrumbs through MENU_SIDEBAR', () => {
  it.each([
    ['/project-sales/pipeline', ['Project Sales', 'Projects']],
    ['/sla-management/conversations', ['SLA', 'Conversations']],
    ['/sales/customer-asks', ['Sales', 'Customer asks']],
  ])('%s -> %j', (path, expected) => {
    expect(trail(path)).toEqual(expected);
  });
});
