import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';

import AuditTrail from './AuditTrail';
import type { AuditLogEntry } from '@/types/audit.types';

// AUDIT-TRAIL-RESUBMITTED: every resubmission on a record's trail reads "Appealed by <who>"
// and every rejection "Rejected by <who>", derived from the record's own history (oldest
// first), so past resubmits read the same as new ones. Every form calls a resubmission an appeal
// (COMPLAINT-APPEAL-WORDING, owner 28 Oct): the heading reads "Appealed". Fixtures only, no real data.

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

function status(
  from: string,
  to: string,
  extra: Partial<AuditLogEntry> = {},
): AuditLogEntry {
  return entry({
    ...extra,
    description: `status: ${from} → ${to}`,
    old_values: { status: from, ...(extra.old_values ?? {}) },
    new_values: { status: to, ...(extra.new_values ?? {}) },
  });
}

/** The API returns newest first; fixtures are written oldest first for readability. */
function mockHistory(oldestFirst: AuditLogEntry[]) {
  const entries = [...oldestFirst].reverse();
  useAuditLogs.mockReturnValue({
    data: {
      data: entries,
      pagination: { total: entries.length, page: 1, limit: 200 },
      empty: false,
    },
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
  it('past history, rejected twice and resubmitted from the portal each time, reads Rejected / Appealed twice', () => {
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
      'Appealed',
      'update',
      'Rejected',
      'Appealed',
    ]);
    expect(rows[3].text).toContain('by Tech reviewer');
    expect(rows[4].text).toContain('by Portal contact');
    // The past resubmit reads as what it was, with the #1924 field diff under it.
    expect(rows[4].lines).toEqual([
      'status: rejected → appealed',
      'Product code: CWCX604-P-RL-NEW → CWCY604',
    ]);
    expect(rows[7].lines).toEqual([
      'status: rejected → appealed',
      'Defect description: Cracked → Cracked, photos attached',
    ]);
    expect(document.body.textContent).not.toContain('rejected → submitted');
  });

  it('a new portal resubmit (status resubmitted) reads "Appealed by <who>" with its diff', () => {
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
    expect(rows.map((r) => r.heading)).toEqual(['Rejected', 'Appealed']);
    expect(rows[1].text).toContain('by Portal contact');
    expect(rows[1].lines).toEqual([
      'status: rejected → appealed',
      'Product code: A-1 → B-2',
    ]);
  });

  it('a chatbot edit of a rejected complaint that kept status rejected (before RESUBMITTED-STATUS) reads Appealed', () => {
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
    expect(rows.map((r) => r.heading)).toEqual(['Rejected', 'Appealed']);
    expect(rows[1].text).toContain('by Chatbot');
    expect(rows[1].lines).toEqual([
      'Defect description: Cracked → Cracked on two panels',
    ]);
  });

  it('a legacy row without the old status still reads Appealed from the status the record left', () => {
    mockHistory([
      status('responded', 'rejected', STAFF),
      entry({
        ...PORTAL,
        old_values: { product_code: 'A-1' },
        new_values: { status: 'submitted', product_code: 'B-2' },
      }),
    ]);
    renderTrail();

    expect(rowsOldestFirst().map((r) => r.heading)).toEqual([
      'Rejected',
      'Appealed',
    ]);
  });

  it('a customer save on a row written before the actor columns (actor legacy, a contact id) reads Appealed', () => {
    mockHistory([
      status('responded', 'rejected', STAFF),
      entry({
        actor_type: 'legacy',
        contact_id: 'a0000000-0000-4000-8000-000000000003',
        user_display_name: 'Customer A',
        old_values: { defect_description: 'Cracked' },
        new_values: { defect_description: 'Cracked, photos attached' },
      }),
    ]);
    renderTrail();

    const rows = rowsOldestFirst();
    expect(rows.map((r) => r.heading)).toEqual(['Rejected', 'Appealed']);
    expect(rows[1].text).toContain('by Customer A');
  });

  it('an integration save on a rejected record after the Resubmitted status went live stays "update"', () => {
    mockHistory([
      status('responded', 'rejected', { ...STAFF, changed_at: '2026-10-29T01:00:00Z' }),
      entry({
        ...CHATBOT,
        changed_at: '2026-10-29T02:00:00Z',
        old_values: { salesperson: 'X' },
        new_values: { salesperson: 'Y' },
      }),
    ]);
    renderTrail();

    expect(rowsOldestFirst().map((r) => r.heading)).toEqual(['Rejected', 'update']);
  });

  it('a staff edit while rejected, and a customer save on a record that is not rejected, stay "update"', () => {
    mockHistory([
      entry({
        ...PORTAL,
        old_values: { product_code: 'A-1' },
        new_values: { product_code: 'A-2' },
      }),
      status('responded', 'rejected', STAFF),
      entry({
        ...STAFF,
        old_values: { salesperson: 'X' },
        new_values: { salesperson: 'Y' },
      }),
    ]);
    renderTrail();

    expect(rowsOldestFirst().map((r) => r.heading)).toEqual([
      'update',
      'Rejected',
      'update',
    ]);
  });

  it('a stage-based form resubmitted before the status existed (stock inquiry) reads Appealed', () => {
    mockHistory([
      status('pending_project_sales', 'rejected', {
        ...STAFF,
        entity_type: 'stock_inquiry',
      }),
      status('rejected', 'pending_project_sales', {
        ...PORTAL,
        entity_type: 'stock_inquiry',
      }),
    ]);
    renderTrail('stock_inquiry');

    const rows = rowsOldestFirst();
    expect(rows.map((r) => r.heading)).toEqual(['Rejected', 'Appealed']);
    // Only the plain "submitted" stage is renamed; a named stage stays as recorded.
    expect(rows[1].lines).toEqual(['status: rejected → pending_project_sales']);
  });

  it('a status-engine record (labels only in the summary) reads Rejected, then Appealed on the customer save', () => {
    const engine = { entity_type: 'purchase_request' };
    mockHistory([
      entry({
        ...engine,
        ...STAFF,
        description: 'Status: Submitted → Rejected',
        old_values: { status_id: 'f0000000-0000-4000-8000-000000000006' },
        new_values: { status_id: 'f0000000-0000-4000-8000-000000000007' },
      }),
      entry({ ...engine, ...PORTAL, old_values: { remarks: 'a' }, new_values: { remarks: 'b' } }),
    ]);
    renderTrail('purchase_request');

    expect(rowsOldestFirst().map((r) => r.heading)).toEqual(['Rejected', 'Appealed']);
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
        new_values: { status: 'submitted' },
      }),
      // Still rejected: the record's own customer save is the resubmit, not the child's move.
      entry({ ...PORTAL, old_values: { product_code: 'A-1' }, new_values: { product_code: 'A-2' } }),
    ]);
    renderTrail();

    expect(rowsOldestFirst().map((r) => r.heading)).toEqual(['Rejected', 'update', 'Appealed']);
  });

  it('a complaint never says resubmit: the appeal and the staff answer to it both read appealed', () => {
    mockHistory([
      status('responded', 'rejected', STAFF),
      status('rejected', 'resubmitted', PORTAL),
      status('resubmitted', 'responded', STAFF),
    ]);
    renderTrail();

    const rows = rowsOldestFirst();
    expect(rows.map((r) => r.heading)).toEqual(['Rejected', 'Appealed', 'update']);
    expect(rows[1].lines).toEqual(['status: rejected → appealed']);
    expect(rows[2].lines).toEqual(['status: appealed → responded']);
    expect(document.body.textContent).not.toMatch(/resubmit/i);
  });

  it('a customer note that says "resubmitted" is quoted as written, never reworded', () => {
    mockHistory([
      status('responded', 'rejected', STAFF),
      status('rejected', 'resubmitted', {
        ...PORTAL,
        old_values: { defect_description: 'Cracked' },
        new_values: { defect_description: 'Cracked, resubmitted with photos' },
      }),
    ]);
    renderTrail();

    expect(rowsOldestFirst()[1].lines).toEqual([
      'status: rejected → appealed',
      'Defect description: Cracked → Cracked, resubmitted with photos',
    ]);
  });

  it('an undo reason that says "resubmitted" is quoted as typed', () => {
    mockHistory([
      status('rejected', 'resubmitted', PORTAL),
      entry({
        ...STAFF,
        description: 'Undo: customer resubmitted the wrong photos (reversed approve)',
        old_values: { status: 'approved' },
        new_values: { status: 'resubmitted' },
      }),
    ]);
    renderTrail();

    expect(rowsOldestFirst()[1].lines[0]).toBe(
      'Undo: customer resubmitted the wrong photos (reversed approve)',
    );
  });
});
