/**
 * PRICETAG-COMBO: the Combos card shows and edits the new combo fields.
 *
 * UAC: documentation/plans/dealer-kit/price-tag-combo-template-fields-acceptance-criteria.md
 * (AC-6.1, AC-6.2, AC-6.3, AC-6.4).
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). The card renders no price, description,
 * free items, top-up or upgrade control yet, so each case is red on a missing element.
 * The card edits in place (as its choice-group control already does), so editing is
 * "the input is there and a change is saved"; read-only is "the same labels, the values
 * as text, no input".
 *
 * Assumptions the coder may tighten with the captain: field labels are the UAC words
 * (List price, Sell price, Description, Accessories included; per part Sell price, Top-up,
 * Upgrade), saved through `useUpdateProductCombo().mutate({ comboId, write })` beside the
 * existing `useUpdateProductComboPart().mutate({ partId, write })`, on blur.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';

import type { ProductComboPartRow, ProductComboRow } from '../../types/productCombo.types';

const permission = vi.hoisted(() => ({ canEdit: true }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => permission.canEdit,
}));

// PRICETAG-COMBO-FORMAT AC-21: the description is the shared RichTextEditor (its own suite covers
// tiptap) and the live tag preview has its own suite; both are stood in for here so these tests
// keep pinning what they always did.
vi.mock('@/components/ui/rich-text-editor', () => {
  const Stand = (props: {
    value?: string;
    onChange: (v: string) => void;
    'aria-labelledby'?: string;
  }) => (
    <textarea
      aria-labelledby={props['aria-labelledby']}
      value={props.value ?? ''}
      onChange={(e) => props.onChange(e.target.value)}
    />
  );
  return { RichTextEditor: Stand, default: Stand };
});
vi.mock('./ComboTagPreview', () => ({ ComboTagPreview: () => null }));

vi.mock('./ComboTemplatesField', () => ({ ComboTemplatesField: () => null }));
// The accessory list has its own suite; here it stands in as a labelled marker.
vi.mock('./AccessoryListField', () => ({
  AccessoryListField: (props: { label?: string; ownerId: string; canEdit: boolean }) => (
    <div data-testid="accessory-list" data-owner={props.ownerId} data-can-edit={String(props.canEdit)}>
      {props.label}
    </div>
  ),
}));

vi.mock('./AddComboModal', () => ({
  AddComboModal: () => null,
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={props.placeholder ?? ''}
      value={props.value}
      onChange={(event) => props.onChange(event.target.value)}
    >
      <option value="">{props.placeholder ?? ''}</option>
      {(props.options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

const combosQuery = vi.hoisted(() => ({
  value: { data: undefined, isLoading: false, isError: false } as {
    data: ProductComboRow[] | undefined;
    isLoading: boolean;
    isError: boolean;
  },
}));
const updateComboMutate = vi.hoisted(() => vi.fn());
const updatePartMutate = vi.hoisted(() => vi.fn());

vi.mock('../../hooks/useProductCombos', () => ({
  useProductCombos: () => combosQuery.value,
  useProductComboDelete: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useProductComboPartDelete: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useAddProductComboPart: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateProductComboPart: () => ({ mutate: updatePartMutate }),
  useUpdateProductCombo: () => ({ mutate: updateComboMutate, isPending: false }),
}));

vi.mock('../../hooks/useProductComboImage', () => ({
  useProductComboImage: () => ({
    uploadMutateAsync: vi.fn(),
    deleteMutateAsync: vi.fn(),
    isUploading: false,
    isDeleting: false,
  }),
}));

import { ProductCombosSection } from './ProductCombosSection';

function part(
  overrides: Partial<ProductComboPartRow> & Pick<ProductComboPartRow, 'id' | 'code'>,
): ProductComboPartRow {
  return {
    combo_id: 'combo-3',
    product_id: `p-${overrides.id}`,
    product_name: `ZZT ${overrides.code}`,
    dimensions: null,
    choice_group: null,
    sort_order: 0,
    ...overrides,
  } as ProductComboPartRow;
}

const MIRROR = part({ id: 'part-mirror', code: 'ZZMIR' });
const WHITE = part({
  id: 'part-white',
  code: 'ZZWHITE',
  choice_group: 'Basin',
  sort_order: 1,
  sell_price: 280,
} as never);
const BLACK = part({ id: 'part-black', code: 'ZZBLACK', choice_group: 'Basin', sort_order: 2 });
const STONE = part({
  id: 'part-stone',
  code: 'ZZSTONE',
  sort_order: 3,
  is_upgrade: true,
  topup_amount: 100,
} as never);

const COMBO = {
  id: 'combo-3',
  host_product_id: 'prod-1',
  name: '3 in 1',
  sort_order: 0,
  parts: [MIRROR, WHITE, BLACK, STONE],
  description: 'Cabinet, mirror and basin',
  list_price: 2500,
  sell_price: 1999,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
} as unknown as ProductComboRow;

function renderCard() {
  combosQuery.value = { data: [COMBO], isLoading: false, isError: false };
  render(<ProductCombosSection productId="prod-1" />);
  return screen.getByText('3 in 1').closest('[data-testid="combo-block"]') as HTMLElement;
}

function written(mock: ReturnType<typeof vi.fn>) {
  return mock.mock.calls.map((call) => call[0]);
}

beforeEach(() => {
  vi.clearAllMocks();
  permission.canEdit = true;
});

describe('Combos card, combo fields (AC-6.1)', () => {
  it('shows List price, Sell price, Description and Accessories included for each combo, editable', () => {
    const block = renderCard();
    const scope = within(block);

    expect(scope.getByLabelText(/^List price \(RM\)/i)).toHaveValue(2500);
    expect(scope.getByLabelText(/^Sell price \(RM\)/i)).toHaveValue(1999);
    expect(scope.getByLabelText(/^Description/i)).toHaveValue('<p>Cabinet, mirror and basin</p>');
    // Accessories included is the accessory list now, not a text box (renamed from Free items, 7 Nov).
    expect(scope.queryByLabelText(/^Free items/i)).toBeNull();
    expect(scope.queryByText(/Free items/i)).toBeNull();
    expect(scope.getByTestId('accessory-list')).toHaveTextContent('Accessories included');
    expect(scope.getByTestId('accessory-list')).toHaveAttribute('data-owner', 'combo-3');
  });

  it('saves a changed combo price through the combo update hook with a number', () => {
    const block = renderCard();
    const input = within(block).getByLabelText(/^List price \(RM\)/i);
    fireEvent.change(input, { target: { value: '2600' } });
    fireEvent.blur(input);

    const calls = written(updateComboMutate);
    expect(calls).toHaveLength(1);
    expect(calls[0].comboId).toBe('combo-3');
    expect(Number(calls[0].write.list_price)).toBe(2600);
    expect(Object.keys(calls[0].write)).toEqual(['list_price']);
  });

  it('saves a changed description', () => {
    const block = renderCard();
    const description = within(block).getByLabelText(/^Description/i);
    fireEvent.change(description, { target: { value: 'New text' } });
    fireEvent.blur(description);

    expect(written(updateComboMutate)).toEqual([
      { comboId: 'combo-3', write: { description: 'New text' } },
    ]);
  });

  it('sends null, not an empty string, when a price is cleared', () => {
    const block = renderCard();
    const input = within(block).getByLabelText(/^Sell price \(RM\)/i);
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.blur(input);

    expect(written(updateComboMutate)).toEqual([
      { comboId: 'combo-3', write: { sell_price: null } },
    ]);
  });

  it('does not save when nothing changed', () => {
    const block = renderCard();
    fireEvent.blur(within(block).getByLabelText(/^List price \(RM\)/i));
    expect(updateComboMutate).not.toHaveBeenCalled();
  });

  it('shows Sell price if picked on an option row and saves it', () => {
    renderCard();
    const row = screen.getByText('ZZWHITE').closest('div.grid') as HTMLElement;
    const sell = within(row).getByLabelText(/Sell price/i);
    expect(sell).toHaveValue(280);

    fireEvent.change(sell, { target: { value: '290' } });
    fireEvent.blur(sell);
    const calls = written(updatePartMutate).filter((call) => call.write.sell_price !== undefined);
    expect(calls).toHaveLength(1);
    expect(calls[0].partId).toBe('part-white');
    expect(Number(calls[0].write.sell_price)).toBe(290);
  });

  it('shows Top-up and an Upgrade toggle on a part row and saves them', () => {
    renderCard();
    const row = screen.getByText('ZZSTONE').closest('div.grid') as HTMLElement;
    const topup = within(row).getByLabelText(/Top-up/i);
    expect(topup).toHaveValue(100);

    fireEvent.change(topup, { target: { value: '0' } });
    fireEvent.blur(topup);
    const topupCalls = written(updatePartMutate).filter((call) => call.write.topup_amount !== undefined);
    expect(topupCalls).toHaveLength(1);
    expect(Number(topupCalls[0].write.topup_amount)).toBe(0);

    const toggle = within(row).getByRole('checkbox', { name: /Upgrade/i });
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);
    expect(written(updatePartMutate)).toContainEqual({
      partId: 'part-stone',
      write: { is_upgrade: false },
    });
  });

  it('read-only shows the same labels and the values as text, with no input', () => {
    permission.canEdit = false;
    const block = renderCard();
    const scope = within(block);

    expect(scope.getByText(/List price/i)).toBeInTheDocument();
    expect(scope.getByText(/Sell price/i)).toBeInTheDocument();
    expect(scope.getByTestId('accessory-list')).toHaveAttribute('data-can-edit', 'false');
    expect(scope.getByText('Cabinet, mirror and basin')).toBeInTheDocument();
    expect(scope.getByText(/2,?500/)).toBeInTheDocument();
    expect(scope.queryByLabelText(/^List price \(RM\)/i)).toBeNull();
    expect(scope.queryByLabelText(/^Description/i)).toBeNull();
  });

  it('adds no new page and no new modal: no dialog role anywhere', () => {
    renderCard();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });
});

/** The Upgrade block heading: the "Upgrade" text that is not a row's toggle label. */
function upgradeHeading(): HTMLElement | undefined {
  return screen
    .queryAllByText(/^Upgrade$/i)
    .find((node) => !node.closest('label') && node.tagName !== 'BUTTON');
}

describe('Upgrade block (AC-6.2)', () => {
  it('draws upgrade rows in their own Upgrade block, after the choice groups', () => {
    renderCard();
    const heading = upgradeHeading() as HTMLElement;
    expect(heading).toBeDefined();
    const basin = screen.getByText(/^Basin - pick one$/);
    expect(
      basin.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    const block = heading.closest('div') as HTMLElement;
    expect(within(block).getByText('ZZSTONE')).toBeInTheDocument();
    expect(within(block).queryByText('ZZMIR')).toBeNull();
    expect(within(block).queryByText('ZZWHITE')).toBeNull();
  });

  it('keeps an upgrade out of the fixed parts and the choice group', () => {
    renderCard();
    const basin = screen.getByText(/^Basin - pick one$/).closest('div') as HTMLElement;
    expect(within(basin).queryByText('ZZSTONE')).toBeNull();
  });

  it('draws no Upgrade block when the combo has no upgrade rows', () => {
    combosQuery.value = {
      data: [{ ...COMBO, parts: [MIRROR, WHITE, BLACK] } as ProductComboRow],
      isLoading: false,
      isError: false,
    };
    render(<ProductCombosSection productId="prod-1" />);
    expect(upgradeHeading()).toBeUndefined();
  });
});

describe('Combos card hygiene (AC-6.3, AC-6.4)', () => {
  it('a new field row stacks at 375px and long values truncate', () => {
    renderCard();
    const row = screen.getByText('ZZWHITE').closest('div.grid') as HTMLElement;
    expect(row.className).toContain('sm:grid-cols-');
    expect(screen.getByText('ZZWHITE').className).toContain('truncate');
    // The classes this lane added: the new inputs wrap under the code at 375px, and the
    // combo's own fields stack in one column before the sm breakpoint.
    const priceBox = within(row).getByLabelText(/Sell price if picked/i).closest('div.flex-wrap') as HTMLElement;
    expect(priceBox.className).toContain('sm:col-span-full');
    const comboFields = within(screen.getByTestId('combo-block')).getByLabelText(/^List price \(RM\)/i).closest('div.grid') as HTMLElement;
    expect(comboFields.className).toContain('sm:grid-cols-2');
  });

  it('the accessory list cell can shrink, so a long row never widens the page at 375px', () => {
    renderCard();
    // A grid item defaults to min-width:auto; without min-w-0 the list's truncating rows push
    // the whole page past 375px (crew pass on #2273: 399px).
    const cell = screen.getAllByTestId('accessory-list')[0].parentElement as HTMLElement;
    expect(cell.className).toContain('min-w-0');
  });

  it('shows a message and does not save a negative figure', () => {
    const block = renderCard();
    const input = within(block).getByLabelText(/^List price \(RM\)/i);
    fireEvent.change(input, { target: { value: '-5' } });
    fireEvent.blur(input);
    expect(updateComboMutate).not.toHaveBeenCalled();
    expect(within(block).getByText(/Enter a number of at least 0/i)).toBeInTheDocument();
  });

  it('puts the box back when the server refuses the write', () => {
    const block = renderCard();
    const input = within(block).getByLabelText(/^List price \(RM\)/i);
    fireEvent.change(input, { target: { value: '2600' } });
    fireEvent.blur(input);
    const options = updateComboMutate.mock.calls[0][1] as { onError: () => void };
    expect(typeof options.onError).toBe('function');
    act(() => options.onError());
    expect(within(block).getByLabelText(/^List price \(RM\)/i)).toHaveValue(2500);
  });

  it('shows no uuid anywhere on the card', () => {
    const block = renderCard();
    expect(block.textContent ?? '').not.toMatch(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
    );
  });
});
