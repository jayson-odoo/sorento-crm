import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import AuditTrail from './AuditTrail';
import type { AuditLogEntry } from '@/types/audit.types';

// OCN-ORDER-CHANGE-NOTICE round 7 (browser pass): an order change notice's History reads in words.
// The backend words the status move and the held action ("Status: Approved → Done", "Mark done
// applied"); the stored code ("processed_by_cs") never shows under it.

const useAuditLogs = vi.fn();

vi.mock('@/hooks/useAuditLogs', () => ({
  useAuditLogs: (...a: unknown[]) => useAuditLogs(...a),
}));

afterEach(() => cleanup());

const OCN_ID = 'b2c3d4e5-0302-4a00-8000-000000000302';

function entry(overrides: Partial<AuditLogEntry>): AuditLogEntry {
  return {
    id: `log-${Math.random()}`,
    entity_type: 'order_change_notice',
    entity_id: OCN_ID,
    action: 'UPDATE',
    user_id: null,
    actor_label: 'CS Person A',
    changed_at: '2026-11-12T20:08:00Z',
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

describe('AuditTrail on an order change notice', () => {
  it('shows the worded status move once, never the stored code', () => {
    mockEntries([
      entry({
        description: 'Status: Approved → Done',
        old_values: { status: 'approved', cs_comment: null },
        new_values: { status: 'processed_by_cs', cs_comment: 'Stock released.' },
      }),
    ]);
    render(<AuditTrail entityType="order_change_notice" entityId={OCN_ID} />);
    const lines = screen.getAllByTestId('audit-change-line').map((li) => li.textContent);
    expect(lines[0]).toBe('Status: Approved → Done');
    expect(lines).toContain('Cs comment: (empty) → Stock released.');
    expect(document.body.textContent).not.toMatch(/processed_by_cs/);
  });

  it('shows a held move by its name, never the action key', () => {
    mockEntries([entry({ description: 'Mark done applied' })]);
    render(<AuditTrail entityType="order_change_notice" entityId={OCN_ID} />);
    expect(screen.getAllByTestId('audit-change-line').map((li) => li.textContent)).toEqual(['Mark done applied']);
    expect(document.body.textContent).not.toMatch(/ocn\./);
  });
});
