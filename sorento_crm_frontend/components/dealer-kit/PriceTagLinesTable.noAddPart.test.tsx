/**
 * PRICETAG-ALA-CARTE, owner ruling (crew answer (a)): the "Add part" select is gone from every line
 * of the price tag request line editor, ala carte and combo lines alike, on every path that puts a
 * line on the table (single pick, multi-add, reopen). A deleted package row comes back only through
 * the Package warning's Restore (guard), and a saved line that already carries an extra catalogue
 * part still renders it with its Remove and still sends it on save (guard).
 *
 * Through the real table and editor hook; SearchableSelect is a native select stand-in labelled by
 * its placeholder, the Item picker is the real multi-select. Written test-FIRST; fake codes only.
 */
import React, { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('@/components/dealer-kit/DesignViewer', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/dealer-kit/DesignLightbox', () => ({ __esModule: true, default: () => null }));
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    placeholder?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select
      aria-label={String(props.placeholder ?? '')}
      data-placeholder={String(props.placeholder ?? '')}
      value={props.value ?? ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="" />
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { PriceTagLinesTable } from './PriceTagLinesTable';
import { usePriceTagLineEditor, type PriceTagLineLookups } from '@/hooks/usePriceTagLineEditor';
import {
  draftLinesPayload,
  emptyDraftLine,
  lineToDraft,
  partsFromCombo,
  type DraftLine,
} from '@/lib/dealer-kit/price-tag-draft-lines';
import type { ProductComboOption, TagItemOption } from '@/app/(auth)/portal/lib/price-tag-request-service';

const part = (id: string, code: string) => ({
  product_id: id,
  code,
  name: `${code} name`,
  choice_group: null,
  is_upgrade: false,
  topup_amount: null,
  is_discontinued: false,
});
// One combo, two fixed parts: deleting one leaves a Package warning naming it.
const C: ProductComboOption = {
  combo_id: 'c-nap-1',
  name: 'Package NAP',
  parts: [part('p-nap-part1', 'P-NAP-PART1'), part('p-nap-part2', 'P-NAP-PART2')],
};

const ITEMS: TagItemOption[] = [
  { kind: 'product', id: 'p-nap-1', code: 'P-NAP-1', name: 'Nap basin', list_price: 100 },
  { kind: 'product', id: 'p-nap-4', code: 'P-NAP-4', name: 'Nap mirror', list_price: 50 },
];
const COMBOS: Record<string, ProductComboOption[]> = { 'p-nap-1': [C], 'p-nap-4': [] };

const LOOKUPS: PriceTagLineLookups = {
  lookupTagItems: vi.fn(async (q?: string) =>
    ITEMS.filter((i) => !q || i.code.toLowerCase().includes(q.toLowerCase())),
  ),
  lookupProductCombos: vi.fn(async (id: string) => ({ host_guarded: false, combos: COMBOS[id] ?? [] })),
  lookupLinePricing: vi.fn(async () => []),
};

function productLine(key: string, productId: string, code: string, comboId: string | null): DraftLine {
  const combos = COMBOS[productId] ?? [];
  const combo = combos.find((c) => c.combo_id === comboId);
  return {
    ...emptyDraftLine(),
    key,
    line_type: 'product',
    product_id: productId,
    code,
    name: code,
    combo_id: comboId,
    combos,
    combos_loaded: true,
    parts: combo ? partsFromCombo(combo) : [],
  } as DraftLine;
}

function Harness({ initial }: { initial: DraftLine[] }) {
  const [lines, setLines] = useState<DraftLine[]>(initial);
  const editor = usePriceTagLineEditor({ lines, setLines, priceMode: 'list', lookups: LOOKUPS });
  return (
    <>
      <PriceTagLinesTable lines={lines} priceMode="list" isMobile={false} editor={editor} showNumberErrors={false} />
      <output data-testid="state">
        {JSON.stringify(
          lines.map((l) => ({
            code: l.code,
            combo_id: l.combo_id,
            combos_loaded: l.combos_loaded,
            parts: l.parts.map((p) => p.code),
          })),
        )}
      </output>
      <output data-testid="payload">{JSON.stringify(draftLinesPayload(lines, 'list'))}</output>
    </>
  );
}

const state = () =>
  JSON.parse(screen.getByTestId('state').textContent ?? '[]') as {
    code: string;
    combo_id: string | null;
    combos_loaded: boolean;
    parts: string[];
  }[];
const payload = () =>
  JSON.parse(screen.getByTestId('payload').textContent ?? '[]') as {
    parts: { product_id: string | null; role: string | null; candidates: string[] }[];
  }[];

/** No "Add part" control in any form: not by label, placeholder or visible text. */
function expectNoAddPart() {
  expect(screen.queryByRole('combobox', { name: 'Add part' })).toBeNull();
  expect(screen.queryByLabelText('Add part')).toBeNull();
  expect(screen.queryByPlaceholderText('Add part')).toBeNull();
  expect(document.querySelector('[data-placeholder="Add part"]')).toBeNull();
  expect(screen.queryByText('Add part')).toBeNull();
}

describe('1. an ala carte line of a product with a combo', () => {
  it('shows the Package select but no "Add part"', () => {
    render(<Harness initial={[productLine('l1', 'p-nap-1', 'P-NAP-1', null)]} />);
    // Sanity: the line is the one the old code offered Add part on (a product with a combo).
    expect(screen.getByRole('combobox', { name: 'Ala carte' })).toBeInTheDocument();
    expectNoAddPart();
  });
});

describe('2. a combo line with one package row deleted', () => {
  const removePart2 = () =>
    fireEvent.click(screen.getByRole('button', { name: 'Remove part P-NAP-PART2 from line 1' }));

  it('shows no "Add part"', async () => {
    render(<Harness initial={[productLine('l1', 'p-nap-1', 'P-NAP-1', C.combo_id)]} />);
    removePart2();
    await waitFor(() => expect(state()[0].parts).toEqual(['P-NAP-PART1']));
    expectNoAddPart();
  });

  it('guard: the Package warning Restore button is still there and puts the deleted row back', async () => {
    render(<Harness initial={[productLine('l1', 'p-nap-1', 'P-NAP-1', C.combo_id)]} />);
    removePart2();
    await waitFor(() => expect(state()[0].parts).toEqual(['P-NAP-PART1']));
    expect(screen.getByText('Package warning')).toBeInTheDocument();
    expect(screen.getByText('Missing: P-NAP-PART2')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Restore' }));
    await waitFor(() => expect(state()[0].parts).toEqual(['P-NAP-PART1', 'P-NAP-PART2']));
    expect(screen.queryByText('Package warning')).toBeNull();
    expect(screen.getByRole('button', { name: 'Remove part P-NAP-PART2 from line 1' })).toBeInTheDocument();
  });
});

describe('3. a reopened saved line carrying an extra catalogue part', () => {
  function reopened(): DraftLine {
    const saved = lineToDraft(
      {
        id: 'saved-l1',
        line_type: 'product',
        product_id: 'p-nap-1',
        product_set_id: null,
        name: 'Nap basin',
        code: 'P-NAP-1',
        quantity: 1,
        combo_id: C.combo_id,
        price_type: 'list',
        parts: [
          { id: 'sp1', product_id: 'p-nap-part1', code: 'P-NAP-PART1', name: 'P-NAP-PART1 name', role: null, candidates: [] },
          { id: 'sp2', product_id: 'p-nap-part2', code: 'P-NAP-PART2', name: 'P-NAP-PART2 name', role: null, candidates: [] },
          // Not in the combo: added by hand before the ruling.
          { id: 'sp3', product_id: 'p-nap-xtra', code: 'P-NAP-XTRA', name: 'Nap extra bracket', role: null, candidates: [] },
        ],
      } as never,
      'list',
    );
    return { ...saved, combos: [C], combos_loaded: true } as DraftLine;
  }

  it('shows no "Add part"', () => {
    render(<Harness initial={[reopened()]} />);
    expectNoAddPart();
  });

  it('guard: the extra part row renders with its code and its Remove control', () => {
    render(<Harness initial={[reopened()]} />);
    expect(screen.getByText('Nap extra bracket')).toBeInTheDocument();
    expect(screen.getByText('P-NAP-XTRA')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove part P-NAP-XTRA from line 1' })).toBeInTheDocument();
  });

  it('guard: the save payload still carries the extra part, unchanged and in order', () => {
    render(<Harness initial={[reopened()]} />);
    const [line] = payload();
    expect(line.parts).toEqual([
      { product_id: 'p-nap-part1', role: null, candidates: [] },
      { product_id: 'p-nap-part2', role: null, candidates: [] },
      { product_id: 'p-nap-xtra', role: null, candidates: [] },
    ]);
  });
});

// Scoped to the Item picker's list so a Package option can never be the row found.
const rowFor = async (code: string) =>
  within(await screen.findByRole('listbox')).findByRole('option', { name: new RegExp(code) });

describe('4. multi-add, and a product with no combo', () => {
  it('two products added at once (one with a combo, one without) show no "Add part"', async () => {
    render(<Harness initial={[{ ...emptyDraftLine(), key: 'l1' } as DraftLine]} />);
    fireEvent.click(screen.getByRole('combobox', { name: 'Item for line 1' }));
    fireEvent.click(await rowFor('P-NAP-1'));
    fireEvent.click(await rowFor('P-NAP-4'));
    await waitFor(() => {
      const lines = state().filter((l) => l.code);
      expect(lines.map((l) => l.code)).toEqual(['P-NAP-1', 'P-NAP-4']);
      expect(lines.every((l) => l.combos_loaded)).toBe(true);
    });
    // Sanity: the combo answer arrived, so the old code would now show Add part on line 1.
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Ala carte' })).toBeInTheDocument());
    expectNoAddPart();
  });

  it('a line of a product with no combo shows no "Add part"', () => {
    render(<Harness initial={[productLine('l1', 'p-nap-4', 'P-NAP-4', null)]} />);
    expectNoAddPart();
  });
});
