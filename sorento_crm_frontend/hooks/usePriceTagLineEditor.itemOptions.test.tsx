/**
 * PRICETAG-LPSP fix round 2: the Item and part picker options, and what a pick writes to the line.
 *
 * Bug 17 (owner, 4 Nov): each option is ONE line with the code shown once, "CODE  RM <list
 * price>", and the name as the second line only when it adds something other than the code; a
 * set keeps its D47 marker as "Set" in front of that line, a product gets no "Product" word.
 * Bug 14: the line's code comes from the option's own `code`, never parsed out of a label, so an
 * item whose name equals its code still carries the code (the eye preview header reads it).
 */
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock('@/components/dealer-kit/DesignLightbox', () => ({
  __esModule: true,
  default: ({ title }: { title: string }) => <div data-testid="lightbox">{title}</div>,
}));
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { PriceTagLivePreview } from '@/components/dealer-kit/PriceTagLivePreview';

import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import type {
  TagItemOption,
  TagPreviewResponse,
} from '@/app/(auth)/portal/lib/price-tag-request-service';
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
  it('labels each Item option with the code only: no name, no price (AC-13)', async () => {
    const { result } = setup();
    const options = await result.current.editor.fetchItemOptions('');
    expect(options.map((o) => o.label)).toEqual([
      'SRTWT7634-BL',
      'SRTSH2626-GY',
      'SRTZERO-1',
      'SET-ONE',
      'SET-TWO',
    ]);
  });

  it('has no second line; a set carries a Set badge, a product none (AC-13)', async () => {
    const { result } = setup();
    const options = await result.current.editor.fetchItemOptions('');
    expect(options.map((o) => o.description)).toEqual([undefined, undefined, undefined, undefined, undefined]);
    expect(options.map((o) => o.badgeText)).toEqual([undefined, undefined, undefined, 'Set', 'Set']);
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
});

describe('the eye preview header after a pick (bug 14)', () => {
  it('reads "CODE - LP" for an item whose name equals its code, never "Preview"', async () => {
    const { result } = setup();
    const options = await result.current.editor.fetchItemOptions('');
    act(() =>
      result.current.editor.handleItemSelect('l1', options.find((o) => o.value === 'product:p-2')!),
    );
    const line = result.current.lines[0];
    const lookup = vi.fn(
      async () =>
        ({
          lines: [{ line_id: line.key, tag_id: line.key, code: 'SRTSH2626-GY', name: 'x', images: [] }],
          templates: {
            [line.key]: {
              id: 'tpl',
              name: 'A5',
              family: 'art_basin',
              doc: { layers: [], width_mm: 80, height_mm: 50 },
              print_size: { width_mm: 80, height_mm: 50 },
            },
          },
          assets: {},
          images: {},
          fonts: [],
        }) as unknown as TagPreviewResponse,
    );
    render(
      <PriceTagLivePreview
        lines={[line]}
        priceMode="list"
        lookupTagPreview={lookup}
        {...({ lineKey: line.key } as object)}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId('lightbox')).toHaveTextContent('SRTSH2626-GY - LP'),
    );
  });
});
