/**
 * COMBO-RENAME: rename a combo in place from its title on the Combos card.
 *
 * UAC: documentation/plans/products/combo-rename-acceptance-criteria.md (AC-1 to AC-6).
 * Written test-FIRST: the card had no rename control, so every case is red on a missing pencil.
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
const updateComboMutateAsync = vi.hoisted(() => vi.fn());
const updatePartMutate = vi.hoisted(() => vi.fn());

vi.mock('../../hooks/useProductCombos', () => ({
  useProductCombos: () => combosQuery.value,
  useProductComboDelete: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useProductComboPartDelete: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useAddProductComboPart: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateProductComboPart: () => ({ mutate: updatePartMutate }),
  useUpdateProductCombo: () => ({
    mutate: updateComboMutate,
    mutateAsync: updateComboMutateAsync,
    isPending: false,
  }),
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

const COMBO = {
  id: 'combo-3',
  host_product_id: 'prod-1',
  name: 'WALL HUNG WATER CLOSET COMBO',
  sort_order: 0,
  parts: [] as ProductComboPartRow[],
  description: null,
  list_price: null,
  sell_price: null,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
} as unknown as ProductComboRow;

function renderCard() {
  combosQuery.value = { data: [COMBO], isLoading: false, isError: false };
  render(<ProductCombosSection productId="prod-1" />);
  return screen.getByTestId('combo-block');
}

function openRename(block: HTMLElement) {
  fireEvent.click(within(block).getByRole('button', { name: 'Rename combo WALL HUNG WATER CLOSET COMBO' }));
  return within(block).getByLabelText('Combo name') as HTMLInputElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  permission.canEdit = true;
});

describe('Combos card, rename (COMBO-RENAME)', () => {
  it('AC-1: no pencil without the edit permission', () => {
    permission.canEdit = false;
    const block = renderCard();
    expect(within(block).queryByRole('button', { name: /^Rename combo/ })).toBeNull();
    expect(within(block).getByText('WALL HUNG WATER CLOSET COMBO')).toBeInTheDocument();
  });

  it('AC-2/AC-6: the pencil opens an input with the current name, capped at 100', () => {
    const block = renderCard();
    const input = openRename(block);
    expect(input).toHaveValue('WALL HUNG WATER CLOSET COMBO');
    expect(input).toHaveAttribute('maxLength', '100');
    expect(within(block).getByRole('button', { name: 'Save' })).toBeInTheDocument();
    expect(within(block).getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('AC-3: Enter saves the trimmed name and closes the editor once the save settles', async () => {
    let resolve: (value: unknown) => void = () => undefined;
    updateComboMutateAsync.mockImplementation(() => new Promise((r) => (resolve = r)));
    const block = renderCard();
    const input = openRename(block);
    fireEvent.change(input, { target: { value: '  WALL HUNG WC SET  ' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(updateComboMutateAsync).toHaveBeenCalledTimes(1);
    expect(updateComboMutateAsync.mock.calls[0][0]).toEqual({
      comboId: 'combo-3',
      write: { name: 'WALL HUNG WC SET' },
    });
    // Through mutateAsync, never mutate: the section's one update mutation is shared with the
    // price and description edits, and a later mutate() drops an earlier call's callbacks.
    expect(updateComboMutate).not.toHaveBeenCalled();
    expect(within(block).getByLabelText('Combo name')).toBeDisabled();

    await act(async () => resolve({}));
    expect(within(block).queryByLabelText('Combo name')).toBeNull();
  });

  it('AC-3: a refused save re-enables the input', async () => {
    updateComboMutateAsync.mockRejectedValue(
      Object.assign(new Error('Server error. Try again or contact support.'), { status: 500 }),
    );
    const block = renderCard();
    const input = openRename(block);
    fireEvent.change(input, { target: { value: 'WALL HUNG WC SET' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(await within(block).findByText('Server error. Try again or contact support.')).toBeInTheDocument();
    expect(within(block).getByLabelText('Combo name')).not.toBeDisabled();
  });

  it('AC-3: Save with the name unchanged closes with no write', () => {
    const block = renderCard();
    openRename(block);
    fireEvent.click(within(block).getByRole('button', { name: 'Save' }));
    expect(updateComboMutateAsync).not.toHaveBeenCalled();
    expect(within(block).queryByLabelText('Combo name')).toBeNull();
  });

  it('AC-2: Escape cancels with no write and restores the title', () => {
    const block = renderCard();
    const input = openRename(block);
    fireEvent.change(input, { target: { value: 'SOMETHING ELSE' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(updateComboMutateAsync).not.toHaveBeenCalled();
    expect(within(block).queryByLabelText('Combo name')).toBeNull();
    expect(within(block).getByText('WALL HUNG WATER CLOSET COMBO')).toBeInTheDocument();
  });

  it('AC-2: Cancel closes with no write', () => {
    const block = renderCard();
    const input = openRename(block);
    fireEvent.change(input, { target: { value: 'SOMETHING ELSE' } });
    fireEvent.click(within(block).getByRole('button', { name: 'Cancel' }));
    expect(updateComboMutateAsync).not.toHaveBeenCalled();
    expect(within(block).queryByLabelText('Combo name')).toBeNull();
  });

  it('AC-4: an empty name is a field error and sends nothing', () => {
    const block = renderCard();
    const input = openRename(block);
    fireEvent.change(input, { target: { value: '   ' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(updateComboMutateAsync).not.toHaveBeenCalled();
    expect(within(block).getByText('A combo needs a name')).toBeInTheDocument();
    expect(within(block).getByLabelText('Combo name')).toHaveAttribute('aria-invalid', 'true');
  });

  it('AC-5: a 409 reads as the taken-name message and the editor stays open', async () => {
    updateComboMutateAsync.mockRejectedValue(
      Object.assign(new Error('This product already has a combo called "3 in 1"'), { status: 409 }),
    );
    const block = renderCard();
    const input = openRename(block);
    fireEvent.change(input, { target: { value: '3 in 1' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(updateComboMutateAsync).toHaveBeenCalledTimes(1);
    expect(
      await within(block).findByText('Another combo on this product already has this name'),
    ).toBeInTheDocument();
    expect(within(block).getByLabelText('Combo name')).toHaveValue('3 in 1');
  });
});
