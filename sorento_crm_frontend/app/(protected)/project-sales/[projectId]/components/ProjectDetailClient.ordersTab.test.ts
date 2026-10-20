/** PM-SIMPLIFY AC-O1: one Orders tab; the old tab links still land on it. */
import { describe, expect, it } from 'vitest';
import { TABS, resolveProjectTab } from './ProjectDetailClient';

describe('the Orders tab', () => {
  it('replaces POs, Delivery schedules and Sales orders', () => {
    const labels = TABS.map((tab) => tab.label);
    expect(labels).toContain('Orders');
    expect(labels).not.toContain('POs');
    expect(labels).not.toContain('Delivery schedules');
    expect(labels).not.toContain('Sales orders');
    expect(TABS).toHaveLength(11);
  });

  it('opens Orders for the old ?tab= links', () => {
    expect(resolveProjectTab('pos')).toBe('orders');
    expect(resolveProjectTab('schedules')).toBe('orders');
    expect(resolveProjectTab('sales-orders')).toBe('orders');
    expect(resolveProjectTab('orders')).toBe('orders');
    expect(resolveProjectTab(null)).toBe('overview');
    expect(resolveProjectTab('nonsense')).toBe('overview');
  });
});
