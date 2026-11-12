import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import AuditTrail from './AuditTrail';
import type { AuditLogEntry } from '@/types/audit.types';

// SUPPLIER-COST-ACCESS: for a reader without `products.cost.view` the server replaces a cost
// value with "hidden" (old and new alike) and names the field in `masked_fields`. The trail
// must still say the cost changed, by whom, and never print a value.

const useAuditLogs = vi.fn();

vi.mock('@/hooks/useAuditLogs', () => ({
  useAuditLogs: (...a: unknown[]) => useAuditLogs(...a),
}));

afterEach(() => cleanup());

const PRODUCT_ID = 'p0000000-0000-4000-8000-000000000001';

function entry(overrides: Partial<AuditLogEntry>): AuditLogEntry {
  return {
    id: `log-${Math.random()}`,
    entity_type: 'product',
    entity_id: PRODUCT_ID,
    action: 'UPDATE',
    user_id: null,
    actor_label: 'ZZT Buyer',
    changed_at: '2026-11-10T06:02:00Z',
    old_values: null,
    new_values: null,
    description: null,
    ip_address: null,
    ...overrides,
  };
}

function mockEntries(entries: AuditLogEntry[]) {
  useAuditLogs.mockReturnValue({
    data: { data: entries, pagination: { total: entries.length, page: 1, limit: 50 }, empty: entries.length === 0 },
    isLoading: false,
  });
}

describe('AuditTrail masked cost fields (SUPPLIER-COST-ACCESS)', () => {
  it('shows that the cost changed, with no value, when the server masked it', () => {
    mockEntries([
      entry({
        old_values: { cost_price: 'hidden' },
        new_values: { cost_price: 'hidden' },
        masked_fields: ['cost_price'],
      }),
    ]);
    render(<AuditTrail entityType="product" entityId={PRODUCT_ID} />);
    const lines = screen.getAllByTestId('audit-change-line').map((li) => li.textContent);
    expect(lines).toEqual(['Cost price changed (values hidden)']);
    expect(screen.getByText(/ZZT Buyer/)).toBeInTheDocument();
  });

  it('shows the values to a reader the server did not mask', () => {
    mockEntries([
      entry({ old_values: { cost_price: '120.00' }, new_values: { cost_price: '125.00' } }),
    ]);
    render(<AuditTrail entityType="product" entityId={PRODUCT_ID} />);
    const lines = screen.getAllByTestId('audit-change-line').map((li) => li.textContent);
    expect(lines).toEqual(['Cost price: 120.00 → 125.00']);
  });
});
