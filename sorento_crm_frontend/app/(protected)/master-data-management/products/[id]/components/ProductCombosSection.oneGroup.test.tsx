/**
 * COMBO-SETTINGS-UX owner round 1 (10 Nov 18:2x), crew ruling: a choice group with ONE part is a
 * FIXED part (CARD-pricetag-combo-render-04nov.md:134). It gets no "Sell price if picked" and reads
 * as fixed; a choice is a group of 2+ parts. The group field reads as what it is, "Choice group
 * (only for pick-one parts)", never as a name field: a part's own name is its Label.
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

const GROUP = 'Choice group (only for pick-one parts)';
const part = (over: Partial<ProductComboPartRow> & Pick<ProductComboPartRow, 'id' | 'code'>): ProductComboPartRow =>
  ({
    combo_id: 'combo-t',
    product_id: `p-${over.id}`,
    product_name: over.code,
    dimensions: null,
    choice_group: null,
    sort_order: 0,
    ...over,
  }) as ProductComboPartRow;

const ALONE = part({ id: 'acc', code: 'ACC-SRT4003', choice_group: 'Test', sell_price: '50.00' } as never);
const TAP1 = part({ id: 't1', code: 'SRTKT1633SS-BL', choice_group: 'TAP' });
const TAP2 = part({ id: 't2', code: 'SRTKT1634SS-BL', choice_group: 'TAP' });
const COMBO = {
  id: 'combo-t',
  host_product_id: 'prod-host',
  name: 'SRTKS7061-BL',
  sort_order: 0,
  description: null,
  parts: [ALONE, TAP1, TAP2],
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
} as unknown as ProductComboRow;

beforeEach(() => {
  permission.canEdit = true;
  combosQuery.value = { data: [COMBO], isLoading: false, isError: false };
});

describe('a one-part choice group is a fixed part', () => {
  it('offers "Sell price if picked" only on a real choice (2+ parts)', () => {
    render(<ProductCombosSection productId="prod-host" productCode="SRTKS7061-BL" />);
    expect(screen.queryByLabelText('Sell price if picked for ACC-SRT4003')).toBeNull();
    expect(screen.getByLabelText('Sell price if picked for SRTKT1633SS-BL')).toBeInTheDocument();
    expect(screen.getByLabelText('Sell price if picked for SRTKT1634SS-BL')).toBeInTheDocument();
  });

  it('says plainly that the lone part prints as a fixed part, and shows it with the fixed parts', () => {
    render(<ProductCombosSection productId="prod-host" productCode="SRTKS7061-BL" />);
    expect(screen.getByText('Only part in "Test", so it prints as a fixed part.')).toBeInTheDocument();
    // No "pick one" box for it; the TAP group keeps its own.
    expect(screen.queryByText(/^Test - pick one$/)).toBeNull();
    expect(screen.getByText('TAP - pick one')).toBeInTheDocument();
  });

  it('the group field reads as a choice group, not a name', () => {
    render(<ProductCombosSection productId="prod-host" productCode="SRTKS7061-BL" />);
    expect(screen.getAllByLabelText(GROUP)).toHaveLength(3);
  });
});
