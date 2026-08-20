/**
 * SCM M4 Slice B - buildPoBulkActions gating (AC-M4.6), plus bulk delete
 * (captain, 20 Aug: "give me an option to bulk delete purchase orders").
 * The PO Actions dropdown surfaces Confirm ONLY when the selection contains
 * ≥1 draft, Delete whenever anything at all is selected (any status), and
 * returns [] (button hidden) when nothing is selected.
 */
import { describe, it, expect, vi } from 'vitest';
import { buildPoBulkActions } from './poBulkActions';

const handlers = () => ({ onConfirm: vi.fn(), onDelete: vi.fn() });

describe('buildPoBulkActions (AC-M4.6)', () => {
  it('returns [] when nothing is selected (Actions button hidden)', () => {
    expect(buildPoBulkActions({ draftCount: 0, selectedCount: 0 }, handlers())).toEqual([]);
  });

  it('lists Confirm when ≥1 draft is selected', () => {
    const actions = buildPoBulkActions({ draftCount: 2, selectedCount: 2 }, handlers());
    expect(actions.map((a) => a.key)).toContain('bulk-confirm');
  });

  it('wires Confirm to its handler', () => {
    const h = handlers();
    const actions = buildPoBulkActions({ draftCount: 1, selectedCount: 1 }, h);
    actions.find((a) => a.key === 'bulk-confirm')?.onClick?.();
    expect(h.onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe('buildPoBulkActions - bulk delete (20 Aug)', () => {
  it('lists Delete whenever anything is selected, regardless of status', () => {
    // No drafts at all - an all-active selection must still offer Delete.
    const actions = buildPoBulkActions({ draftCount: 0, selectedCount: 3 }, handlers());
    expect(actions.map((a) => a.key)).toEqual(['bulk-delete']);
  });

  it('lists both Confirm and Delete when the selection mixes drafts and non-drafts', () => {
    const actions = buildPoBulkActions({ draftCount: 1, selectedCount: 3 }, handlers());
    expect(actions.map((a) => a.key)).toEqual(['bulk-confirm', 'bulk-delete']);
  });

  it('marks Delete as destructive', () => {
    const actions = buildPoBulkActions({ draftCount: 0, selectedCount: 1 }, handlers());
    expect(actions.find((a) => a.key === 'bulk-delete')?.destructive).toBe(true);
  });

  it('wires Delete to its handler', () => {
    const h = handlers();
    const actions = buildPoBulkActions({ draftCount: 0, selectedCount: 2 }, h);
    actions.find((a) => a.key === 'bulk-delete')?.onClick?.();
    expect(h.onDelete).toHaveBeenCalledTimes(1);
  });
});
