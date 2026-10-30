/**
 * AC-SR-50 (amended by PS-REGISTER-CHECK-FIRST AC-T1..T3): the project detail tabs read, in order,
 * Overview, Documents, Quotation, Samples Request, Sponsorship Form, PO, SO, Stakeholders, Tasks,
 * Activity. There is no Samples tab; its old link opens Samples Request, and the retired order
 * links open PO. Tab ids stay as today (`sample-requests`, `orders` for PO); SO is `sales-orders`.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import * as client from './ProjectDetailClient';

const tabs = () =>
  (client as unknown as { TABS?: ReadonlyArray<{ id: string; label: string }> }).TABS!;

describe('project detail tabs', () => {
  it('AC-T1 labels and order are exact', () => {
    expect(tabs(), 'ProjectDetailClient must export TABS').toBeDefined();
    expect(tabs().map((t) => t.label)).toEqual([
      'Overview',
      'Documents',
      'Quotation',
      'Samples Request',
      'Sponsorship Form',
      'PO',
      'SO',
      'Stakeholders',
      'Tasks',
      'Activity',
    ]);
  });

  it('AC-T3 there is no Samples tab', () => {
    expect(tabs().map((t) => t.label)).not.toContain('Samples');
    expect(tabs().map((t) => t.id)).not.toContain('samples');
  });

  it('AC-T3 ?tab=samples opens Samples Request', () => {
    const idOf = (label: string) => tabs().find((t) => t.label === label)?.id;
    expect(idOf('Samples Request')).toBe('sample-requests');
    expect(client.resolveProjectTab('samples')).toBe('sample-requests');
  });

  it.each(['orders', 'pos', 'schedules'])('AC-T3 ?tab=%s opens PO', (legacy) => {
    const po = tabs().find((t) => t.label === 'PO')?.id;
    expect(po).toBe('orders');
    expect(client.resolveProjectTab(legacy)).toBe(po);
  });

  it('AC-T2 SO is its own tab, distinct from PO', () => {
    const so = tabs().find((t) => t.label === 'SO')?.id;
    expect(so).toBe('sales-orders');
    expect(client.resolveProjectTab('sales-orders')).toBe('sales-orders');
    expect(client.resolveProjectTab('sales-orders-tab')).toBe('overview');
  });
});
