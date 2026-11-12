/**
 * PRICETAG-MULTI-ADD: AC-3 (Add N fills the origin row, inserts the rest below), AC-4 (no
 * duplicates), AC-9 (Discontinued hint), through the real table, editor hook and picker.
 * Written test-FIRST against the Contract in pricetag-multi-add-acceptance-criteria.md.
 */
import React, { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';

vi.mock('@/components/dealer-kit/DesignViewer', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/dealer-kit/DesignLightbox', () => ({ __esModule: true, default: () => null }));
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { PriceTagLinesTable } from './PriceTagLinesTable';
import { usePriceTagLineEditor } from '@/hooks/usePriceTagLineEditor';
import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import type { TagItemOption } from '@/app/(auth)/portal/lib/price-tag-request-service';

const ITEMS: TagItemOption[] = [
  { kind: 'product', id: 'p-x', code: 'DIY-BS-4501', name: 'Basin X', list_price: 100 },
  { kind: 'product', id: 'p-y', code: 'DIY-BS-4502', name: 'Basin Y', list_price: 120 },
  { kind: 'product_set', id: 's-z', code: 'DIY-SET-4503', name: 'Vanity Z', list_price: 900 },
  { kind: 'product', id: 'p-old', code: 'DIY-BS-4599', name: 'Old Basin', list_price: 50, is_discontinued: true },
  { kind: 'product', id: 'p-a', code: 'DIY-BS-4001', name: 'Basin A', list_price: 10 },
];

const lookups = () => ({
  lookupTagItems: vi.fn(async (q?: string) =>
    ITEMS.filter((i) => !q || i.code.toLowerCase().includes(q.toLowerCase())),
  ),
  lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
  lookupLinePricing: vi.fn(async () => []),
});

const row = (key: string, extra: Partial<DraftLine> = {}): DraftLine =>
  ({ ...emptyDraftLine(), key, ...extra }) as DraftLine;

const A = () =>
  row('A', { line_type: 'product', product_id: 'p-a', code: 'DIY-BS-4001', name: 'Basin A' });
const B = () => row('B');

const LOOKUPS = lookups();

function hookSetup(initial: DraftLine[]) {
  return renderHook(() => {
    const [lines, setLines] = useState<DraftLine[]>(initial);
    const editor = usePriceTagLineEditor({ lines, setLines, priceMode: 'selling', lookups: LOOKUPS });
    return { lines, editor };
  });
}

async function options(result: { current: { editor: { fetchItemOptions: (q: string) => Promise<any[]> } } }) {
  return result.current.editor.fetchItemOptions('');
}

describe('AC-3 handleItemsAdd', () => {
  it('rows [A, B]: adding X, Y, Z from A gives [X, Y, Z, B], no blank row, single-pick fields', async () => {
    const { result } = hookSetup([row('A'), row('B', { code: 'KEEP-B', product_id: 'p-b' })]);
    const opts = await options(result);
    const x = opts.find((o) => o.value === 'product:p-x')!;
    const y = opts.find((o) => o.value === 'product:p-y')!;
    const z = opts.find((o) => o.value === 'product_set:s-z')!;

    act(() => result.current.editor.handleItemsAdd('A', [x, y, z]));

    const lines = result.current.lines;
    expect(lines.map((l) => l.code)).toEqual(['DIY-BS-4501', 'DIY-BS-4502', 'DIY-SET-4503', 'KEEP-B']);
    expect(lines[0].key).toBe('A');
    expect(lines[3].key).toBe('B');
    expect(new Set(lines.map((l) => l.key)).size).toBe(4);
    expect(lines[0]).toMatchObject({ line_type: 'product', product_id: 'p-x', product_set_id: null, name: 'Basin X' });
    expect(lines[1]).toMatchObject({ line_type: 'product', product_id: 'p-y', product_set_id: null, name: 'Basin Y' });
    expect(lines[2]).toMatchObject({ line_type: 'product_set', product_id: null, product_set_id: 's-z', name: 'Vanity Z' });
    const blank = emptyDraftLine();
    for (const l of lines.slice(0, 3)) {
      expect(l.quantity).toEqual(blank.quantity);
      expect(l.combo_id).toBeNull();
      expect(l.parts).toEqual([]);
      expect(l.pricing).toBeNull();
    }
    expect(lines[2].combos_loaded).toBe(true);
    expect(lines[0].combos_loaded).toBe(false);
  });

  it('a new line matches what handleItemSelect gives a fresh row', async () => {
    const single = hookSetup([row('A')]);
    const opts = await options(single.result);
    const y = opts.find((o) => o.value === 'product:p-y')!;
    act(() => single.result.current.editor.handleItemSelect('A', y));

    const multi = hookSetup([row('A')]);
    const x = opts.find((o) => o.value === 'product:p-x')!;
    act(() => multi.result.current.editor.handleItemsAdd('A', [x, y]));

    const strip = ({ key: _k, ...rest }: DraftLine) => rest;
    expect(strip(multi.result.current.lines[1])).toEqual(strip(single.result.current.lines[0]));
  });
});

describe('combos memory across Add N', () => {
  it('re-asks the combos lookup for a product put back on a row that held it before', async () => {
    const { result } = hookSetup([row('A')]);
    const opts = await options(result);
    const p = opts.find((o) => o.value === 'product:p-x')!;
    const q = opts.find((o) => o.value === 'product:p-y')!;
    const r = opts.find((o) => o.value === 'product:p-a')!;
    LOOKUPS.lookupProductCombos.mockClear();

    act(() => result.current.editor.handleItemsAdd('A', [p]));
    await waitFor(() => expect(result.current.lines[0].combos_loaded).toBe(true));
    expect(LOOKUPS.lookupProductCombos).toHaveBeenCalledTimes(1);

    act(() => result.current.editor.handleItemsAdd('A', [q]));
    await waitFor(() => expect(result.current.lines[0].product_id).toBe('p-y'));
    await waitFor(() => expect(result.current.lines[0].combos_loaded).toBe(true));
    LOOKUPS.lookupProductCombos.mockClear();

    act(() => result.current.editor.handleItemsAdd('A', [p, r]));
    await waitFor(() => expect(result.current.lines[0].combos_loaded).toBe(true));
    expect(result.current.lines[0].product_id).toBe('p-x');
    expect(LOOKUPS.lookupProductCombos).toHaveBeenCalledWith('p-x');
  });
});

describe('AC-4 no duplicates', () => {
  it('skips an option already on another line, and the same item twice in one batch', async () => {
    const { result } = hookSetup([row('A'), { ...A(), key: 'B' }]);
    const opts = await options(result);
    const a = opts.find((o) => o.value === 'product:p-a')!;
    const x = opts.find((o) => o.value === 'product:p-x')!;

    act(() => result.current.editor.handleItemsAdd('A', [a, x, x]));

    const lines = result.current.lines;
    expect(lines.map((l) => l.code)).toEqual(['DIY-BS-4501', 'DIY-BS-4001']);
    expect(lines.filter((l) => l.product_id === 'p-x')).toHaveLength(1);
    expect(lines.filter((l) => l.product_id === 'p-a')).toHaveLength(1);
  });
});

describe('AC-9 Discontinued', () => {
  it('tagItemOption gives badgeText Discontinued for a discontinued product only', async () => {
    const { result } = hookSetup([row('A')]);
    const opts = await options(result);
    expect(opts.find((o) => o.value === 'product:p-old')!.badgeText).toBe('Discontinued');
    expect(opts.find((o) => o.value === 'product:p-x')!.badgeText).toBeUndefined();
    expect(opts.find((o) => o.value === 'product_set:s-z')!.badgeText).toBeUndefined();
  });
});

function Harness({ initial }: { initial: DraftLine[] }) {
  const [lines, setLines] = useState<DraftLine[]>(initial);
  const editor = usePriceTagLineEditor({ lines, setLines, priceMode: 'selling', lookups: LOOKUPS });
  return (
    <>
      <PriceTagLinesTable lines={lines} priceMode="selling" isMobile={false} editor={editor} showNumberErrors={false} />
      <output data-testid="codes">{lines.map((l) => l.code || '-').join(',')}</output>
    </>
  );
}

describe('the Item picker in the table', () => {
  it('shows the Discontinued hint on a discontinued product', async () => {
    render(<Harness initial={[row('A')]} />);
    fireEvent.click(screen.getAllByRole('combobox')[0]);
    await screen.findByRole('checkbox', { name: /Tick DIY-BS-4599/ });
    expect(screen.getByText('Discontinued')).toBeInTheDocument();
  });

  it('ticks two results from row 1, Add 2 fills row 1 and inserts the other below row 2 stays last', async () => {
    render(<Harness initial={[row('A'), { ...A(), key: 'B' }]} />);
    fireEvent.click(screen.getAllByRole('combobox')[0]);
    fireEvent.click(await screen.findByRole('checkbox', { name: /Tick DIY-BS-4501/ }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Tick DIY-BS-4502/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Add 2' }));
    await waitFor(() =>
      expect(screen.getByTestId('codes')).toHaveTextContent('DIY-BS-4501,DIY-BS-4502,DIY-BS-4001'),
    );
  });

  it('shows a product already on another row as Already added', async () => {
    render(<Harness initial={[row('A'), { ...A(), key: 'B' }]} />);
    fireEvent.click(screen.getAllByRole('combobox')[0]);
    const box = await screen.findByRole('checkbox', { name: /Tick DIY-BS-4001/ });
    expect(box).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText('Already added')).toBeInTheDocument();
  });
});
