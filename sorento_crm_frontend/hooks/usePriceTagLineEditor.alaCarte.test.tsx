/**
 * PRICETAG-ALA-CARTE (pricetag-ala-carte-acceptance-criteria.md), the line editor hook: a product
 * line's package is its combo_id, null = ala carte. AC-3 (hand pick defaults), AC-4 (clearing the
 * Package), AC-5 (no auto-pick on a line that was not just picked by hand), AC-6 (the duplicate guard
 * keys on product + package), AC-7 (a re-picked product takes the next unused package), AC-8
 * (multi-add per item) and AC-9 (a zero-part combo is still a package).
 *
 * Written test-FIRST against the UAC; fake codes and prices only.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type { ProductComboOption, ProductCombosLookup } from '@/app/(auth)/portal/lib/price-tag-request-service';
import {
  emptyDraftLine,
  lineToDraft,
  partsFromCombo,
  type DraftLine,
} from '@/lib/dealer-kit/price-tag-draft-lines';
import { addPickedItems, usePriceTagLineEditor } from './usePriceTagLineEditor';

type PickEditor = Parameters<typeof addPickedItems>[0];

const part = (id: string, code: string) => ({
  product_id: id,
  code,
  name: code,
  choice_group: null,
  is_upgrade: false,
  topup_amount: null,
  is_discontinued: false,
});

// P1: exactly one combo (C). P2: two combos (A, B). P3: one combo with zero parts (Z). P4: none.
const C: ProductComboOption = { combo_id: 'c-ala-1', name: 'P-ALA-1 + P-ALA-PART', parts: [part('p-ala-part', 'P-ALA-PART')] };
const A: ProductComboOption = { combo_id: 'c-ala-2a', name: 'Package A', parts: [part('p-ala-part', 'P-ALA-PART')] };
const B: ProductComboOption = { combo_id: 'c-ala-2b', name: 'Package B', parts: [part('p-ala-part2', 'P-ALA-PART2')] };
const Z: ProductComboOption = { combo_id: 'c-ala-3z', name: 'Package Z', parts: [] };

const PRODUCTS = {
  'p-ala-1': { code: 'P-ALA-1', combos: [C] },
  'p-ala-2': { code: 'P-ALA-2', combos: [A, B] },
  'p-ala-3': { code: 'P-ALA-3', combos: [Z] },
  'p-ala-4': { code: 'P-ALA-4', combos: [] as ProductComboOption[] },
} as const;
type ProductId = keyof typeof PRODUCTS;

function makeLookups() {
  return {
    lookupTagItems: vi.fn(async () => []),
    lookupProductCombos: vi.fn(
      async (id: string): Promise<ProductCombosLookup> => ({
        host_guarded: false,
        combos: [...(PRODUCTS[id as ProductId]?.combos ?? [])],
      }),
    ),
    lookupLinePricing: vi.fn(async () => []),
  };
}

function setup(initial: DraftLine[]) {
  const lookups = makeLookups();
  const hook = renderHook(() => {
    const [lines, setLines] = useState<DraftLine[]>(initial);
    const editor = usePriceTagLineEditor({ lines, setLines, priceMode: 'selling', lookups });
    return { lines, editor };
  });
  return { ...hook, lookups };
}

const blank = (key: string): DraftLine => ({ ...emptyDraftLine(), key }) as DraftLine;

/** A product line already on the request with its combos lookup answered. */
function onRequest(key: string, productId: ProductId, comboId: string | null): DraftLine {
  const product = PRODUCTS[productId];
  const combo = product.combos.find((c) => c.combo_id === comboId);
  return {
    ...emptyDraftLine(),
    key,
    line_type: 'product',
    product_id: productId,
    code: product.code,
    name: product.code,
    combo_id: comboId,
    combos: [...product.combos],
    combos_loaded: true,
    parts: combo ? partsFromCombo(combo) : [],
  } as DraftLine;
}

const pick = (productId: ProductId): SearchableSelectOption => ({
  value: `product:${productId}`,
  label: PRODUCTS[productId].code,
  code: PRODUCTS[productId].code,
  name: PRODUCTS[productId].code,
});

const lineOf = (lines: DraftLine[], key: string) => lines.find((l) => l.key === key) as DraftLine;

/** Lets every pending lookup answer and its state update land. */
const settle = () =>
  act(async () => {
    await new Promise((r) => setTimeout(r, 30));
  });

const DUP = (code: string) => `${code} is already on this request.`;

describe('AC-3 hand pick defaults (unchanged)', () => {
  it('a product with exactly one combo starts on that combo with its parts', async () => {
    const { result } = setup([blank('l1')]);
    act(() => result.current.editor.handleItemSelect('l1', pick('p-ala-1')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l1').combos_loaded).toBe(true));
    await settle();
    const l1 = lineOf(result.current.lines, 'l1');
    expect(l1.combo_id).toBe(C.combo_id);
    expect(l1.parts.map((p) => p.product_id)).toEqual(['p-ala-part']);
  });

  it('a product with two combos starts ala carte (combo_id null, no parts)', async () => {
    const { result } = setup([blank('l1')]);
    act(() => result.current.editor.handleItemSelect('l1', pick('p-ala-2')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l1').combos_loaded).toBe(true));
    await settle();
    expect(lineOf(result.current.lines, 'l1').combo_id).toBeNull();
    expect(lineOf(result.current.lines, 'l1').parts).toEqual([]);
  });
});

describe('AC-4 clearing the Package', () => {
  it('clearing sets combo_id null and parts []; choosing a combo puts it and its parts back', () => {
    const { result } = setup([onRequest('l1', 'p-ala-1', C.combo_id)]);
    act(() => result.current.editor.choosePackage('l1', ''));
    expect(lineOf(result.current.lines, 'l1').combo_id).toBeNull();
    expect(lineOf(result.current.lines, 'l1').parts).toEqual([]);
    act(() => result.current.editor.choosePackage('l1', C.combo_id));
    expect(lineOf(result.current.lines, 'l1').combo_id).toBe(C.combo_id);
    expect(lineOf(result.current.lines, 'l1').parts.map((p) => p.product_id)).toEqual(['p-ala-part']);
  });
});

describe('AC-5 no auto-pick on a line that was not just picked by hand', () => {
  it('a reopened line of a one-combo product saved ala carte stays ala carte after the lookup', async () => {
    const reopened = {
      ...emptyDraftLine(),
      key: 'l1',
      line_type: 'product',
      product_id: 'p-ala-1',
      code: 'P-ALA-1',
      name: 'P-ALA-1',
      combo_id: null,
      combos_loaded: false,
    } as DraftLine;
    const { result, lookups } = setup([reopened]);
    await waitFor(() => expect(lineOf(result.current.lines, 'l1').combos_loaded).toBe(true));
    await settle();
    expect(lookups.lookupProductCombos).toHaveBeenCalledWith('p-ala-1');
    expect(lineOf(result.current.lines, 'l1').combos).toHaveLength(1);
    expect(lineOf(result.current.lines, 'l1').combo_id).toBeNull();
    expect(lineOf(result.current.lines, 'l1').parts).toEqual([]);
  });

  it('a line built by lineToDraft (duplicate / revise) with combo_id null stays null after the lookup', async () => {
    const draft = lineToDraft({
      id: 'l1',
      line_type: 'product',
      product_id: 'p-ala-1',
      product_set_id: null,
      name: 'P-ALA-1',
      code: 'P-ALA-1',
      quantity: 1,
      combo_id: null,
      parts: [],
    } as never);
    const { result } = setup([{ ...emptyDraftLine(), ...draft } as DraftLine]);
    await waitFor(() => expect(lineOf(result.current.lines, 'l1').combos_loaded).toBe(true));
    await settle();
    expect(lineOf(result.current.lines, 'l1').combo_id).toBeNull();
    expect(lineOf(result.current.lines, 'l1').parts).toEqual([]);
  });
});

describe('AC-6 the duplicate guard keys on product + package', () => {
  it('same product, one on C and one ala carte: no guard_error', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-1', C.combo_id), onRequest('l2', 'p-ala-1', null)]);
    await settle();
    expect(lineOf(result.current.lines, 'l1').guard_error).toBeNull();
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
  });

  it('changing the later line to the package the earlier one holds flags it; clearing it again removes the flag', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-1', C.combo_id), onRequest('l2', 'p-ala-1', null)]);
    act(() => result.current.editor.choosePackage('l2', C.combo_id));
    expect(lineOf(result.current.lines, 'l2').guard_error).toBe(DUP('P-ALA-1'));
    expect(lineOf(result.current.lines, 'l1').guard_error).toBeNull();

    act(() => result.current.editor.choosePackage('l2', ''));
    expect(lineOf(result.current.lines, 'l2').combo_id).toBeNull();
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
  });

  it('two combos: lines on A and B are fine; moving the B line to A flags it, back to B clears it', () => {
    const { result } = setup([onRequest('l1', 'p-ala-2', A.combo_id), onRequest('l2', 'p-ala-2', B.combo_id)]);
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
    act(() => result.current.editor.choosePackage('l2', A.combo_id));
    expect(lineOf(result.current.lines, 'l2').guard_error).toBe(DUP('P-ALA-2'));
    act(() => result.current.editor.choosePackage('l2', B.combo_id));
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
  });
});

describe('AC-7 a product already on the request takes the next unused package', () => {
  it('one combo, existing line on C: the new pick goes ala carte with no error, and the lookup does not put C on it', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-1', C.combo_id), blank('l2')]);
    act(() => result.current.editor.handleItemSelect('l2', pick('p-ala-1')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').product_id).toBe('p-ala-1'));
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').combos_loaded).toBe(true));
    await settle();
    const l2 = lineOf(result.current.lines, 'l2');
    expect(l2.combo_id).toBeNull();
    expect(l2.parts).toEqual([]);
    expect(l2.guard_error).toBeNull();
    expect(lineOf(result.current.lines, 'l1').combo_id).toBe(C.combo_id);
  });

  it('one combo, existing line ala carte: the new pick starts on C (the default)', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-1', null), blank('l2')]);
    act(() => result.current.editor.handleItemSelect('l2', pick('p-ala-1')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').product_id).toBe('p-ala-1'));
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').combo_id).toBe(C.combo_id));
    expect(lineOf(result.current.lines, 'l2').parts.map((p) => p.product_id)).toEqual(['p-ala-part']);
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
  });

  it('one combo, C and ala carte both used: the third pick is refused with "<code> is already on this request."', async () => {
    const { result } = setup([
      onRequest('l1', 'p-ala-1', C.combo_id),
      onRequest('l2', 'p-ala-1', null),
      blank('l3'),
    ]);
    act(() => result.current.editor.handleItemSelect('l3', pick('p-ala-1')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l3').guard_error).toBe(DUP('P-ALA-1')));
    await settle();
    const pairs = result.current.lines
      .filter((l) => l.product_id === 'p-ala-1')
      .map((l) => l.combo_id ?? 'ala-carte');
    expect(new Set(pairs).size).toBe(pairs.length);
  });

  it('two combos (A, B), existing line ala carte: the new pick starts on A with its parts', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-2', null), blank('l2')]);
    act(() => result.current.editor.handleItemSelect('l2', pick('p-ala-2')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').product_id).toBe('p-ala-2'));
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').combo_id).toBe(A.combo_id));
    expect(lineOf(result.current.lines, 'l2').parts.map((p) => p.product_id)).toEqual(['p-ala-part']);
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
  });

  it('two combos, ala carte and A used: the next pick takes B', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-2', null), onRequest('l2', 'p-ala-2', A.combo_id), blank('l3')]);
    act(() => result.current.editor.handleItemSelect('l3', pick('p-ala-2')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l3').combo_id).toBe(B.combo_id));
    expect(lineOf(result.current.lines, 'l3').guard_error).toBeNull();
  });

  it('a product with no combo already on the request is still refused (its only package is used)', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-4', null), blank('l2')]);
    act(() => result.current.editor.handleItemSelect('l2', pick('p-ala-4')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').guard_error).toBe(DUP('P-ALA-4')));
    expect(result.current.lines.filter((l) => l.product_id === 'p-ala-4')).toHaveLength(1);
  });
});

describe('AC-8 multi-add goes through the same per-item pick', () => {
  it('a product on the request with an unused package is not skipped: Add on a blank row gives it an ala carte line', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-1', C.combo_id), blank('l2')]);
    act(() => addPickedItems(result.current.editor, result.current.lines, 'l2', [pick('p-ala-1')]));
    await waitFor(() => expect(result.current.lines.filter((l) => l.product_id === 'p-ala-1')).toHaveLength(2));
    await settle();
    expect(lineOf(result.current.lines, 'l2').combo_id).toBeNull();
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
  });

  it('addPickedItems hands an option with an unused package to handleItemSelect instead of dropping it', () => {
    const addLine = vi.fn((k?: string) => 'n' + k);
    const handleItemSelect = vi.fn();
    const lines = [onRequest('l1', 'p-ala-1', C.combo_id), blank('l2')];
    addPickedItems({ addLine, handleItemSelect } as unknown as PickEditor, lines, 'l2', [pick('p-ala-1')]);
    expect(handleItemSelect).toHaveBeenCalledWith('l2', expect.objectContaining({ value: 'product:p-ala-1' }));
  });
});

describe('AC-9 a combo with zero parts is still a package', () => {
  it('a hand pick of a product whose only combo has no parts sets combo_id', async () => {
    const { result } = setup([blank('l1')]);
    act(() => result.current.editor.handleItemSelect('l1', pick('p-ala-3')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l1').combos_loaded).toBe(true));
    await settle();
    expect(lineOf(result.current.lines, 'l1').combo_id).toBe(Z.combo_id);
    expect(lineOf(result.current.lines, 'l1').parts).toEqual([]);
  });

  it('a line on Z (no parts) and an ala carte line of the same product are distinct: no guard_error', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-3', Z.combo_id), onRequest('l2', 'p-ala-3', null)]);
    await settle();
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
    act(() => result.current.editor.choosePackage('l2', Z.combo_id));
    expect(lineOf(result.current.lines, 'l2').guard_error).toBe(DUP('P-ALA-3'));
    act(() => result.current.editor.choosePackage('l2', ''));
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
  });

  it('with an ala carte line on the request, a new pick takes Z (set, though empty)', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-3', null), blank('l2')]);
    act(() => result.current.editor.handleItemSelect('l2', pick('p-ala-3')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').product_id).toBe('p-ala-3'));
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').combo_id).toBe(Z.combo_id));
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
  });
});
