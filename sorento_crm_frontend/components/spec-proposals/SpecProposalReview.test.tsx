/**
 * The proposal review - AC-B.7, AC-B.8.
 *
 * `DataGridTable` DOES mount rows under jsdom, but `DataGrid` calls
 * `useListingColumnPreferences` and renders skeletons until it answers - and under
 * jsdom nothing answers. Mocking it, before the import that pulls `DataGrid` in, is
 * what makes rows and badges assertable (see CLAUDE.md).
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { SpecProposalReview } from './SpecProposalReview';
import { MOCK_PROPOSALS } from './__mocks__/specProposals.fixtures';
import type { SpecProposal } from './types';

function renderReview(overrides: Partial<Parameters<typeof SpecProposalReview>[0]> = {}) {
  const onSelectionChange = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={client}>
      <SpecProposalReview
        proposals={MOCK_PROPOSALS}
        selectedKeys={MOCK_PROPOSALS.filter((row) => row.kind !== 'conflict').map(
          (row) => row.spec_key,
        )}
        onSelectionChange={onSelectionChange}
        {...overrides}
      />
    </QueryClientProvider>,
  );
  return { ...result, onSelectionChange };
}

describe('badge copy (AC-B.7)', () => {
  it('badges a new key exactly "New"', () => {
    renderReview();
    // Two rows are `new` (seat_material, is_rimless) - both badge "New" exactly.
    expect(screen.getAllByText('New')).toHaveLength(2);
  });

  it('badges a change over a machine reading with the exact from/to sentence', () => {
    renderReview();
    // dim_height: stored 750 mm -> proposed 770 mm.
    expect(screen.getByText('Changes 750 mm to 770 mm')).toBeInTheDocument();
  });

  it('badges a conflict with the exact "Conflicts with your value X" sentence', () => {
    renderReview();
    // finish: stored "chrome" (readable as "Chrome").
    expect(screen.getByText('Conflicts with your value Chrome')).toBeInTheDocument();
  });
});

describe('a tombstoned conflict badges its own copy, not a dangling sentence', () => {
  // A tombstone conflict has NO stored value at all - the person removed the spec,
  // they did not set one the flyer now disagrees with. `stored_value: null` here is
  // that removal, not "unknown". Rendered through the generic "Conflicts with your
  // value X" sentence, `readableValue(null, undefined)` returns "" and the badge
  // reads "Conflicts with your value " - a trailing space with nothing after it.
  const TOMBSTONE_CONFLICT: SpecProposal = {
    spec_key: 'has_drainer',
    label: 'Has a drainer board',
    data_type: 'boolean',
    value: true,
    unit: null,
    evidence: 'DRAINER',
    kind: 'conflict',
    stored_value: null,
    stored_unit: null,
    stored_source: 'human',
  };

  it('badges exactly "Conflicts with your removal of this spec"', () => {
    renderReview({ proposals: [TOMBSTONE_CONFLICT], selectedKeys: [] });

    expect(
      screen.getByText('Conflicts with your removal of this spec'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Conflicts with your value')).not.toBeInTheDocument();
    expect(screen.queryByText(/Conflicts with your value\s*$/)).not.toBeInTheDocument();
  });
});

describe('conflicts arrive unticked by default (AC-B.7)', () => {
  it('leaves the conflict row unchecked when the parent seeds selection excluding it', () => {
    renderReview();
    const checkboxes = screen.getAllByLabelText('Select row');
    // MOCK_PROPOSALS order: seat_material (new), dim_height (change), is_rimless (new),
    // finish (conflict) - the last row is the one excluded from selectedKeys.
    expect(checkboxes).toHaveLength(4);
    expect(checkboxes[0]).toHaveAttribute('data-state', 'checked');
    expect(checkboxes[1]).toHaveAttribute('data-state', 'checked');
    expect(checkboxes[2]).toHaveAttribute('data-state', 'checked');
    expect(checkboxes[3]).toHaveAttribute('data-state', 'unchecked');
  });
});

describe('selection callback', () => {
  it('adds the row key when an unticked row is ticked', () => {
    const { onSelectionChange } = renderReview();
    const checkboxes = screen.getAllByLabelText('Select row');
    fireEvent.click(checkboxes[3]); // finish - the conflict row, unticked by default
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.arrayContaining(['seat_material', 'dim_height', 'is_rimless', 'finish']),
    );
  });

  it('removes the row key when a ticked row is unticked', () => {
    const { onSelectionChange } = renderReview();
    const checkboxes = screen.getAllByLabelText('Select row');
    fireEvent.click(checkboxes[0]); // seat_material - ticked by default
    const called = onSelectionChange.mock.calls[0][0] as string[];
    expect(called).not.toContain('seat_material');
    expect(called).toEqual(['dim_height', 'is_rimless']);
  });
});

describe('disabled freezes the checkboxes', () => {
  it('disables every row checkbox and selects none of them', () => {
    renderReview({ disabled: true, selectedKeys: [] });
    const checkboxes = screen.getAllByLabelText('Select row');
    expect(checkboxes.length).toBeGreaterThan(0);
    for (const checkbox of checkboxes) {
      expect(checkbox).toBeDisabled();
    }
  });
});

describe('evidence cell', () => {
  it('carries the full sentence as a title, even when truncated on screen', () => {
    const { container } = renderReview();
    const evidenceCell = container.querySelector(
      '[title="Washdown With Rimless"]',
    ) as HTMLElement | null;
    expect(evidenceCell).not.toBeNull();
    expect(evidenceCell).toHaveTextContent('Washdown With Rimless');
  });
});

describe('a multi-value array proposal reads like the scalar path (second review)', () => {
  // A two-tone finish ("ROSE GOLD + MATT BLACK") is one proposal carrying a LIST
  // (`app/services/product_spec_derivation.py`'s `MULTI_VALUE_KEYS` - see
  // tests/test_product_spec_extract_route.py::test_extract_reports_a_multi_value_
  // finish_as_one_proposal_carrying_the_list on the backend). The type this
  // component is handed must accept that shape - `SpecProposal['value']` currently
  // types as `SpecProposalScalar` (string | number | boolean) only, so this literal
  // does not type-check today; that is red on its own, ahead of any render.
  const MULTI_VALUE_CHANGE: SpecProposal = {
    spec_key: 'finish',
    label: 'Finish or colour',
    data_type: 'enum',
    value: ['matte_black', 'rose_gold'],
    unit: null,
    evidence: 'MATTE BLACK + ROSE GOLD',
    kind: 'change',
    stored_value: 'chrome',
    stored_unit: null,
    stored_source: 'derived',
  };

  it('badges "Changes Chrome to Matte black, Rose gold" - comma+space joined, each element humanised', () => {
    renderReview({ proposals: [MULTI_VALUE_CHANGE], selectedKeys: ['finish'] });

    expect(
      screen.getByText('Changes Chrome to Matte black, Rose gold'),
    ).toBeInTheDocument();
  });

  it('renders the same reading in the value cell', () => {
    const { container } = renderReview({
      proposals: [MULTI_VALUE_CHANGE],
      selectedKeys: ['finish'],
    });

    const valueCell = container.querySelector(
      '[data-spec-proposal-value="finish"]',
    ) as HTMLElement | null;
    expect(valueCell).not.toBeNull();
    expect(valueCell).toHaveTextContent('Matte black, Rose gold');
  });
});

describe('empty proposals', () => {
  it('renders the grid without crashing and shows the empty message', () => {
    const empty: SpecProposal[] = [];
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <SpecProposalReview proposals={empty} selectedKeys={[]} onSelectionChange={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(screen.getByText('Nothing to review.')).toBeInTheDocument();
  });
});

/**
 * The two kinds the flyer batch adds as DATA (AC-D.2, AC-D.8): `unchanged` and
 * `suppressed`. Neither is ever tickable, whatever `selectableKinds` says -
 * there is nothing to write for either, so they are the floor rather than a
 * default (see `NEVER_SELECTABLE` in the component under test).
 */
const UNCHANGED_ROW: SpecProposal = {
  spec_key: 'dim_width',
  label: 'Width',
  data_type: 'numeric',
  value: 800,
  unit: 'mm',
  evidence: 'L1700 x W800 x H590mm',
  kind: 'unchanged',
  stored_value: 800,
  stored_unit: 'mm',
  stored_source: 'derived',
};

const SUPPRESSED_ROW: SpecProposal = {
  spec_key: 'flush_type',
  label: 'Flush type',
  data_type: 'text',
  value: 'dual',
  unit: null,
  evidence: 'Dual Flush 3L / 4.5L',
  kind: 'suppressed',
  stored_value: null,
  stored_unit: null,
  stored_source: 'human',
};

describe('the two new kinds, unchanged and suppressed (AC-D.2, AC-D.8)', () => {
  it('badges an unchanged row "Already stored" and disables its checkbox under the default selectable kinds', () => {
    renderReview({ proposals: [UNCHANGED_ROW], selectedKeys: [] });

    expect(screen.getByText('Already stored')).toBeInTheDocument();
    expect(screen.getByLabelText('Select row')).toBeDisabled();
  });

  it('badges a suppressed row "Removed from this product" and disables its checkbox under the default selectable kinds', () => {
    renderReview({ proposals: [SUPPRESSED_ROW], selectedKeys: [] });

    expect(screen.getByText('Removed from this product')).toBeInTheDocument();
    expect(screen.getByLabelText('Select row')).toBeDisabled();
  });

  it('keeps both rows disabled even when a caller names them in selectableKinds explicitly', () => {
    renderReview({
      proposals: [UNCHANGED_ROW, SUPPRESSED_ROW],
      selectedKeys: [],
      selectableKinds: ['new', 'change', 'conflict', 'unchanged', 'suppressed'],
    });

    const checkboxes = screen.getAllByLabelText('Select row');
    expect(checkboxes).toHaveLength(2);
    for (const checkbox of checkboxes) {
      expect(checkbox).toBeDisabled();
    }
  });
});

describe('conflict tickability is decided by selectableKinds, not by the row (AC-D.2, AC-D.8)', () => {
  it('leaves the conflict checkbox enabled under the default selectable kinds (per-product panel)', () => {
    renderReview();

    // MOCK_PROPOSALS order: seat_material (new), dim_height (change), is_rimless
    // (new), finish (conflict).
    const checkboxes = screen.getAllByLabelText('Select row');
    expect(checkboxes[3]).toBeEnabled();
  });

  it('disables the conflict checkbox when selectableKinds is [new, change] - the flyer bulk apply (AC-D.2, L6/L7)', () => {
    renderReview({ selectableKinds: ['new', 'change'] });

    const checkboxes = screen.getAllByLabelText('Select row');
    expect(checkboxes[3]).toBeDisabled();
  });
});

describe('select-all skips non-selectable rows (AC-D.8)', () => {
  it('ticks only new and change rows, and leaves conflict, unchanged and suppressed alone, when selectableKinds is [new, change]', () => {
    const proposals = [...MOCK_PROPOSALS, UNCHANGED_ROW, SUPPRESSED_ROW];
    const { onSelectionChange } = renderReview({
      proposals,
      selectedKeys: [],
      selectableKinds: ['new', 'change'],
    });

    fireEvent.click(screen.getByLabelText('Select all rows on this page'));

    expect(onSelectionChange).toHaveBeenCalled();
    const called = onSelectionChange.mock.calls[0][0] as string[];
    expect(called).toEqual(
      expect.arrayContaining(['seat_material', 'dim_height', 'is_rimless']),
    );
    expect(called).not.toContain('finish');
    expect(called).not.toContain(UNCHANGED_ROW.spec_key);
    expect(called).not.toContain(SUPPRESSED_ROW.spec_key);
  });

  it('ticks new and conflict rows under the default selectable kinds, but never unchanged or suppressed', () => {
    const proposals = [...MOCK_PROPOSALS, UNCHANGED_ROW, SUPPRESSED_ROW];
    const { onSelectionChange } = renderReview({ proposals, selectedKeys: [] });

    fireEvent.click(screen.getByLabelText('Select all rows on this page'));

    const called = onSelectionChange.mock.calls[0][0] as string[];
    expect(called).toEqual(
      expect.arrayContaining([
        'seat_material',
        'dim_height',
        'is_rimless',
        'finish',
      ]),
    );
    expect(called).not.toContain(UNCHANGED_ROW.spec_key);
    expect(called).not.toContain(SUPPRESSED_ROW.spec_key);
  });
});
