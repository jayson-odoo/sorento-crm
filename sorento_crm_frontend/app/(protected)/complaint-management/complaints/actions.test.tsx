/**
 * D15 - one definition, one order, one delete gate, for both surfaces.
 *
 * The list row and the record gear each used to declare their own: the row gated
 * Delete on `status !== 'voided'`, the record on that AND its form-action grace
 * window. Now there is one builder and the difference is an explicit input, so a
 * third rule cannot appear by being written somewhere else.
 */
import { describe, it, expect, vi } from 'vitest';

import { complaintActions, isComplaintVoided } from './actions';
import type { Complaint } from './types/complaint.types';

const noop = { onExport: vi.fn(), onDeleteRequested: vi.fn() };

function complaint(over: Partial<Complaint> = {}): Complaint {
  return { id: 'c-1', status: 'submitted', ...over } as Complaint;
}

describe('complaintActions', () => {
  it('reads Download PDF then Delete, with Delete destructive', () => {
    const actions = complaintActions(complaint(), noop);

    expect(actions.map((a) => a.label)).toEqual(['Download PDF', 'Delete']);
    expect(actions[1].kind).toBe('destructive');
  });

  it('offers no Delete on a voided complaint, which is kept for the audit trail', () => {
    const actions = complaintActions(complaint({ status: 'Voided' }), noop);

    expect(actions.map((a) => a.label)).toEqual(['Download PDF']);
    expect(isComplaintVoided(complaint({ status: ' voided ' }))).toBe(true);
  });

  it('drops Delete while the record says a form action is inside its grace window', () => {
    const actions = complaintActions(complaint(), { ...noop, canDelete: false });

    expect(actions.map((a) => a.label)).toEqual(['Download PDF']);
  });

  it('exports that complaint alone, and asks the caller to confirm the delete', () => {
    const onExport = vi.fn();
    const onDeleteRequested = vi.fn();
    const actions = complaintActions(complaint(), { onExport, onDeleteRequested });

    actions[0].run();
    actions[1].run();

    expect(onExport).toHaveBeenCalledWith('c-1');
    expect(onDeleteRequested).toHaveBeenCalledTimes(1);
  });

  it('says the PDF is busy rather than letting a second export be started', () => {
    const actions = complaintActions(complaint(), { ...noop, isExporting: true });

    expect(actions[0].disabled).toBe(true);
  });
});
