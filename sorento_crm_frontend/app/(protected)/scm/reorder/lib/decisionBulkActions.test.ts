/**
 * SCM M4 Slice B - buildResultsBulkActions gating (AC-M4.9).
 * The unified Actions dropdown lists the CHANGEABLE actions for the selection: a
 * decision is reversible, so Accept shows unless every selected row is already
 * accepted, Reject shows unless every selected row is already rejected, and the
 * button is hidden only on an empty selection.
 */
import { describe, it, expect, vi } from 'vitest';
import { buildResultsBulkActions } from './decisionBulkActions';

describe('buildResultsBulkActions (AC-M4.9)', () => {
  it('returns [] when nothing would change (Actions button hidden)', () => {
    expect(
      buildResultsBulkActions({ acceptCount: 0, rejectCount: 0 }, { onAccept: vi.fn(), onReject: vi.fn() }),
    ).toEqual([]);
  });

  it('lists Accept + Reject when both would change ≥1 selected row', () => {
    const actions = buildResultsBulkActions({ acceptCount: 2, rejectCount: 2 }, { onAccept: vi.fn(), onReject: vi.fn() });
    expect(actions.map((a) => a.key)).toEqual(['bulk-accept', 'bulk-reject']);
    expect(actions.find((a) => a.key === 'bulk-reject')?.destructive).toBe(true);
  });

  it('shows only Accept when every selected row is already rejected', () => {
    const actions = buildResultsBulkActions({ acceptCount: 2, rejectCount: 0 }, { onAccept: vi.fn(), onReject: vi.fn() });
    expect(actions.map((a) => a.key)).toEqual(['bulk-accept']);
  });

  it('shows only Reject when every selected row is already accepted', () => {
    const actions = buildResultsBulkActions({ acceptCount: 0, rejectCount: 3 }, { onAccept: vi.fn(), onReject: vi.fn() });
    expect(actions.map((a) => a.key)).toEqual(['bulk-reject']);
  });

  it('wires each item to its handler', () => {
    const onAccept = vi.fn();
    const onReject = vi.fn();
    const actions = buildResultsBulkActions({ acceptCount: 1, rejectCount: 1 }, { onAccept, onReject });
    actions.find((a) => a.key === 'bulk-accept')?.onClick?.();
    actions.find((a) => a.key === 'bulk-reject')?.onClick?.();
    expect(onAccept).toHaveBeenCalledTimes(1);
    expect(onReject).toHaveBeenCalledTimes(1);
  });
});
