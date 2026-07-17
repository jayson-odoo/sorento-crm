/**
 * SCM M4 Slice B — buildPoBulkActions gating (AC-M4.6).
 * The PO Actions dropdown surfaces Confirm ONLY when the selection contains ≥1
 * draft, and returns [] (button hidden) when no draft is selected.
 */
import { describe, it, expect, vi } from 'vitest';
import { buildPoBulkActions } from './poBulkActions';

describe('buildPoBulkActions (AC-M4.6)', () => {
  it('returns [] when the selection has no drafts (Actions button hidden)', () => {
    expect(buildPoBulkActions({ draftCount: 0 }, { onConfirm: vi.fn() })).toEqual([]);
  });

  it('lists Confirm when ≥1 draft is selected', () => {
    const actions = buildPoBulkActions({ draftCount: 2 }, { onConfirm: vi.fn() });
    expect(actions.map((a) => a.key)).toEqual(['bulk-confirm']);
  });

  it('wires Confirm to its handler', () => {
    const onConfirm = vi.fn();
    buildPoBulkActions({ draftCount: 1 }, { onConfirm })[0].onClick?.();
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
