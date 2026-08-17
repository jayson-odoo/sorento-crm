/**
 * ProductProposalGroup - one product's share of a flyer batch (AC-D.2, AC-D.8).
 *
 * The rows themselves are the real, un-mocked `SpecProposalReview`, so this
 * file exercises the translation between the shared component's `spec_key`
 * selection and the id-keyed selection the flyer batch applies by (L8) - and
 * the per-product select-all, which ticks only `new` + `change`, never a
 * `conflict`, `unchanged` or `suppressed` row.
 *
 * `DataGrid` (inside `SpecProposalReview`) calls `useListingColumnPreferences`,
 * which never answers under jsdom - mocked before the import that pulls it in.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { ProductProposalGroup } from './ProductProposalGroup';
import type { FlyerSpecProductGroup, FlyerSpecProposal } from '../services/flyerSpecProposalService';

function row(overrides: Partial<FlyerSpecProposal>): FlyerSpecProposal {
  return {
    id: 'proposal-x',
    spec_key: 'x',
    label: 'X',
    data_type: 'text',
    value: 'v',
    unit: null,
    evidence: 'V',
    kind: 'new',
    stored_value: null,
    stored_unit: null,
    stored_source: null,
    outcome: null,
    applied_at: null,
    ...overrides,
  };
}

const GROUP: FlyerSpecProductGroup = {
  product_id: 'product-wc-8066',
  product_code: 'SRTWC8066',
  product_name: 'Sorento Wall Hung Water Closet',
  pages: [3],
  proposals: [
    row({ id: 'p-new', spec_key: 'seat_material', label: 'Seat cover material', kind: 'new' }),
    row({
      id: 'p-change',
      spec_key: 'dim_height',
      label: 'Height',
      kind: 'change',
      value: 770,
      unit: 'mm',
      stored_value: 750,
      stored_unit: 'mm',
      stored_source: 'derived',
    }),
    row({
      id: 'p-conflict',
      spec_key: 'finish',
      label: 'Finish or colour',
      kind: 'conflict',
      value: 'matt_black',
      stored_value: 'chrome',
      stored_source: 'human',
    }),
    row({
      id: 'p-unchanged',
      spec_key: 'dim_width',
      label: 'Width',
      kind: 'unchanged',
      value: 800,
      unit: 'mm',
      stored_value: 800,
      stored_unit: 'mm',
      stored_source: 'derived',
    }),
    row({
      id: 'p-suppressed',
      spec_key: 'flush_type',
      label: 'Flush type',
      kind: 'suppressed',
      value: 'dual',
      stored_source: 'human',
    }),
  ],
};

function renderGroup(overrides: Partial<Parameters<typeof ProductProposalGroup>[0]> = {}) {
  const onSelectionChange = vi.fn();
  const result = render(
    <ProductProposalGroup
      group={GROUP}
      selectedIds={new Set()}
      onSelectionChange={onSelectionChange}
      {...overrides}
    />,
  );
  return { ...result, onSelectionChange };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ProductProposalGroup, per-product select-all (AC-D.2, AC-D.8)', () => {
  it('shows the product identity and select-all summary', () => {
    renderGroup();

    expect(screen.getByText('SRTWC8066')).toBeInTheDocument();
    expect(screen.getByText('Sorento Wall Hung Water Closet')).toBeInTheDocument();
    expect(screen.getByText('p. 3')).toBeInTheDocument();
    expect(screen.getByText('0 of 2 ticked')).toBeInTheDocument();
  });

  it('ticks only the new and change rows of this product, never conflict/unchanged/suppressed', () => {
    const { onSelectionChange } = renderGroup();

    fireEvent.click(
      screen.getByLabelText('Select every applicable row for SRTWC8066'),
    );

    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.arrayContaining(['p-new', 'p-change']),
    );
    const called = onSelectionChange.mock.calls[0][0] as string[];
    expect(called).toHaveLength(2);
    expect(called).not.toContain('p-conflict');
    expect(called).not.toContain('p-unchanged');
    expect(called).not.toContain('p-suppressed');
  });

  it('unticks every row of this product when select-all is clicked again', () => {
    const { onSelectionChange } = renderGroup({
      selectedIds: new Set(['p-new', 'p-change']),
    });

    fireEvent.click(
      screen.getByLabelText('Select every applicable row for SRTWC8066'),
    );

    expect(onSelectionChange).toHaveBeenCalledWith([]);
  });

  it('offers no select-all when this product has nothing selectable pending', () => {
    const settledOnly: FlyerSpecProductGroup = {
      ...GROUP,
      proposals: GROUP.proposals.map((p) => ({ ...p, outcome: 'applied', applied_at: 'x' })),
    };

    render(
      <ProductProposalGroup
        group={settledOnly}
        selectedIds={new Set()}
        onSelectionChange={vi.fn()}
      />,
    );

    expect(
      screen.queryByLabelText('Select every applicable row for SRTWC8066'),
    ).toBeNull();
  });
});

describe('ProductProposalGroup, rows delegate to the shared review (AC-D.2)', () => {
  it('renders the pending rows through SpecProposalReview, including the new kinds', () => {
    renderGroup();

    expect(screen.getByText('New')).toBeInTheDocument();
    expect(screen.getByText('Changes 750 mm to 770 mm')).toBeInTheDocument();
    expect(screen.getByText('Conflicts with your value Chrome')).toBeInTheDocument();
    expect(screen.getByText('Already stored')).toBeInTheDocument();
    expect(screen.getByText('Removed from this product')).toBeInTheDocument();
  });

  it('restricts the row checkboxes to new + change, matching the select-all rule', () => {
    renderGroup();

    const conflictCell = screen.getByText('Conflicts with your value Chrome');
    const conflictRow = conflictCell.closest('tr');
    expect(conflictRow).not.toBeNull();
    expect(within(conflictRow as HTMLElement).getByLabelText('Select row')).toBeDisabled();

    const newCell = screen.getByText('New');
    const newRow = newCell.closest('tr');
    expect(newRow).not.toBeNull();
    expect(within(newRow as HTMLElement).getByLabelText('Select row')).toBeEnabled();
  });
});

describe('ProductProposalGroup, settled rows are read-only (AC-D.4, AC-D.8)', () => {
  it('moves an applied row out of the table and into the "Already decided" list', () => {
    const withApplied: FlyerSpecProductGroup = {
      ...GROUP,
      proposals: [
        ...GROUP.proposals,
        row({
          id: 'p-settled',
          spec_key: 'material',
          label: 'Material',
          kind: 'new',
          value: 'acrylic',
          outcome: 'applied',
          applied_at: '2026-08-17T09:00:00',
        }),
      ],
    };

    render(
      <ProductProposalGroup
        group={withApplied}
        selectedIds={new Set()}
        onSelectionChange={vi.fn()}
      />,
    );

    const settled = screen.getByText('Already decided').closest('div');
    expect(settled).not.toBeNull();
    expect(within(settled as HTMLElement).getByText('Material')).toBeInTheDocument();
    expect(within(settled as HTMLElement).getByText('Applied')).toBeInTheDocument();
    // A settled row is not a table row any more - there is no checkbox for it.
    // The base GROUP has 5 still-pending rows; the added settled row adds none.
    expect(screen.queryAllByLabelText('Select row')).toHaveLength(5);
  });

  it('says every row for this product has been through an apply when nothing is pending', () => {
    const settledOnly: FlyerSpecProductGroup = {
      ...GROUP,
      proposals: GROUP.proposals.map((p) => ({ ...p, outcome: 'applied', applied_at: 'x' })),
    };

    render(
      <ProductProposalGroup
        group={settledOnly}
        selectedIds={new Set()}
        onSelectionChange={vi.fn()}
      />,
    );

    expect(
      screen.getByText(
        'Every row this flyer proposed for this product has been through an apply.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryAllByLabelText('Select row')).toHaveLength(0);
  });
});
