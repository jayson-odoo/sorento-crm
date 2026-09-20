/**
 * The Combos section on the product page (S1, D1).
 *
 * UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`
 * AC-S1-1 (the list and its empty state), AC-S1-4 (the choice group control and
 * "pick one" grouping), AC-S1-5 (removal is a deferred action, never a confirm
 * dialog) and AC-S1-9 (the parts table scrolls inside its own container).
 *
 * Marketing reads the catalogue page beside this section and records the package
 * once. What these tests pin is what a reader of that section can tell at a
 * glance: which parts always come with the cabinet, and which four are the one
 * basin they pick - because a choice group rendered as four ordinary part rows
 * says "this package contains four basins", which is a different product.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

import type {
  ProductComboPartRow,
  ProductComboRow,
} from '../../types/productCombo.types';

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

vi.mock('./AddComboModal', () => ({
  AddComboModal: ({ open }: { open: boolean }) =>
    open ? <div data-testid="add-combo-modal" /> : null,
}));

/** The choice-group control and the Add part picker are both SearchableSelect;
 *  the real one is a Radix popover whose options exist only while it is open,
 *  which would test the popover rather than the section. */
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
  value: { data: undefined, isLoading: true, isError: false } as {
    data: ProductComboRow[] | undefined;
    isLoading: boolean;
    isError: boolean;
  },
}));
const comboDeleteRun = vi.hoisted(() => vi.fn());
const partDeleteRun = vi.hoisted(() => vi.fn());
const updatePartMutate = vi.hoisted(() => vi.fn());
const addPartMutateAsync = vi.hoisted(() => vi.fn());

vi.mock('../../hooks/useProductCombos', () => ({
  useProductCombos: () => combosQuery.value,
  useProductComboDelete: () => ({ run: comboDeleteRun, targetId: null, isPending: false }),
  useProductComboPartDelete: () => ({ run: partDeleteRun, targetId: null, isPending: false }),
  useAddProductComboPart: () => ({ mutateAsync: addPartMutateAsync, isPending: false }),
  useUpdateProductComboPart: () => ({ mutate: updatePartMutate }),
}));

import { ProductCombosSection } from './ProductCombosSection';

const PRODUCT_ID = 'prod-cabinet';

function part(
  overrides: Partial<ProductComboPartRow> & Pick<ProductComboPartRow, 'id' | 'code'>,
): ProductComboPartRow {
  return {
    combo_id: 'combo-3',
    product_id: `p-${overrides.id}`,
    product_name: `ZZT ${overrides.code}`,
    dimensions: '800 x 500 x 220 mm',
    choice_group: null,
    sort_order: 0,
    ...overrides,
  };
}

const MIRROR = part({ id: 'part-mirror', code: 'SRTMR502-BL', sort_order: 0 });
const BASIN_WHITE = part({
  id: 'part-basin-wh',
  code: 'SRTBS900-WH',
  choice_group: 'Basin',
  sort_order: 1,
});
const BASIN_BLACK = part({
  id: 'part-basin-bk',
  code: 'SRTBS900-BK',
  choice_group: 'Basin',
  sort_order: 2,
});

const COMBO_3_IN_1: ProductComboRow = {
  id: 'combo-3',
  host_product_id: PRODUCT_ID,
  name: '3 in 1',
  sort_order: 0,
  parts: [MIRROR, BASIN_WHITE, BASIN_BLACK],
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
};

const COMBO_4_IN_1: ProductComboRow = {
  ...COMBO_3_IN_1,
  id: 'combo-4',
  name: '4 in 1',
  sort_order: 1,
  parts: [{ ...MIRROR, id: 'part-mirror-2', combo_id: 'combo-4' }],
};

beforeEach(() => {
  vi.clearAllMocks();
  combosQuery.value = { data: [], isLoading: false, isError: false };
});

// ---------------------------------------------------------------------------
// AC-S1-1 - the list, its states, and the empty state
// ---------------------------------------------------------------------------

describe('ProductCombosSection', () => {
  it('says "No combos" with an Add combo button when the product has none', () => {
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    expect(screen.getByText('Combos')).toBeInTheDocument();
    expect(screen.getByText('No combos.')).toBeInTheDocument();
    // The empty state carries the next step, not just the absence (D7 / the
    // CRUD standard's "explicit empty state + next-step CTA").
    expect(screen.getAllByRole('button', { name: /Add combo/ }).length).toBeGreaterThan(0);
  });

  it('shows a loading state rather than an empty one while the combos are in flight', () => {
    combosQuery.value = { data: undefined, isLoading: true, isError: false };
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    // "No combos" while loading reads as a product with no package, which is a
    // fact marketing would act on.
    expect(screen.queryByText('No combos.')).toBeNull();
  });

  it('explains a failed load instead of showing the empty state', () => {
    combosQuery.value = { data: undefined, isLoading: false, isError: true };
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    expect(screen.getByText(/Could not load combos/)).toBeInTheDocument();
    expect(screen.queryByText('No combos.')).toBeNull();
  });

  it('lists every combo by its catalogue name with its parts under it', () => {
    combosQuery.value = { data: [COMBO_3_IN_1, COMBO_4_IN_1], isLoading: false, isError: false };
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    expect(screen.getByText('3 in 1')).toBeInTheDocument();
    expect(screen.getByText('4 in 1')).toBeInTheDocument();
    // A part is named by its own code, name and dimensions - never an id (AC-X-2).
    expect(screen.getAllByText(MIRROR.code).length).toBe(2);
    expect(screen.getAllByText(MIRROR.product_name).length).toBe(2);
    expect(screen.getAllByText('800 x 500 x 220 mm').length).toBeGreaterThan(0);
  });

  it('opens the Add combo modal, which asks for a name only', () => {
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    expect(screen.queryByTestId('add-combo-modal')).toBeNull();
    fireEvent.click(screen.getAllByRole('button', { name: /Add combo/ })[0]);
    expect(screen.getByTestId('add-combo-modal')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // AC-S1-4 - the choice group
  // -------------------------------------------------------------------------

  it('groups parts sharing a label under it, with "pick one", and leaves fixed parts ungrouped', () => {
    combosQuery.value = { data: [COMBO_3_IN_1], isLoading: false, isError: false };
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    const group = screen.getByText(/^Basin - pick one$/).closest('div');
    expect(group).not.toBeNull();
    const grouped = within(group as HTMLElement);
    expect(grouped.getByText(BASIN_WHITE.code)).toBeInTheDocument();
    expect(grouped.getByText(BASIN_BLACK.code)).toBeInTheDocument();
    // The fixed part is NOT inside the group: it always comes with the package.
    expect(grouped.queryByText(MIRROR.code)).toBeNull();
  });

  it('a group of ONE is not offered as a choice - there is nothing to pick between', () => {
    combosQuery.value = {
      data: [{ ...COMBO_3_IN_1, parts: [MIRROR, BASIN_WHITE] }],
      isLoading: false,
      isError: false,
    };
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    // The heading is the label alone. `getAllByText` because "Basin" is also an
    // option inside every choice-group control on the combo.
    const headings = screen
      .getAllByText('Basin')
      .filter((node) => node.tagName === 'P');
    expect(headings).toHaveLength(1);
    expect(screen.queryByText(/pick one/)).toBeNull();
  });

  it('the choice-group control is clearable, and offers the labels already used on THIS combo', () => {
    combosQuery.value = { data: [COMBO_3_IN_1], isLoading: false, isError: false };
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    const controls = screen.getAllByLabelText('Fixed part');
    expect(controls).toHaveLength(3);
    // Every row offers the vocabulary the combo already uses, deduped - a basin
    // group is a word off the catalogue page, not a list the system can know.
    expect(within(controls[0]).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Fixed part',
      'Basin',
    ]);

    fireEvent.change(controls[0], { target: { value: 'Basin' } });
    expect(updatePartMutate).toHaveBeenCalledWith({
      partId: MIRROR.id,
      write: { choice_group: 'Basin' },
    });

    // Clearing it back to empty makes the part fixed again, sent as null rather
    // than as an empty string.
    fireEvent.change(screen.getAllByLabelText('Fixed part')[1], { target: { value: '' } });
    expect(updatePartMutate).toHaveBeenLastCalledWith({
      partId: BASIN_WHITE.id,
      write: { choice_group: null },
    });
  });

  // -------------------------------------------------------------------------
  // AC-S1-5 - removal is deferred, never a dialog
  // -------------------------------------------------------------------------

  it('Remove part and Delete combo park the removal, with no confirmation dialog (D7)', () => {
    combosQuery.value = { data: [COMBO_3_IN_1], isLoading: false, isError: false };
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    fireEvent.click(screen.getByRole('button', { name: `Remove ${MIRROR.code}` }));
    expect(partDeleteRun).toHaveBeenCalledWith(
      expect.objectContaining({ id: MIRROR.id }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Delete combo 3 in 1' }));
    expect(comboDeleteRun).toHaveBeenCalledWith(
      expect.objectContaining({ id: COMBO_3_IN_1.id, subject: '3 in 1' }),
    );

    // `ConfirmDeleteDialog` is retired: a new importer of it, or of a
    // destructive AlertDialog, is a defect.
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  // -------------------------------------------------------------------------
  // AC-S1-9 - 375px
  // -------------------------------------------------------------------------

  it('a part row stacks at 375px and every long value truncates rather than overflowing', () => {
    combosQuery.value = { data: [COMBO_3_IN_1], isLoading: false, isError: false };
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    const row = screen.getAllByText(MIRROR.code)[0].closest('div.grid');
    expect(row).not.toBeNull();
    // One column under `sm`, three from `sm` up: the page must not scroll
    // sideways at 375px.
    expect((row as HTMLElement).className).toContain('sm:grid-cols-');
    expect(screen.getAllByText(MIRROR.code)[0].className).toContain('truncate');
    expect(screen.getAllByText(MIRROR.product_name)[0].className).toContain('truncate');
  });

  // -------------------------------------------------------------------------
  // AC-S5-5 (PLAN-price-tag-r10.md S5): the combo block shows Upload when
  // empty, else the thumbnail with Replace and Clear - image files only.
  // Written test-FIRST: `ProductComboRow` carries no `image` field yet and
  // the block renders no upload control at all, so this is red on a missing
  // element rather than a wrong one.
  // -------------------------------------------------------------------------

  it('AC-S5-5: shows an Upload control when the combo has no image', () => {
    combosQuery.value = { data: [COMBO_3_IN_1], isLoading: false, isError: false };
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    const combo3 = screen.getByText('3 in 1').closest('[data-testid="combo-block"]');
    expect(combo3).not.toBeNull();
    expect(
      within(combo3 as HTMLElement).getByRole('button', { name: /upload/i }),
    ).toBeInTheDocument();
  });

  it('AC-S5-5: shows the thumbnail with Replace and Clear when the combo has an image', () => {
    combosQuery.value = {
      data: [
        {
          ...COMBO_3_IN_1,
          image: { attachment_id: 'att-combo-1', url: 'https://cdn.example.test/combo.jpg' },
        } as ProductComboRow,
      ],
      isLoading: false,
      isError: false,
    };
    render(<ProductCombosSection productId={PRODUCT_ID} />);

    const combo3 = screen.getByText('3 in 1').closest('[data-testid="combo-block"]');
    expect(combo3).not.toBeNull();
    const scoped = within(combo3 as HTMLElement);
    expect(scoped.getByRole('img', { name: /3 in 1/i })).toHaveAttribute(
      'src',
      'https://cdn.example.test/combo.jpg',
    );
    expect(scoped.getByRole('button', { name: /replace/i })).toBeInTheDocument();
    expect(scoped.getByRole('button', { name: /clear/i })).toBeInTheDocument();
  });
});
