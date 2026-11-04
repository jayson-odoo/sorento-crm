/** PRICETAG-COMBO-RENDER fix round 1 (S2): a single pick over a multi-pick row replaces it. */
import { act, renderHook } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { draftLinesPayload, emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import { usePriceTagLineEditor } from './usePriceTagLineEditor';

const candidates = ['A', 'B', 'C'].map((c) => ({ product_id: `id-${c}`, code: c, name: c }));

function line(): DraftLine {
  return {
    ...emptyDraftLine(),
    key: 'l1',
    parts: [
      { key: 'g1', product_id: null, code: '', name: '', role: 'Tap', candidates, product_ids: ['id-A', 'id-B'] },
    ],
  } as DraftLine;
}

describe('resolvePart over a multi-pick row', () => {
  it('drops the stale picks, so the payload sends only the new pick', () => {
    const lookups = {
      lookupTagItems: vi.fn(async () => []),
      lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
      lookupLinePricing: vi.fn(async () => []),
    };
    const hook = renderHook(() => {
      const [lines, setLines] = useState([line()]);
      return { lines, editor: usePriceTagLineEditor({ lines, setLines, priceMode: 'list', lookups }) };
    });
    act(() => hook.result.current.editor.resolvePart('l1', 'g1', 'id-C'));
    const [payload] = draftLinesPayload(hook.result.current.lines, 'list');
    expect(payload.parts).toEqual([{ product_id: 'id-C', role: 'Tap', candidates: [] }]);
  });
});

describe('reopening a saved line with several picks in one group', () => {
  it('restores the group candidates once the combos lookup answers, so the row is a multi-pick row', async () => {
    const { waitFor } = await import('@testing-library/react');
    const { lineToDraft } = await import('@/lib/dealer-kit/price-tag-draft-lines');
    const combo = {
      combo_id: 'c1',
      name: 'Combo',
      parts: ['A', 'B', 'C'].map((c) => ({ product_id: `id-${c}`, code: c, name: c, choice_group: 'Tap' })),
    };
    const lookups = {
      lookupTagItems: vi.fn(async () => []),
      lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [combo] })),
      lookupLinePricing: vi.fn(async () => []),
    };
    const draft = lineToDraft({
      id: 'l1', line_type: 'product', product_id: 'host', product_set_id: null, name: 'H', code: 'H', quantity: 1,
      combo_id: 'c1',
      parts: ['C', 'A'].map((c, i) => ({ id: `p${i}`, product_id: `id-${c}`, code: c, name: c, role: 'Tap', candidates: [] })),
    } as never);
    const hook = renderHook(() => {
      const [lines, setLines] = useState([draft]);
      return { lines, editor: usePriceTagLineEditor({ lines, setLines, priceMode: 'list', lookups }) };
    });
    await waitFor(() => expect(hook.result.current.lines[0].combos_loaded).toBe(true));
    const [row] = hook.result.current.lines[0].parts;
    expect(hook.result.current.lines[0].parts).toHaveLength(1);
    expect(row.candidates.map((c) => c.code)).toEqual(['A', 'B', 'C']);
    expect(row.product_ids).toEqual(['id-C', 'id-A']);
  });
});
