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
