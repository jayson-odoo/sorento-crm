/**
 * PRICETAG-LPSP fix round 2: the Item and part picker options, and what a pick writes to the line.
 *
 * Bug 17 (owner, 4 Nov): each option is ONE line with the code shown once, "CODE  RM <list
 * price>", and the name as the second line only when it adds something other than the code; a
 * set keeps its D47 marker as "Set" in front of that line, a product gets no "Product" word.
 * Bug 14: the line's code comes from the option's own `code`, never parsed out of a label, so an
 * item whose name equals its code still carries the code (the eye preview header reads it).
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import type { TagItemOption } from '@/app/(auth)/portal/lib/price-tag-request-service';
import { usePriceTagLineEditor } from './usePriceTagLineEditor';

const ITEMS: TagItemOption[] = [
  { kind: 'product', id: 'p-1', code: 'SRTWT7634-BL', name: 'ZZT Basin Mixer', list_price: 1050 },
  { kind: 'product', id: 'p-2', code: 'SRTSH2626-GY', name: 'SRTSH2626-GY', list_price: null },
  { kind: 'product', id: 'p-3', code: 'SRTZERO-1', name: 'SRTZERO-1', list_price: 0 },
  { kind: 'product_set', id: 's-1', code: 'SET-ONE', name: 'ZZT Vanity Set', list_price: 2400 },
  { kind: 'product_set', id: 's-2', code: 'SET-TWO', name: 'SET-TWO', list_price: null },
];

function setup() {
  const lookups = {
    lookupTagItems: vi.fn(async () => ITEMS),
    lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
    lookupLinePricing: vi.fn(async () => []),
  };
  return renderHook(() => {
    const [lines, setLines] = useState<DraftLine[]>([{ ...emptyDraftLine(), key: 'l1' }]);
    const editor = usePriceTagLineEditor({ lines, setLines, priceMode: 'selling', lookups });
    return { lines, editor };
  });
}

describe('usePriceTagLineEditor Item options (bug 17)', () => {
  it('labels each option "CODE  RM <list price>", the price only when known and above 0', async () => {
    const { result } = setup();
    const options = await result.current.editor.fetchItemOptions('');
    expect(options.map((o) => o.label)).toEqual([
      'SRTWT7634-BL  RM 1,050',
      'SRTSH2626-GY',
      'SRTZERO-1',
      'SET-ONE  RM 2,400',
      'SET-TWO',
    ]);
  });

  it('shows the name only when it adds something, and never the word Product', async () => {
    const { result } = setup();
    const options = await result.current.editor.fetchItemOptions('');
    expect(options.map((o) => o.description)).toEqual([
      'ZZT Basin Mixer',
      undefined,
      undefined,
      'Set - ZZT Vanity Set',
      'Set',
    ]);
  });

  it('carries the code on the option itself', async () => {
    const { result } = setup();
    const options = await result.current.editor.fetchItemOptions('');
    expect(options.map((o) => o.code)).toEqual([
      'SRTWT7634-BL',
      'SRTSH2626-GY',
      'SRTZERO-1',
      'SET-ONE',
      'SET-TWO',
    ]);
  });

  it('the part picker lists products only, with the same option shape', async () => {
    const { result } = setup();
    const options = await result.current.editor.fetchPartOptions('');
    expect(options.map((o) => [o.label, o.description, o.code])).toEqual([
      ['SRTWT7634-BL  RM 1,050', 'ZZT Basin Mixer', 'SRTWT7634-BL'],
      ['SRTSH2626-GY', undefined, 'SRTSH2626-GY'],
      ['SRTZERO-1', undefined, 'SRTZERO-1'],
    ]);
  });
});

describe('usePriceTagLineEditor item pick (bug 14)', () => {
  it('an item whose name equals its code puts that code on the line', async () => {
    const { result } = setup();
    const options = await result.current.editor.fetchItemOptions('');
    const same = options.find((o) => o.value === 'product:p-2')!;
    act(() => result.current.editor.handleItemSelect('l1', same));
    expect(result.current.lines[0].code).toBe('SRTSH2626-GY');
    expect(result.current.lines[0].name).toBe('SRTSH2626-GY');
  });

  it('an item with a distinct name keeps its code and its name, not the option label', async () => {
    const { result } = setup();
    const options = await result.current.editor.fetchItemOptions('');
    const named = options.find((o) => o.value === 'product:p-1')!;
    act(() => result.current.editor.handleItemSelect('l1', named));
    expect(result.current.lines[0].code).toBe('SRTWT7634-BL');
    expect(result.current.lines[0].name).toBe('ZZT Basin Mixer');
  });

  it('a set whose name equals its code puts that code on the line', async () => {
    const { result } = setup();
    const options = await result.current.editor.fetchItemOptions('');
    const set = options.find((o) => o.value === 'product_set:s-2')!;
    act(() => result.current.editor.handleItemSelect('l1', set));
    expect(result.current.lines[0].code).toBe('SET-TWO');
  });

  it('a part added by hand whose name equals its code carries that code', async () => {
    const { result } = setup();
    const items = await result.current.editor.fetchItemOptions('');
    act(() => result.current.editor.handleItemSelect('l1', items[0]));
    const parts = await result.current.editor.fetchPartOptions('');
    act(() => result.current.editor.addPart('l1', parts.find((o) => o.value === 'product:p-2')!));
    await waitFor(() => expect(result.current.lines[0].parts).toHaveLength(1));
    expect(result.current.lines[0].parts[0].code).toBe('SRTSH2626-GY');
    expect(result.current.lines[0].parts[0].name).toBe('SRTSH2626-GY');
  });
});
