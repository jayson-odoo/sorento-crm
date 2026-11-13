/**
 * PRICETAG-ALA-CARTE (pricetag-ala-carte-acceptance-criteria.md, owner's final answers 13 Nov), the
 * line editor hook: a product line's package is its combo_id, null = ala carte. AC-3 (every new line
 * starts ala carte, single-combo auto-pick gone), AC-4 (choosePackage), AC-5 (saved lines keep their
 * package exactly), AC-6 (no duplicate guard for products, sets keep it), AC-7 (multi-add never skips
 * a product already on the request) and AC-8 (a zero-part combo is still a package).
 *
 * Written test-FIRST against the UAC; fake codes only.
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


const SET_PICK: SearchableSelectOption = { value: 'product_set:s-ala-1', label: 'S-ALA-1', code: 'S-ALA-1', name: 'S-ALA-1' };

/** A line as it arrives from the server: built by lineToDraft, combos not asked yet. */
function saved(id: string, productId: ProductId, comboId: string | null): DraftLine {
  const combo = PRODUCTS[productId].combos.find((c) => c.combo_id === comboId);
  const draft = lineToDraft({
    id,
    line_type: 'product',
    product_id: productId,
    product_set_id: null,
    name: PRODUCTS[productId].code,
    code: PRODUCTS[productId].code,
    quantity: 1,
    combo_id: comboId,
    parts: (combo?.parts ?? []).map((p, i) => ({
      id: `${id}-part-${i}`,
      product_id: p.product_id,
      code: p.code,
      name: p.name,
      role: null,
      candidates: [],
    })),
  } as never);
  return { ...emptyDraftLine(), ...draft } as DraftLine;
}

describe('AC-3 every newly added product line starts ala carte', () => {
  it('a hand pick of a product with exactly one combo stays ala carte after the lookup (no auto-pick)', async () => {
    const { result, lookups } = setup([blank('l1')]);
    act(() => result.current.editor.handleItemSelect('l1', pick('p-ala-1')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l1').combos_loaded).toBe(true));
    await settle();
    expect(lookups.lookupProductCombos).toHaveBeenCalledWith('p-ala-1');
    const l1 = lineOf(result.current.lines, 'l1');
    expect(l1.combos.map((c) => c.combo_id)).toEqual([C.combo_id]);
    expect(l1.combo_id).toBeNull();
    expect(l1.parts).toEqual([]);
  });

  it('a hand pick of a product with two combos starts ala carte', async () => {
    const { result } = setup([blank('l1')]);
    act(() => result.current.editor.handleItemSelect('l1', pick('p-ala-2')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l1').combos_loaded).toBe(true));
    await settle();
    expect(lineOf(result.current.lines, 'l1').combo_id).toBeNull();
    expect(lineOf(result.current.lines, 'l1').parts).toEqual([]);
  });

  it('a product whose only combo has zero parts also starts ala carte', async () => {
    const { result } = setup([blank('l1')]);
    act(() => result.current.editor.handleItemSelect('l1', pick('p-ala-3')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l1').combos_loaded).toBe(true));
    await settle();
    expect(lineOf(result.current.lines, 'l1').combo_id).toBeNull();
  });

  it('multi-add: each added line of a one-combo product starts ala carte', async () => {
    const { result } = setup([blank('l1')]);
    act(() => addPickedItems(result.current.editor, result.current.lines, 'l1', [pick('p-ala-1'), pick('p-ala-3')]));
    await waitFor(() => expect(result.current.lines.every((l) => l.combos_loaded)).toBe(true));
    await settle();
    expect(result.current.lines.map((l) => l.product_id)).toEqual(['p-ala-1', 'p-ala-3']);
    expect(result.current.lines.map((l) => l.combo_id)).toEqual([null, null]);
    expect(result.current.lines.map((l) => l.parts.length)).toEqual([0, 0]);
  });
});

describe('AC-4 choosePackage', () => {
  it('choosing a combo sets it and its parts; clearing sets combo_id null and parts []', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-1', null)]);
    act(() => result.current.editor.choosePackage('l1', C.combo_id));
    expect(lineOf(result.current.lines, 'l1').combo_id).toBe(C.combo_id);
    expect(lineOf(result.current.lines, 'l1').parts.map((p) => p.product_id)).toEqual(['p-ala-part']);
    act(() => result.current.editor.choosePackage('l1', ''));
    expect(lineOf(result.current.lines, 'l1').combo_id).toBeNull();
    expect(lineOf(result.current.lines, 'l1').parts).toEqual([]);
  });
});

describe('AC-5 saved lines keep their package exactly', () => {
  it('a reopened ala carte line of a one-combo product stays ala carte after the lookup', async () => {
    const { result, lookups } = setup([saved('srv-1', 'p-ala-1', null)]);
    await waitFor(() => expect(lineOf(result.current.lines, 'srv-1').combos_loaded).toBe(true));
    await settle();
    expect(lookups.lookupProductCombos).toHaveBeenCalledWith('p-ala-1');
    expect(lineOf(result.current.lines, 'srv-1').combo_id).toBeNull();
    expect(lineOf(result.current.lines, 'srv-1').parts).toEqual([]);
  });

  it('a reopened line on C keeps C and its saved parts after the lookup', async () => {
    const { result } = setup([saved('srv-1', 'p-ala-1', C.combo_id)]);
    await waitFor(() => expect(lineOf(result.current.lines, 'srv-1').combos_loaded).toBe(true));
    await settle();
    expect(lineOf(result.current.lines, 'srv-1').combo_id).toBe(C.combo_id);
    expect(lineOf(result.current.lines, 'srv-1').parts.map((p) => p.product_id)).toEqual(['p-ala-part']);
  });

  it('a reopened pair of the same product (C and ala carte) keeps both packages, no guard_error', async () => {
    const { result } = setup([saved('srv-1', 'p-ala-1', C.combo_id), saved('srv-2', 'p-ala-1', null)]);
    await waitFor(() => expect(result.current.lines.every((l) => l.combos_loaded)).toBe(true));
    await settle();
    expect(result.current.lines.map((l) => l.combo_id)).toEqual([C.combo_id, null]);
    expect(result.current.lines.map((l) => l.guard_error)).toEqual([null, null]);
  });
});

describe('AC-6 no duplicate guard for products', () => {
  it('picking a product already on the request (on C) adds it, ala carte, with no error', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-1', C.combo_id), blank('l2')]);
    act(() => result.current.editor.handleItemSelect('l2', pick('p-ala-1')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').product_id).toBe('p-ala-1'));
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').combos_loaded).toBe(true));
    await settle();
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
    expect(lineOf(result.current.lines, 'l2').combo_id).toBeNull();
    expect(lineOf(result.current.lines, 'l1').combo_id).toBe(C.combo_id);
  });

  it('ala carte twice is allowed: a product with no combo picked onto a second line has no error', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-4', null), blank('l2')]);
    act(() => result.current.editor.handleItemSelect('l2', pick('p-ala-4')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l2').product_id).toBe('p-ala-4'));
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
  });

  it('a third line of the same product is added too', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-1', C.combo_id), onRequest('l2', 'p-ala-1', null), blank('l3')]);
    act(() => result.current.editor.handleItemSelect('l3', pick('p-ala-1')));
    await waitFor(() => expect(lineOf(result.current.lines, 'l3').product_id).toBe('p-ala-1'));
    expect(lineOf(result.current.lines, 'l3').guard_error).toBeNull();
    expect(result.current.lines.filter((l) => l.product_id === 'p-ala-1')).toHaveLength(3);
  });

  it('moving a line onto the package another line of the product holds raises no guard_error', () => {
    const { result } = setup([onRequest('l1', 'p-ala-2', A.combo_id), onRequest('l2', 'p-ala-2', B.combo_id)]);
    act(() => result.current.editor.choosePackage('l2', A.combo_id));
    expect(lineOf(result.current.lines, 'l2').combo_id).toBe(A.combo_id);
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
  });

  it('sets keep the guard: a set already on the request is refused with "<code> is already on this request."', () => {
    const setLine = { ...emptyDraftLine(), key: 'l1', line_type: 'product_set', product_set_id: 's-ala-1', code: 'S-ALA-1', combos_loaded: true } as DraftLine;
    const { result } = setup([setLine, blank('l2')]);
    act(() => result.current.editor.handleItemSelect('l2', SET_PICK));
    expect(lineOf(result.current.lines, 'l2').guard_error).toBe(DUP('S-ALA-1'));
    expect(lineOf(result.current.lines, 'l2').product_set_id).toBeNull();
  });
});

describe('AC-7 multi-add never skips a product already on the request', () => {
  it('Add on a blank row of a product already on the request gives it its own ala carte line', async () => {
    const { result } = setup([onRequest('l1', 'p-ala-1', C.combo_id), blank('l2')]);
    act(() => addPickedItems(result.current.editor, result.current.lines, 'l2', [pick('p-ala-1')]));
    await waitFor(() => expect(result.current.lines.filter((l) => l.product_id === 'p-ala-1')).toHaveLength(2));
    await settle();
    expect(lineOf(result.current.lines, 'l2').combo_id).toBeNull();
    expect(lineOf(result.current.lines, 'l2').guard_error).toBeNull();
  });

  it('addPickedItems hands a product already on another line to handleItemSelect instead of dropping it', () => {
    const addLine = vi.fn((k?: string) => 'n' + k);
    const handleItemSelect = vi.fn();
    const lines = [onRequest('l1', 'p-ala-4', null), blank('l2')];
    addPickedItems({ addLine, handleItemSelect } as unknown as PickEditor, lines, 'l2', [pick('p-ala-4'), pick('p-ala-1')]);
    expect(handleItemSelect.mock.calls.map(([k, o]) => [k, (o as SearchableSelectOption).value])).toEqual([
      ['l2', 'product:p-ala-4'],
      ['nl2', 'product:p-ala-1'],
    ]);
  });

  it('a set already on another line is still skipped (sets unchanged)', () => {
    const addLine = vi.fn((k?: string) => 'n' + k);
    const handleItemSelect = vi.fn();
    const setLine = { ...emptyDraftLine(), key: 'l1', line_type: 'product_set', product_set_id: 's-ala-1', code: 'S-ALA-1' } as DraftLine;
    addPickedItems({ addLine, handleItemSelect } as unknown as PickEditor, [setLine, blank('l2')], 'l2', [SET_PICK]);
    expect(handleItemSelect).not.toHaveBeenCalled();
  });
});

describe('AC-8 a combo with zero parts is still a package', () => {
  it('choosing Z (no parts) sets combo_id Z, parts []', () => {
    const { result } = setup([onRequest('l1', 'p-ala-3', null)]);
    act(() => result.current.editor.choosePackage('l1', Z.combo_id));
    expect(lineOf(result.current.lines, 'l1').combo_id).toBe(Z.combo_id);
    expect(lineOf(result.current.lines, 'l1').parts).toEqual([]);
  });

  it('a saved line on Z with no parts keeps Z after the lookup', async () => {
    const { result } = setup([saved('srv-1', 'p-ala-3', Z.combo_id)]);
    await waitFor(() => expect(lineOf(result.current.lines, 'srv-1').combos_loaded).toBe(true));
    await settle();
    expect(lineOf(result.current.lines, 'srv-1').combo_id).toBe(Z.combo_id);
  });
});
