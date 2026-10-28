import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';

import AuditTrail from './AuditTrail';
import type { AuditLogEntry } from '@/types/audit.types';

// AUDIT-TRAIL-RESUBMITTED: every resubmission on a record's trail reads "Resubmitted by <who>"
// and every rejection "Rejected by <who>", derived from the record's own history (oldest
// first), so past resubmits read the same as new ones. Fixtures only, no real data.

const useAuditLogs = vi.fn();

vi.mock('@/hooks/useAuditLogs', () => ({
  useAuditLogs: (...a: unknown[]) => useAuditLogs(...a),
}));

afterEach(() => cleanup());

const RECORD_ID = 'c0000000-0000-4000-8000-000000000002';
const STAFF = { actor_type: 'user', actor_label: 'Tech reviewer' };
const PORTAL = { actor_type: 'contact', actor_label: 'Portal contact' };
const CHATBOT = { actor_type: 'integration', actor_label: 'Chatbot' };

let minute = 0;
function entry(overrides: Partial<AuditLogEntry>): AuditLogEntry {
  minute += 1;
  return {
    id: `log-${minute}`,
    entity_type: 'complaint',
    entity_id: RECORD_ID,
    action: 'UPDATE',
    user_id: null,
    changed_at: `2026-09-01T09:${String(minute).padStart(2, '0')}:00Z`,
    old_values: null,
    new_values: null,
    description: null,
    ip_address: null,
    ...overrides,
  };
}

function status(from: string, to: string, extra: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return entry({
    description: `status: ${from} → ${to}`,
    old_values: { status: from, ...(extra.old_values ?? {}) },
    new_values: { status: to, ...(extra.new_values ?? {}) },
    ...extra,
  });
}

/** The API returns newest first; fixtures are written oldest first for readability. */
function mockHistory(oldestFirst: AuditLogEntry[]) {
  const entries = [...oldestFirst].reverse();
  useAuditLogs.mockReturnValue({
    data: { data: entries, pagination: { total: entries.length, page: 1, limit: 200 }, empty: false },
    isLoading: false,
  });
}

function renderTrail(entityType = 'complaint') {
  render(<AuditTrail entityType={entityType} entityId={RECORD_ID} />);
}

/** Each shown row, oldest first: heading, actor line and change lines. */
function rowsOldestFirst() {
  return screen
    .getAllByRole('listitem')
    .filter((li) => li.dataset.auditEntry)
    .reverse()
    .map((li) => ({
      heading: within(li).getByTestId('audit-action').textContent,
      text: li.textContent ?? '',
      lines: within(li)
        .getAllByTestId('audit-change-line')
        .map((l) => l.textContent),
    }));
}

describe('AuditTrail resubmissions (AUDIT-TRAIL-RESUBMITTED)', () => {
  it('past history, rejected twice and resubmitted from the portal each time, reads Rejected / Resubmitted twice', () => {
    mockHistory([
      entry({ action: 'CREATE', new_values: { status: 'draft' }, ...PORTAL }),
      status('draft', 'submitted', PORTAL),
      status('submitted', 'responded', STAFF),
      status('responded', 'rejected', {
        ...STAFF,
        old_values: { rejection_reason: null },
        new_values: { rejection_reason: 'Photos missing' },
      }),
      // Written before RESUBMITTED-STATUS: the row says rejected -> submitted.
      status('rejected', 'submitted', {
        ...PORTAL,
        old_values: { product_code: 'CWCX604-P-RL-NEW' },
        new_values: { product_code: 'CWCY604' },
      }),
      status('submitted', 'responded', STAFF),
      status('responded', 'rejected', STAFF),
      status('rejected', 'submitted', {
        ...PORTAL,
        old_values: { defect_description: 'Cracked' },
        new_values: { defect_description: 'Cracked, photos attached' },
      }),
    ]);
    renderTrail();

    const rows = rowsOldestFirst();
    expect(rows.map((r) => r.heading)).toEqual([
      'create',
      'update',
      'update',
      'Rejected',
      'Resubmitted',
      'update',
      'Rejected',
      'Resubmitted',
    ]);
    expect(rows[3].text).toContain('by Tech reviewer');
    expect(rows[4].text).toContain('by Portal contact');
    // The past resubmit reads as what it was, with the #1924 field diff under it.
    expect(rows[4].lines).toEqual(['status: rejected → resubmitted', 'Product code: CWCX604-P-RL-NEW → CWCY604']);
    expect(rows[7].lines).toEqual([
      'status: rejected → resubmitted',
      'Defect description: Cracked → Cracked, photos attached',
    ]);
    expect(document.body.textContent).not.toContain('rejected → submitted');
  });

  it('a new portal resubmit (status resubmitted) reads "Resubmitted by <who>" with its diff', () => {
    mockHistory([
      status('responded', 'rejected', STAFF),
      status('rejected', 'resubmitted', {
        ...PORTAL,
        old_values: { product_code: 'A-1' },
        new_values: { product_code: 'B-2' },
      }),
    ]);
    renderTrail();

    const rows = rowsOldestFirst();
    expect(rows.map((r) => r.heading)).toEqual(['Rejected', 'Resubmitted']);
    expect(rows[1].text).toContain('by Portal contact');
    expect(rows[1].lines).toEqual(['status: rejected → resubmitted', 'Product code: A-1 → B-2']);
  });

  it('a chatbot edit of a rejected complaint that kept status rejected (before RESUBMITTED-STATUS) reads Resubmitted', () => {
    mockHistory([
      status('responded', 'rejected', STAFF),
      entry({
        ...CHATBOT,
        old_values: { defect_description: 'Cracked' },
        new_values: { defect_description: 'Cracked on two panels' },
      }),
    ]);
    renderTrail();

    const rows = rowsOldestFirst();
    expect(rows.map((r) => r.heading)).toEqual(['Rejected', 'Resubmitted']);
    expect(rows[1].text).toContain('by Chatbot');
    expect(rows[1].lines).toEqual(['Defect description: Cracked → Cracked on two panels']);
  });

  it('a legacy row without the old status still reads Resubmitted from the status the record left', () => {
    mockHistory([
      status('responded', 'rejected', STAFF),
      entry({
        ...PORTAL,
        old_values: { product_code: 'A-1' },
        new_values: { status: 'submitted', product_code: 'B-2' },
      }),
    ]);
    renderTrail();

    expect(rowsOldestFirst().map((r) => r.heading)).toEqual(['Rejected', 'Resubmitted']);
  });

  it('a staff edit while rejected, and a customer save on a record that is not rejected, stay "update"', () => {
    mockHistory([
      entry({ ...PORTAL, old_values: { product_code: 'A-1' }, new_values: { product_code: 'A-2' } }),
      status('responded', 'rejected', STAFF),
      entry({ ...STAFF, old_values: { salesperson: 'X' }, new_values: { salesperson: 'Y' } }),
    ]);
    renderTrail();

    expect(rowsOldestFirst().map((r) => r.heading)).toEqual(['update', 'Rejected', 'update']);
  });

  it('a stage-based form resubmitted before the status existed (stock inquiry) reads Resubmitted', () => {
    mockHistory([
      status('pending_project_sales', 'rejected', { ...STAFF, entity_type: 'stock_inquiry' }),
      status('rejected', 'pending_project_sales', { ...PORTAL, entity_type: 'stock_inquiry' }),
    ]);
    renderTrail('stock_inquiry');

    const rows = rowsOldestFirst();
    expect(rows.map((r) => r.heading)).toEqual(['Rejected', 'Resubmitted']);
    // Only the plain "submitted" stage is renamed; a named stage stays as recorded.
    expect(rows[1].lines).toEqual(['status: rejected → pending_project_sales']);
  });

  it('a child row on the trail never moves the record status', () => {
    mockHistory([
      status('responded', 'rejected', STAFF),
      entry({
        ...PORTAL,
        entity_type: 'complaint_product_lines',
        entity_id: 'l0000000-0000-4000-8000-000000000009',
        entity_label: 'Product line CWCY604',
        old_values: { status: 'rejected' },
        new_values: { status: 'open' },
      }),
      entry({ ...STAFF, old_values: { salesperson: 'X' }, new_values: { salesperson: 'Y' } }),
    ]);
    renderTrail();

    expect(rowsOldestFirst().map((r) => r.heading)).toEqual(['Rejected', 'update', 'update']);
  });
});
