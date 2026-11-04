/** PRICETAG-COMBO: the line pricing lookup is told which combo a line is asked for. */
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import { usePriceTagLineEditor } from './usePriceTagLineEditor';

describe('usePriceTagLineEditor line pricing', () => {
  it('sends the line combo_id', async () => {
    const lookupLinePricing = vi.fn(async () => []);
    const lookups = {
      lookupTagItems: vi.fn(async () => []),
      lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
      lookupLinePricing,
    };
    const lines: DraftLine[] = [
      { ...emptyDraftLine(), key: 'l1', product_id: 'host-1', code: 'ZZ1', combo_id: 'combo-1' },
    ];
    renderHook(() =>
      usePriceTagLineEditor({ lines, setLines: vi.fn(), priceMode: 'selling', lookups }),
    );
    await waitFor(() => expect(lookupLinePricing).toHaveBeenCalled());
    const [, sent] = lookupLinePricing.mock.calls[0] as unknown as [string, { combo_id: string | null }[]];
    expect(sent[0].combo_id).toBe('combo-1');
  });
});
