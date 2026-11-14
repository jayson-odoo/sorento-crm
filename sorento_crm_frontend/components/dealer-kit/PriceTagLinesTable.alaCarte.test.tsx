/**
 * PRICETAG-ALA-CARTE (pricetag-ala-carte-acceptance-criteria.md), the shared lines table: AC-1 (the
 * Package select shows for a product with 1+ combos), AC-2 (combo names only, clearable, placeholder
 * "Ala carte"), AC-4 (clearing it through the table) and AC-7 (the Item picker never greys or skips a
 * product already on the request). Through the real table and editor hook; SearchableSelect is a
 * native select stand-in labelled by its placeholder, the Item picker is the real multi-select.
 *
 * Written test-FIRST against the UAC; fake codes and prices only.
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
    clearable?: boolean;
    onChange?: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select
      aria-label={String(props.placeholder ?? '')}
      data-clearable={String(!!props.clearable)}
      value={props.value ?? ''}
      onChange={(e) => props.onChange?.(e.target.value)}
    >
      <option value="" data-empty="true" />
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
import { emptyDraftLine, partsFromCombo, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import type { ProductComboOption, TagItemOption } from '@/app/(auth)/portal/lib/price-tag-request-service';

const part = (id: string, code: string) => ({
  product_id: id,
  code,
  name: code,
  choice_group: null,
  is_upgrade: false,
  topup_amount: null,
  is_discontinued: false,
});
const C: ProductComboOption = { combo_id: 'c-ala-1', name: 'P-ALA-1 + P-ALA-PART', parts: [part('p-ala-part', 'P-ALA-PART')] };
const A: ProductComboOption = { combo_id: 'c-ala-2a', name: 'Package A', parts: [part('p-ala-part', 'P-ALA-PART')] };
const B: ProductComboOption = { combo_id: 'c-ala-2b', name: 'Package B', parts: [] };

const ITEMS: TagItemOption[] = [
  { kind: 'product', id: 'p-ala-1', code: 'P-ALA-1', name: 'Ala basin', list_price: 100 },
  { kind: 'product', id: 'p-ala-4', code: 'P-ALA-4', name: 'Ala mirror', list_price: 50 },
];
const COMBOS: Record<string, ProductComboOption[]> = { 'p-ala-1': [C], 'p-ala-2': [A, B], 'p-ala-4': [] };

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
        {JSON.stringify(lines.map((l) => ({ code: l.code, combo_id: l.combo_id, parts: l.parts.length })))}
      </output>
    </>
  );
}

const packageSelects = () => screen.queryAllByRole('combobox', { name: 'Ala carte' }) as HTMLSelectElement[];
const optionLabels = (select: HTMLSelectElement) =>
  Array.from(select.options)
    .filter((o) => o.dataset.empty !== 'true')
    .map((o) => o.textContent);
const state = () =>
  JSON.parse(screen.getByTestId('state').textContent ?? '[]') as { code: string; combo_id: string | null; parts: number }[];

describe('AC-1 the Package select shows for a product with 1+ combos', () => {
  it('a line of a product with exactly one combo shows the Package select', () => {
    render(<Harness initial={[productLine('l1', 'p-ala-1', 'P-ALA-1', null)]} />);
    expect(packageSelects()).toHaveLength(1);
  });

  it('a line of a product with two combos shows it too', () => {
    render(<Harness initial={[productLine('l1', 'p-ala-2', 'P-ALA-2', null)]} />);
    expect(packageSelects()).toHaveLength(1);
  });

  it('a product with no combo and a set line show no Package select', () => {
    const setLine = {
      ...emptyDraftLine(),
      key: 'l2',
      line_type: 'product_set',
      product_set_id: 's-ala-1',
      code: 'S-ALA-1',
      name: 'S-ALA-1',
      combos_loaded: true,
    } as DraftLine;
    render(<Harness initial={[productLine('l1', 'p-ala-4', 'P-ALA-4', null), setLine]} />);
    expect(packageSelects()).toHaveLength(0);
    expect(screen.queryByRole('combobox', { name: 'Package' })).toBeNull();
  });
});

describe('AC-2 options, clearable, placeholder', () => {
  it('one combo: clearable, placeholder "Ala carte", options are the combo names only, empty value when ala carte', () => {
    render(<Harness initial={[productLine('l1', 'p-ala-1', 'P-ALA-1', null)]} />);
    const [select] = packageSelects();
    expect(select).toBeDefined();
    expect(select.dataset.clearable).toBe('true');
    expect(select.value).toBe('');
    expect(optionLabels(select)).toEqual([C.name]);
  });

  it('two combos: options are both names in order, no extra "Ala carte" option; a line on B shows B', () => {
    render(<Harness initial={[productLine('l1', 'p-ala-2', 'P-ALA-2', B.combo_id)]} />);
    const [select] = packageSelects();
    expect(select).toBeDefined();
    expect(optionLabels(select)).toEqual(['Package A', 'Package B']);
    expect(optionLabels(select)).not.toContain('Ala carte');
    expect(select.value).toBe(B.combo_id);
  });
});

describe('AC-4 choosing and clearing the Package in the table', () => {
  it('a one-combo line on C cleared goes ala carte with no parts; choosing C again puts its parts back', async () => {
    render(<Harness initial={[productLine('l1', 'p-ala-1', 'P-ALA-1', C.combo_id)]} />);
    const [select] = packageSelects();
    expect(select).toBeDefined();
    fireEvent.change(select, { target: { value: '' } });
    await waitFor(() => expect(state()[0]).toEqual({ code: 'P-ALA-1', combo_id: null, parts: 0 }));
    fireEvent.change(packageSelects()[0], { target: { value: C.combo_id } });
    await waitFor(() => expect(state()[0]).toEqual({ code: 'P-ALA-1', combo_id: C.combo_id, parts: 1 }));
  });
});

// Scoped to the Item picker's list, so a Package select option whose combo name holds the code
// (C is "P-ALA-1 + P-ALA-PART") can never be the row found.
const rowFor = async (code: string) =>
  within(await screen.findByRole('listbox')).findByRole('option', { name: new RegExp(code) });

describe('AC-7 the Item picker never greys or skips a product already on the request', () => {
  it('a product on the request is not disabled or "Already added", and a click adds another line of it', async () => {
    render(<Harness initial={[productLine('l1', 'p-ala-1', 'P-ALA-1', C.combo_id), { ...emptyDraftLine(), key: 'l2' } as DraftLine]} />);
    fireEvent.click(screen.getByRole('combobox', { name: 'Item for line 2' }));
    const option = await rowFor('P-ALA-1');
    expect(option).not.toHaveAttribute('aria-disabled', 'true');
    expect(within(option).queryByText('Already added')).toBeNull();
    fireEvent.click(option);
    await waitFor(() => expect(state().filter((l) => l.code === 'P-ALA-1')).toHaveLength(2));
    expect(state()[1]).toMatchObject({ code: 'P-ALA-1', combo_id: null, parts: 0 });
  });

  it('a product with no combo already on the request is not greyed either (ala carte twice is allowed)', async () => {
    render(<Harness initial={[productLine('l1', 'p-ala-4', 'P-ALA-4', null), { ...emptyDraftLine(), key: 'l2' } as DraftLine]} />);
    fireEvent.click(screen.getByRole('combobox', { name: 'Item for line 2' }));
    const option = await rowFor('P-ALA-4');
    expect(option).not.toHaveAttribute('aria-disabled', 'true');
    expect(within(option).queryByText('Already added')).toBeNull();
  });
});
