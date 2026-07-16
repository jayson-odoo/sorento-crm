/**
 * SCM M4 Slice B — buildResultsBulkActions gating (AC-M4.9).
 * The unified Actions dropdown lists ONLY the applicable actions (Accept +
 * Reject) and returns [] (button hidden) when the selection has no pending rows.
 */
import { describe, it, expect, vi } from 'vitest';
import { buildResultsBulkActions } from './decisionBulkActions';

describe('buildResultsBulkActions (AC-M4.9)', () => {
  it('returns [] when no selected row is still pending (Actions button hidden)', () => {
    expect(buildResultsBulkActions({ pendingCount: 0 }, { onAccept: vi.fn(), onReject: vi.fn() })).toEqual([]);
  });

  it('lists Accept + Reject when ≥1 pending row is selected', () => {
    const actions = buildResultsBulkActions({ pendingCount: 2 }, { onAccept: vi.fn(), onReject: vi.fn() });
    expect(actions.map((a) => a.key)).toEqual(['bulk-accept', 'bulk-reject']);
    expect(actions.find((a) => a.key === 'bulk-reject')?.destructive).toBe(true);
  });

  it('wires each item to its handler', () => {
    const onAccept = vi.fn();
    const onReject = vi.fn();
    const actions = buildResultsBulkActions({ pendingCount: 1 }, { onAccept, onReject });
    actions.find((a) => a.key === 'bulk-accept')?.onClick?.();
    actions.find((a) => a.key === 'bulk-reject')?.onClick?.();
    expect(onAccept).toHaveBeenCalledTimes(1);
    expect(onReject).toHaveBeenCalledTimes(1);
  });
});
