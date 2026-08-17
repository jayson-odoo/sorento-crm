/**
 * ProductProposalGroup - one product's share of a flyer batch (AC-D.2, AC-D.8).
 *
 * The rows themselves are the real, un-mocked `SpecProposalReview`, so this
 * file exercises the translation between the shared component's `spec_key`
 * selection and the id-keyed selection the flyer batch applies by (L8) - and
 * the per-product select-all, which ticks every TICKABLE row - `new`, `change`
 * and, since the captain's amendment (AC-F.4), `conflict` - and never an
 * `unchanged` or `suppressed` one.
 *
 * `DataGrid` (inside `SpecProposalReview`) calls `useListingColumnPreferences`,
 * which never answers under jsdom - mocked before the import that pulls it in.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

// The add-a-specification dialog asks which keys this product may carry. The
// hook is react-query over `getApplicableSpecKeys`; what this file is about is
// what the group does with the answer, so the answer is set per test.
const { applicableKeysQuery } = vi.hoisted(() => ({ applicableKeysQuery: vi.fn() }));
vi.mock('../hooks/useFlyerSpecProposals', () => ({
  useApplicableSpecKeysQuery: (...args: unknown[]) => applicableKeysQuery(...args),
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
    allowed_values: null,
    origin: 'flyer',
    edited: false,
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
      data_type: 'numeric',
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
      data_type: 'enum',
      allowed_values: ['chrome', 'matt_black'],
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

/** The options of whichever SearchableSelect popover is open, in order. */
function optionLabels(): string[] {
  return screen
    .getAllByRole('option')
    .map((option) => option.textContent?.trim() ?? '');
}

let applicableKeys: { code: string; keys: unknown[] } = { code: '', keys: [] };

beforeEach(() => {
  vi.clearAllMocks();
  applicableKeys = { code: '', keys: [] };
  applicableKeysQuery.mockImplementation(() => ({
    data: applicableKeys,
    isLoading: false,
  }));
});

describe('ProductProposalGroup, per-product select-all (AC-D.2, AC-D.8)', () => {
  it('shows the product identity and select-all summary', () => {
    renderGroup();

    expect(screen.getByText('SRTWC8066')).toBeInTheDocument();
    expect(screen.getByText('Sorento Wall Hung Water Closet')).toBeInTheDocument();
    expect(screen.getByText('p. 3')).toBeInTheDocument();
    // new + change + conflict = 3 tickable rows (AC-F.4). It was 2 before the
    // captain's amendment made a ticked conflict the confirmation.
    expect(screen.getByText('0 of 3 ticked')).toBeInTheDocument();
  });

  it('ticks the new, change AND conflict rows of this product, never unchanged/suppressed (AC-F.4)', () => {
    // AC-F.4, captain amendment 2026-08-17: a `conflict` row is tickable in
    // bulk exactly like a `change`, and the confirm dialog naming how many of
    // them were set by a person is the confirmation. This test asserted a
    // 2-row selection excluding `p-conflict` under the superseded L6/L7 rule.
    const { onSelectionChange } = renderGroup();

    fireEvent.click(
      screen.getByLabelText('Select every applicable row for SRTWC8066'),
    );

    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.arrayContaining(['p-new', 'p-change', 'p-conflict']),
    );
    const called = onSelectionChange.mock.calls[0][0] as string[];
    expect(called).toHaveLength(3);
    expect(called).not.toContain('p-unchanged');
    expect(called).not.toContain('p-suppressed');
  });

  it('unticks every row of this product when select-all is clicked again', () => {
    // All THREE tickable rows, so the box reads fully-ticked and the click
    // clears it. Two of three would be indeterminate, and a click there ticks
    // the third (AC-F.4 added `conflict` to the tickable set).
    const { onSelectionChange } = renderGroup({
      selectedIds: new Set(['p-new', 'p-change', 'p-conflict']),
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

  it('leaves the conflict checkbox ENABLED and the unchanged one disabled, matching the select-all rule (AC-F.4)', () => {
    // Was "restricts the row checkboxes to new + change": the conflict row is
    // tickable since the captain's amendment (AC-F.4), and `unchanged` is now
    // the row this asserts is refused.
    renderGroup();

    const conflictCell = screen.getByText('Conflicts with your value Chrome');
    const conflictRow = conflictCell.closest('tr');
    expect(conflictRow).not.toBeNull();
    expect(within(conflictRow as HTMLElement).getByLabelText('Select row')).toBeEnabled();

    const unchangedCell = screen.getByText('Already stored');
    const unchangedRow = unchangedCell.closest('tr');
    expect(unchangedRow).not.toBeNull();
    expect(
      within(unchangedRow as HTMLElement).getByLabelText('Select row'),
    ).toBeDisabled();

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

describe('ProductProposalGroup, correcting a value in place (AC-F.3)', () => {
  it('offers the pencil on a pending new/change/conflict row and not on unchanged or suppressed', () => {
    renderGroup({ onEditValue: vi.fn() });

    expect(screen.getByLabelText('Edit Seat cover material')).toBeInTheDocument();
    expect(screen.getByLabelText('Edit Height')).toBeInTheDocument();
    expect(screen.getByLabelText('Edit Finish or colour')).toBeInTheDocument();
    expect(screen.queryByLabelText('Edit Width')).toBeNull();
    expect(screen.queryByLabelText('Edit Flush type')).toBeNull();
  });

  it('offers no in-place edit for a multi-value proposal, and says where it is edited', () => {
    const multi: FlyerSpecProductGroup = {
      ...GROUP,
      proposals: [
        row({
          id: 'p-multi',
          spec_key: 'finish',
          label: 'Finish or colour',
          data_type: 'enum',
          kind: 'change',
          value: ['rose_gold', 'matt_black'],
          allowed_values: ['rose_gold', 'matt_black', 'chrome'],
          stored_value: 'chrome',
          stored_source: 'derived',
        }),
        row({
          id: 'p-one-value-list',
          spec_key: 'seat_material',
          label: 'Seat cover material',
          value: ['duroplast'],
        }),
      ],
    };

    render(
      <ProductProposalGroup
        group={multi}
        selectedIds={new Set()}
        onSelectionChange={vi.fn()}
        onEditValue={vi.fn()}
      />,
    );

    // The editor holds ONE value, so opening it on a list of two would save the
    // first and lose the second.
    const pencil = screen.getByLabelText('Edit Finish or colour');
    expect(pencil).toBeDisabled();
    expect(
      screen.getByTitle(
        'Multi-value specifications are edited on the product page',
      ),
    ).toBeInTheDocument();

    fireEvent.click(pencil);
    expect(screen.queryByLabelText('Save Finish or colour')).toBeNull();

    // A list of one loses nothing, so it edits here like any other value.
    expect(screen.getByLabelText('Edit Seat cover material')).toBeEnabled();
  });

  it('offers no pencil at all when the caller passes no edit handler', () => {
    renderGroup();

    expect(screen.queryByLabelText('Edit Seat cover material')).toBeNull();
  });

  it('swaps a closed-vocabulary row to a dropdown of exactly the allowed values', () => {
    const withVocabulary: FlyerSpecProductGroup = {
      ...GROUP,
      proposals: [
        row({
          id: 'p-enum',
          spec_key: 'trap_type',
          label: 'Trap type',
          data_type: 'enum',
          value: 's_trap',
          allowed_values: ['s_trap', 'p_trap'],
        }),
      ],
    };

    render(
      <ProductProposalGroup
        group={withVocabulary}
        selectedIds={new Set()}
        onSelectionChange={vi.fn()}
        onEditValue={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText('Edit Trap type'));

    fireEvent.click(
      document.querySelector('[data-slot="searchable-select-trigger"]')!,
    );
    // Exactly the registry's vocabulary, and nothing else to type into.
    expect(optionLabels()).toEqual(['S trap', 'P trap']);
  });

  it('swaps a numeric row to a number input carrying the registry unit, and saves the parsed number', async () => {
    const onEditValue = vi.fn().mockResolvedValue(undefined);
    renderGroup({ onEditValue });

    fireEvent.click(screen.getByLabelText('Edit Height'));

    const input = screen.getByLabelText('Height') as HTMLInputElement;
    expect(input).toHaveAttribute('type', 'number');
    expect(input.value).toBe('770');
    // The unit belongs to the key and is never typed into the value.
    expect(screen.getByText('mm')).toBeInTheDocument();

    fireEvent.change(input, { target: { value: '780' } });
    fireEvent.click(screen.getByLabelText('Save Height'));

    await waitFor(() =>
      expect(onEditValue).toHaveBeenCalledWith('p-change', 780),
    );
  });

  it('swaps a boolean row to a Yes/No select', () => {
    const withBoolean: FlyerSpecProductGroup = {
      ...GROUP,
      proposals: [
        row({
          id: 'p-bool',
          spec_key: 'is_rimless',
          label: 'Rimless',
          data_type: 'boolean',
          value: true,
        }),
      ],
    };

    render(
      <ProductProposalGroup
        group={withBoolean}
        selectedIds={new Set()}
        onSelectionChange={vi.fn()}
        onEditValue={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText('Edit Rimless'));
    fireEvent.click(
      document.querySelector('[data-slot="searchable-select-trigger"]')!,
    );

    expect(optionLabels()).toEqual(['Yes', 'No']);
  });

  it('swaps a free-text row to a text input and restores the read value on cancel', () => {
    const onEditValue = vi.fn();
    renderGroup({ onEditValue });

    fireEvent.click(screen.getByLabelText('Edit Seat cover material'));
    const input = screen.getByLabelText('Seat cover material') as HTMLInputElement;
    expect(input).toHaveAttribute('type', 'text');

    fireEvent.change(input, { target: { value: 'uf' } });
    fireEvent.click(screen.getByLabelText('Cancel editing Seat cover material'));

    expect(screen.queryByLabelText('Seat cover material')).toBeNull();
    expect(onEditValue).not.toHaveBeenCalled();
  });

  it('marks a row the server says was edited', () => {
    const edited: FlyerSpecProductGroup = {
      ...GROUP,
      proposals: [row({ id: 'p-edited', spec_key: 'seat_material', label: 'Seat cover material', edited: true })],
    };

    render(
      <ProductProposalGroup
        group={edited}
        selectedIds={new Set()}
        onSelectionChange={vi.fn()}
      />,
    );

    expect(screen.getByText('edited')).toBeInTheDocument();
  });
});

describe('ProductProposalGroup, dismissing a row (AC-G.4)', () => {
  it('asks before dismissing, in the contract copy, and does not call until confirmed', () => {
    const onDismiss = vi.fn().mockResolvedValue(undefined);
    renderGroup({ onDismiss });

    fireEvent.click(screen.getByLabelText('Dismiss Seat cover material'));

    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('Dismiss this proposal?');
    expect(dialog).toHaveTextContent('It will not be applied.');
    expect(onDismiss).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('fsp-dismiss-confirm'));

    expect(onDismiss).toHaveBeenCalledWith('p-new');
  });

  it('offers Dismiss on an unchanged row too - there is nothing to write, but there is a row to remove', () => {
    renderGroup({ onDismiss: vi.fn() });

    expect(screen.getByLabelText('Dismiss Width')).toBeInTheDocument();
  });

  it('offers no Dismiss at all when the caller passes no handler', () => {
    renderGroup();

    expect(screen.queryByLabelText('Dismiss Seat cover material')).toBeNull();
  });
});

describe('ProductProposalGroup, adding a specification (AC-G.4)', () => {
  it('offers "Add specification" only when the caller can add, and posts the picked key and value', async () => {
    applicableKeys = {
      code: 'SRTWC8066',
      keys: [
        {
          spec_key: 'flush_volume',
          label: 'Flush volume',
          data_type: 'numeric',
          unit: 'l',
          allowed_values: [],
          synonyms: {},
          applicable: true,
          held: false,
        },
        // Already proposed for this product, so the picker must not offer it.
        {
          spec_key: 'seat_material',
          label: 'Seat cover material',
          data_type: 'text',
          unit: null,
          allowed_values: [],
          synonyms: {},
          applicable: true,
          held: false,
        },
      ],
    };
    const onAddRow = vi.fn().mockResolvedValue(undefined);
    renderGroup({ onAddRow });

    fireEvent.click(screen.getByText('Add specification'));

    const dialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(dialog).getByRole('combobox', { name: /specification/i }),
    );
    // `seat_material` is already a row in this group, so a second row for it
    // would be refused server-side - the picker must not offer it (AC-G.4).
    expect(optionLabels()).toEqual(['Flush volume']);
    fireEvent.click(screen.getByText('Flush volume'));

    const value = within(dialog).getByLabelText('Flush volume');
    fireEvent.change(value, { target: { value: '4.5' } });
    fireEvent.click(screen.getByTestId('fsp-add-row-submit'));

    await waitFor(() =>
      expect(onAddRow).toHaveBeenCalledWith({
        spec_key: 'flush_volume',
        value: 4.5,
      }),
    );
  });

  it('offers nothing when the caller passes no add handler', () => {
    renderGroup();

    expect(screen.queryByText('Add specification')).toBeNull();
  });
});
