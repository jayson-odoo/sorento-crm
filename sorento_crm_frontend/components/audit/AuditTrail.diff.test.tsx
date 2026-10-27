import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';

import AuditTrail from './AuditTrail';
import type { AuditLogEntry } from '@/types/audit.types';

// AUDIT-TRAIL-DIFF: an UPDATE lists every field it changed; a status summary is an extra
// first line, never a replacement. Shapes mirror two portal resubmits (fixtures, no real data).

const useAuditLogs = vi.fn();

vi.mock('@/hooks/useAuditLogs', () => ({
  useAuditLogs: (...a: unknown[]) => useAuditLogs(...a),
}));

afterEach(() => cleanup());

const COMPLAINT_ID = 'c0000000-0000-4000-8000-000000000001';

function entry(overrides: Partial<AuditLogEntry>): AuditLogEntry {
  return {
    id: `log-${Math.random()}`,
    entity_type: 'complaint',
    entity_id: COMPLAINT_ID,
    action: 'UPDATE',
    user_id: null,
    actor_label: 'Portal contact',
    changed_at: '2026-08-28T10:09:00Z',
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

function renderTrail() {
  render(<AuditTrail entityType="complaint" entityId={COMPLAINT_ID} />);
}

const BEFORE = 'A'.repeat(251);
const AFTER = `${BEFORE}${' appended detail'.padEnd(169, '.')}`;

describe('AuditTrail field diff (AUDIT-TRAIL-DIFF)', () => {
  it('resubmit with a long text append: shows the status summary AND the description change', () => {
    mockEntries([
      entry({
        description: 'status: rejected → submitted',
        old_values: { status: 'rejected', defect_description: BEFORE, portal_draft_at: '2026-08-28T10:00:00' },
        new_values: { status: 'submitted', defect_description: AFTER, portal_draft_at: null },
      }),
    ]);
    renderTrail();
    const lines = screen.getAllByTestId('audit-change-line').map((li) => li.textContent);
    expect(lines[0]).toBe('status: rejected → submitted');
    // The summary already says it; the raw status field is not listed twice.
    expect(lines.filter((l) => l?.includes('rejected'))).toHaveLength(1);
    // Long text: a collapsible before/after, with BOTH full values present (never cut).
    const desc = screen.getByText('Defect description changed');
    const block = desc.closest('details') as HTMLElement;
    expect(block).not.toBeNull();
    expect(within(block).getByTestId('audit-before').textContent).toBe(BEFORE);
    expect(within(block).getByTestId('audit-after').textContent).toBe(AFTER);
    // Bookkeeping fields never show.
    expect(document.body.textContent).not.toMatch(/portal draft/i);
  });

  it('resubmit with a product code swap: shows the status summary AND "Product code: old → new"', () => {
    mockEntries([
      entry({
        description: 'status: rejected → submitted',
        old_values: { status: 'rejected', product_code: 'CWCX604-P-RL-NEW', last_responded_at: '2026-08-30T00:00:00' },
        new_values: { status: 'submitted', product_code: 'CWCY604', last_responded_at: '2026-09-01T01:33:00' },
      }),
    ]);
    renderTrail();
    const lines = screen.getAllByTestId('audit-change-line').map((li) => li.textContent);
    expect(lines).toEqual(['status: rejected → submitted', 'Product code: CWCX604-P-RL-NEW → CWCY604']);
  });

  it('hides an UPDATE whose only change is a bookkeeping field', () => {
    mockEntries([
      entry({ id: 'noise', old_values: { updated_at: '1' }, new_values: { updated_at: '2' } }),
      entry({ id: 'real', old_values: { quantity: '2' }, new_values: { quantity: '3' } }),
    ]);
    renderTrail();
    expect(screen.getAllByRole('listitem').filter((li) => li.dataset.auditEntry)).toHaveLength(1);
    expect(screen.queryByText('Updated')).not.toBeInTheDocument();
    expect(screen.getByText('Quantity: 2 → 3')).toBeInTheDocument();
  });

  it('a child row reads as the child, named by its label, never by id', () => {
    const lineId = 'd0000000-0000-4000-8000-000000000002';
    mockEntries([
      entry({
        entity_type: 'complaint_product_lines',
        entity_id: lineId,
        entity_label: 'Product line CWCY604',
        action: 'INSERT',
        new_values: { id: lineId, complaint_id: COMPLAINT_ID, product_code: 'CWCY604' },
      }),
      entry({
        entity_type: 'complaint_product_lines',
        entity_id: lineId,
        entity_label: 'Product line CWCY604',
        action: 'UPDATE',
        old_values: { quantity: '2' },
        new_values: { quantity: '3' },
      }),
      entry({
        entity_type: 'complaint_product_lines',
        entity_id: lineId,
        entity_label: 'Product line CWCX604-P-RL-NEW',
        action: 'DELETE',
        old_values: { id: lineId, product_code: 'CWCX604-P-RL-NEW' },
      }),
    ]);
    renderTrail();
    expect(screen.getByText('Product line CWCY604 added')).toBeInTheDocument();
    expect(screen.getByText('Product line CWCY604: Quantity: 2 → 3')).toBeInTheDocument();
    expect(screen.getByText('Product line CWCX604-P-RL-NEW removed')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(lineId);
  });

  it('an id-valued field reads as changed, never as raw ids', () => {
    const a = 'e0000000-0000-4000-8000-000000000003';
    const b = 'e0000000-0000-4000-8000-000000000004';
    mockEntries([entry({ old_values: { root_cause_id: a }, new_values: { root_cause_id: b } })]);
    renderTrail();
    expect(screen.getByText('Root cause changed')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(a);
  });

  // Owner + Kay, 27 Oct: rejected -> submitted reads "Resubmitted", derived from the transition
  // so existing history shows it without a data change. Same two resubmit shapes as above.
  it('resubmit shape 1 (status + long text append) heads the row "Resubmitted by <actor>"', () => {
    mockEntries([
      entry({
        description: 'status: rejected → submitted',
        old_values: { status: 'rejected', defect_description: BEFORE },
        new_values: { status: 'submitted', defect_description: AFTER },
      }),
    ]);
    renderTrail();
    const row = screen.getAllByRole('listitem').find((li) => li.dataset.auditEntry) as HTMLElement;
    expect(within(row).getByTestId('audit-action').textContent).toBe('Resubmitted');
    expect(row.textContent).toContain('by Portal contact');
    expect(within(row).getByText('Defect description changed')).toBeInTheDocument();
  });

  it('resubmit shape 2 (status + product code) heads the row "Resubmitted" with the field change under it', () => {
    mockEntries([
      entry({
        description: 'status: rejected → submitted',
        old_values: { status: 'rejected', product_code: 'CWCX604-P-RL-NEW' },
        new_values: { status: 'submitted', product_code: 'CWCY604' },
      }),
    ]);
    renderTrail();
    expect(screen.getByTestId('audit-action').textContent).toBe('Resubmitted');
    expect(screen.getByText('Product code: CWCX604-P-RL-NEW → CWCY604')).toBeInTheDocument();
  });

  it('the real resubmitted status (RESUBMITTED-STATUS) heads the row "Resubmitted" too', () => {
    mockEntries([
      // No summary on the row: the raw values alone must say it is a resubmit.
      entry({
        description: null,
        old_values: { status: 'rejected', product_code: 'CWCX604-P-RL-NEW' },
        new_values: { status: 'resubmitted', product_code: 'CWCY604' },
      }),
    ]);
    renderTrail();
    expect(screen.getByTestId('audit-action').textContent).toBe('Resubmitted');
  });

  it('a status-engine record (status_id, labels only in the summary) also reads "Resubmitted"', () => {
    mockEntries([
      entry({
        entity_type: 'purchase_request',
        description: 'Status: Rejected → Submitted',
        old_values: { status_id: 'f0000000-0000-4000-8000-000000000005' },
        new_values: { status_id: 'f0000000-0000-4000-8000-000000000006' },
      }),
    ]);
    render(<AuditTrail entityType="purchase_request" entityId={COMPLAINT_ID} />);
    expect(screen.getByTestId('audit-action').textContent).toBe('Resubmitted');
  });

  it('any other status move keeps the plain action heading', () => {
    mockEntries([
      entry({
        description: 'status: submitted → approved',
        old_values: { status: 'submitted' },
        new_values: { status: 'approved' },
      }),
    ]);
    renderTrail();
    expect(screen.getByTestId('audit-action').textContent).toBe('update');
  });

  it('a status_id move under an unrelated stored description is still listed', () => {
    mockEntries([
      entry({
        entity_type: 'purchase_request',
        description: 'Approved by procurement',
        old_values: { status_id: 'f0000000-0000-4000-8000-000000000005' },
        new_values: { status_id: 'f0000000-0000-4000-8000-000000000006' },
      }),
    ]);
    render(<AuditTrail entityType="purchase_request" entityId={COMPLAINT_ID} />);
    const lines = screen.getAllByTestId('audit-change-line').map((li) => li.textContent);
    expect(lines).toEqual(['Approved by procurement', 'Status changed']);
  });

  it('a page whose rows are all bookkeeping says so instead of "no history"', () => {
    mockEntries([entry({ old_values: { updated_at: '1' }, new_values: { updated_at: '2' } })]);
    renderTrail();
    expect(screen.getByText('No field changes to show.')).toBeInTheDocument();
    expect(screen.queryByText('No audit history for this record.')).not.toBeInTheDocument();
  });
});
