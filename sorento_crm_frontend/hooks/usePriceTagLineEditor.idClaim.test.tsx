/**
 * PRICETAG-ALA-CARTE review finding (blocking): a saved line's `id` claims that line's tags on the
 * server, so it must only travel while the line still holds the SAME product. Changing the Item to
 * another product turns the row into a new line (no `id` in the payload); clearing the Item drops
 * `saved_id`; choosing another Package keeps the id (same product, AC-12).
 *
 * Written test-FIRST; fake codes only.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type { ProductComboOption, ProductCombosLookup } from '@/app/(auth)/portal/lib/price-tag-request-service';
import { draftLinesPayload, emptyDraftLine, lineToDraft, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import { usePriceTagLineEditor } from './usePriceTagLineEditor';

const A: ProductComboOption = { combo_id: 'c-idc-a', name: 'Package A', parts: [] };
const B: ProductComboOption = { combo_id: 'c-idc-b', name: 'Package B', parts: [] };

const COMBOS: Record<string, ProductComboOption[]> = { 'p-idc-1': [A, B], 'p-idc-2': [] };

function setup(initial: DraftLine[]) {
  const lookups = {
    lookupTagItems: vi.fn(async () => []),
    lookupProductCombos: vi.fn(
      async (id: string): Promise<ProductCombosLookup> => ({ host_guarded: false, combos: [...(COMBOS[id] ?? [])] }),
    ),
    lookupLinePricing: vi.fn(async () => []),
  };
  return renderHook(() => {
    const [lines, setLines] = useState<DraftLine[]>(initial);
    const editor = usePriceTagLineEditor({ lines, setLines, priceMode: 'list', lookups });
    return { lines, editor };
  });
}

/** A line as it arrives from the server (lineToDraft sets saved_id). */
function saved(id: string, productId: string, comboId: string | null): DraftLine {
  const draft = lineToDraft({
    id,
    line_type: 'product',
    product_id: productId,
    product_set_id: null,
    name: productId.toUpperCase(),
    code: productId.toUpperCase(),
    quantity: 1,
    combo_id: comboId,
    parts: [],
  } as never);
  return { ...emptyDraftLine(), ...draft } as DraftLine;
}

const pick = (productId: string): SearchableSelectOption => ({
  value: `product:${productId}`,
  label: productId.toUpperCase(),
  code: productId.toUpperCase(),
  name: productId.toUpperCase(),
});

const lineOf = (lines: DraftLine[], key: string) => lines.find((l) => l.key === key) as DraftLine;
const payloadOf = (lines: DraftLine[], key: string) =>
  draftLinesPayload([lineOf(lines, key)], 'list')[0] as Record<string, unknown>;

describe('a saved line id travels only with its own product', () => {
  it('guard: a loaded line sends its saved id', () => {
    const { result } = setup([saved('srv-1', 'p-idc-1', null)]);
    expect(payloadOf(result.current.lines, 'srv-1').id).toBe('srv-1');
  });

  it('changing the Item to another product sends no id', async () => {
    const { result } = setup([saved('srv-1', 'p-idc-1', null)]);
    act(() => result.current.editor.handleItemSelect('srv-1', pick('p-idc-2')));
    await waitFor(() => expect(lineOf(result.current.lines, 'srv-1').product_id).toBe('p-idc-2'));
    expect(lineOf(result.current.lines, 'srv-1').saved_id ?? null).toBeNull();
    expect(payloadOf(result.current.lines, 'srv-1')).not.toHaveProperty('id');
  });

  it('clearing the Item drops saved_id', () => {
    const { result } = setup([saved('srv-1', 'p-idc-1', null)]);
    act(() => result.current.editor.handleItemSelect('srv-1', null));
    expect(lineOf(result.current.lines, 'srv-1').product_id).toBeNull();
    expect(lineOf(result.current.lines, 'srv-1').saved_id ?? null).toBeNull();
    expect(payloadOf(result.current.lines, 'srv-1')).not.toHaveProperty('id');
  });

  it('choosing another Package on a saved line keeps its id (same product)', async () => {
    const { result } = setup([saved('srv-1', 'p-idc-1', A.combo_id)]);
    await waitFor(() => expect(lineOf(result.current.lines, 'srv-1').combos_loaded).toBe(true));
    act(() => result.current.editor.choosePackage('srv-1', B.combo_id));
    expect(lineOf(result.current.lines, 'srv-1').combo_id).toBe(B.combo_id);
    expect(payloadOf(result.current.lines, 'srv-1').id).toBe('srv-1');
  });
});
