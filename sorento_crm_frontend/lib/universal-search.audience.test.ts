/**
 * PORTAL-P3-ROLE-MENU round 3, T2: universal search applies the sidebar's audience and
 * portalKind filter, so staff never see the salesperson block and a salesperson sees only the
 * request kinds the contact has.
 */
import { describe, expect, it } from 'vitest';
import { MENU_SIDEBAR } from '@/config/menu.config';
import { createMenuSearchProvider } from '@/lib/universal-search';

type Ctx = Parameters<ReturnType<typeof createMenuSearchProvider>['search']>[1];

const provider = createMenuSearchProvider(MENU_SIDEBAR);
const search = async (q: string, ctx: Record<string, unknown>) =>
  await provider.search(q, ctx as unknown as Ctx);

const ALL = new Set([
  'projects.projects.view',
  'projects.projects.view_own',
  'sla_management.conversations.view',
  'sla_management.conversations.view_own',
  'sales.customer_asks.view',
  'sales.customer_asks.edit',
]);

describe('universal search audience', () => {
  it('staff: no /my-requests result at all', async () => {
    const out = await search('my-requests', { permissionSet: ALL, salesperson: null });
    expect(out).toEqual([]);
  });

  it('staff: Customer asks appears once (no duplicate from the salesperson block)', async () => {
    const out = await search('customer-asks', { permissionSet: ALL, salesperson: null });
    expect(out.filter((r) => r.path === '/sales/customer-asks')).toHaveLength(1);
  });

  it('salesperson: MY REQUESTS results only for the kinds in portalKinds', async () => {
    const out = await search('my-requests', {
      permissionSet: ALL,
      salesperson: { portalKinds: ['stock_inquiry', 'complaint'] },
    });
    expect(out.map((r) => r.path).sort()).toEqual([
      '/my-requests?type=complaint',
      '/my-requests?type=stock_inquiry',
    ]);
  });

  it('salesperson: Customer asks appears once (the MY WORK one)', async () => {
    const out = await search('customer-asks', {
      permissionSet: ALL,
      salesperson: { portalKinds: [] },
    });
    expect(out.filter((r) => r.path === '/sales/customer-asks')).toHaveLength(1);
  });
});
