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
    expect(lines).toContain('Customer Service comment: (empty) → Stock released.');
    expect(document.body.textContent).not.toMatch(/processed_by_cs/);
  });

  it('shows a held move by its name, never the action key', () => {
    mockEntries([entry({ description: 'Mark done applied' })]);
    render(<AuditTrail entityType="order_change_notice" entityId={OCN_ID} />);
    expect(screen.getAllByTestId('audit-change-line').map((li) => li.textContent)).toEqual(['Mark done applied']);
    expect(document.body.textContent).not.toMatch(/ocn\./);
  });
});

describe('AuditTrail field names on an order change notice (round 9)', () => {
  it('names each field as the notice does, never the column', () => {
    mockEntries([
      entry({
        old_values: {
          approval_comments: null,
          void_reason: null,
          customer_po_no: 'XT04/3871',
          so_no_text: null,
          requested_approval_by_user_id: null,
          approver_id: null,
        },
        new_values: {
          approval_comments: 'Fine by me',
          void_reason: 'Raised by mistake',
          customer_po_no: 'XT04/3871 (R1)',
          so_no_text: 'SO397450',
          requested_approval_by_user_id: '2f6b9d38-5e41-4c97-8a20-4d7c1b0e6f06',
          approver_id: '638d8b89-42f4-45a1-9b0e-3c1b8f9a2d02',
        },
      }),
    ]);
    render(<AuditTrail entityType="order_change_notice" entityId={OCN_ID} />);
    const lines = screen.getAllByTestId('audit-change-line').map((li) => li.textContent);
    expect(lines).toEqual([
      'Approval remarks: (empty) → Fine by me',
      'Void reason: (empty) → Raised by mistake',
      'Customer PO no.: XT04/3871 → XT04/3871 (R1)',
      'SO no.: (empty) → SO397450',
      'Approval requester changed',
      'Approver changed',
    ]);
  });

  it('leaves every other record type as it was', () => {
    mockEntries([
      entry({ entity_type: 'complaint', old_values: { cs_comment: null }, new_values: { cs_comment: 'Called back' } }),
    ]);
    render(<AuditTrail entityType="complaint" entityId={OCN_ID} />);
    expect(screen.getAllByTestId('audit-change-line').map((li) => li.textContent)).toEqual([
      'Cs comment: (empty) → Called back',
    ]);
  });
});

describe('AuditTrail values (round 11, review R3)', () => {
  it('reads the amendment change table as "Change rows changed", never JSON or line ids', () => {
    mockEntries([
      entry({
        old_values: { change_table_json: null },
        new_values: {
          change_table_json: {
            rows: [{ so_line_id: '4a1b2c3d-0000-4000-8000-0000000000aa', row_key: '0', verb: 'DELAY' }],
            verb_summary: { DELAY: 1 },
          },
        },
      }),
    ]);
    render(<AuditTrail entityType="order_change_notice" entityId={OCN_ID} />);
    expect(screen.getAllByTestId('audit-change-line').map((li) => li.textContent)).toEqual(['Change rows changed']);
    expect(document.body.textContent).not.toMatch(/so_line_id|\{|4a1b2c3d/);
  });

  it('does the same for structured values on any record', () => {
    mockEntries([
      entry({
        entity_type: 'complaint',
        old_values: { products: [{ id: '4a1b2c3d-0000-4000-8000-0000000000bb', qty: 1 }] },
        new_values: { products: [{ id: '4a1b2c3d-0000-4000-8000-0000000000bb', qty: 2 }] },
      }),
    ]);
    render(<AuditTrail entityType="complaint" entityId={OCN_ID} />);
    expect(screen.getAllByTestId('audit-change-line').map((li) => li.textContent)).toEqual(['Products changed']);
  });

  it('keeps a plain list of words as words', () => {
    mockEntries([entry({ entity_type: 'complaint', old_values: { tags: ['a'] }, new_values: { tags: ['a', 'b'] } })]);
    render(<AuditTrail entityType="complaint" entityId={OCN_ID} />);
    expect(screen.getAllByTestId('audit-change-line').map((li) => li.textContent)).toEqual(['Tags: a → a, b']);
  });

  it("words the notice's coded values as its pages do", () => {
    mockEntries([
      entry({
        old_values: { approval_status: null, source: null, status: 'approved' },
        new_values: { approval_status: 'pending', source: 'crm', status: 'processed_by_cs' },
      }),
    ]);
    render(<AuditTrail entityType="order_change_notice" entityId={OCN_ID} />);
    const lines = screen.getAllByTestId('audit-change-line').map((li) => li.textContent);
    expect(lines).toEqual([
      'Approval status: (empty) → Pending',
      'Source: (empty) → CRM',
      'Status: Approved → Done',
    ]);
    expect(document.body.textContent).not.toMatch(/pending|crm|processed_by_cs/);
  });
});

describe('AuditTrail user fields on an order change notice (round 15)', () => {
  it('reads the approver by the name the History API sends, old to new', () => {
    mockEntries([
      entry({
        old_values: { approver_id: null, requested_approval_by_user_id: null },
        new_values: { approver_id: 'Manager A', requested_approval_by_user_id: 'Admin A' },
      }),
    ]);
    render(<AuditTrail entityType="order_change_notice" entityId={OCN_ID} />);
    expect(screen.getAllByTestId('audit-change-line').map((li) => li.textContent)).toEqual([
      'Approver: (empty) → Manager A',
      'Approval requester: (empty) → Admin A',
    ]);
  });
});
