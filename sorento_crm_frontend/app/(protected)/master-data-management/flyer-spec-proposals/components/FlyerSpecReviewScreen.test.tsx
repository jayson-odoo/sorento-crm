/**
 * FlyerSpecReviewScreen - the batch, product by product, and the one control
 * that writes it (AC-D.2, AC-D.3, AC-D.4, AC-D.5, AC-D.8).
 *
 * The HOOKS are mocked (`useFlyerSpecProposalsQuery`, `useProposeFlyerSpecs`,
 * `useApplyFlyerSpecProposals`), not the service - every batch state in the
 * contract is reachable by controlling what those three return, and `apply`'s
 * mock invokes the `onSuccess` callback the screen passes it, the same shape
 * react-query's real mutation gives it.
 *
 * `DataGrid` (inside the real, un-mocked `SpecProposalReview` /
 * `ProductProposalGroup`) calls `useListingColumnPreferences`, which never
 * answers under jsdom - mocked before the import that pulls it in.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const {
  useFlyerSpecProposalsQuery,
  useProposeFlyerSpecs,
  useApplyFlyerSpecProposals,
  hasPermission,
} = vi.hoisted(() => ({
  useFlyerSpecProposalsQuery: vi.fn(),
  useProposeFlyerSpecs: vi.fn(),
  useApplyFlyerSpecProposals: vi.fn(),
  hasPermission: vi.fn(),
}));

vi.mock('../hooks/useFlyerSpecProposals', () => ({
  useFlyerSpecProposalsQuery,
  useProposeFlyerSpecs,
  useApplyFlyerSpecProposals,
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasPermission(slug),
  useHasAnyPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

import type {
  FlyerSpecApplyResult,
  FlyerSpecProductGroup,
  FlyerSpecProposal,
  FlyerSpecProposals,
} from '../services/flyerSpecProposalService';
import { FlyerSpecReviewScreen } from './FlyerSpecReviewScreen';

function proposalRow(overrides: Partial<FlyerSpecProposal>): FlyerSpecProposal {
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

function batch(overrides: Partial<FlyerSpecProposals> = {}): FlyerSpecProposals {
  return {
    id: 'batch-1',
    reading_id: 'r-1',
    filename: 'Sorento Bathroom Collection 2026 A3.pdf',
    status: 'proposed',
    error_message: null,
    product_count: 0,
    proposal_count: 0,
    new_count: 0,
    change_count: 0,
    conflict_count: 0,
    unchanged_count: 0,
    suppressed_count: 0,
    applied_count: 0,
    read_at: '2026-08-16T09:12:00',
    created_at: '2026-08-16T10:02:00',
    finished_at: '2026-08-16T10:02:41',
    applied_at: null,
    created_by_name: 'Aisyah Rahman',
    applied_by_name: null,
    groups: [],
    ...overrides,
  };
}

const MIXED_GROUP: FlyerSpecProductGroup = {
  product_id: 'product-wc-8066',
  product_code: 'SRTWC8066',
  product_name: 'Sorento Wall Hung Water Closet',
  pages: [3],
  proposals: [
    proposalRow({ id: 'p-new', spec_key: 'seat_material', label: 'Seat cover material', kind: 'new' }),
    proposalRow({
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
    proposalRow({
      id: 'p-conflict',
      spec_key: 'finish',
      label: 'Finish or colour',
      kind: 'conflict',
      value: 'matt_black',
      stored_value: 'chrome',
      stored_source: 'human',
    }),
    proposalRow({
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
    proposalRow({
      id: 'p-suppressed',
      spec_key: 'flush_type',
      label: 'Flush type',
      kind: 'suppressed',
      value: 'dual',
      stored_source: 'human',
    }),
  ],
};

const SECOND_GROUP: FlyerSpecProductGroup = {
  product_id: 'product-bt-1700',
  product_code: 'SRTBT1700',
  product_name: 'Sorento Freestanding Bathtub 1700',
  pages: [7, 11],
  proposals: [
    proposalRow({ id: 'p-new-2', spec_key: 'dim_length', label: 'Length', kind: 'new', value: 1700, unit: 'mm' }),
  ],
};

function countedBatch(groups: FlyerSpecProductGroup[]): FlyerSpecProposals {
  const rows = groups.flatMap((g) => g.proposals);
  const of = (kind: string) => rows.filter((r) => r.kind === kind).length;
  return batch({
    groups,
    product_count: groups.length,
    proposal_count: rows.length,
    new_count: of('new'),
    change_count: of('change'),
    conflict_count: of('conflict'),
    unchanged_count: of('unchanged'),
    suppressed_count: of('suppressed'),
  });
}

const propose = { mutate: vi.fn(), isPending: false };
let applyResult: FlyerSpecApplyResult = { applied: [], refused: [] };
const apply = {
  mutate: vi.fn(
    (
      _ids: string[],
      opts?: { onSuccess?: (result: FlyerSpecApplyResult) => void },
    ) => {
      opts?.onSuccess?.(applyResult);
    },
  ),
  isPending: false,
};

function setQuery(overrides: Partial<{
  data: FlyerSpecProposals;
  isLoading: boolean;
  isError: boolean;
  error: Error;
}>) {
  useFlyerSpecProposalsQuery.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  });
}

function renderScreen() {
  return render(<FlyerSpecReviewScreen readingId="r-1" />);
}

beforeEach(() => {
  vi.clearAllMocks();
  hasPermission.mockReturnValue(true);
  propose.mutate = vi.fn();
  propose.isPending = false;
  apply.isPending = false;
  applyResult = { applied: [], refused: [] };
  useProposeFlyerSpecs.mockReturnValue(propose);
  useApplyFlyerSpecProposals.mockReturnValue(apply);
});

describe('FlyerSpecReviewScreen, loading and error (AC-D.5)', () => {
  it('shows a loading skeleton before the batch answers', () => {
    setQuery({ isLoading: true });

    renderScreen();

    expect(screen.getByTestId('fsp-loading')).toBeInTheDocument();
  });

  it('shows the failure and a way back to the list, not a blank screen', () => {
    setQuery({ isError: true, error: new Error('Permission required: dealer_kit.page.view') });

    renderScreen();

    const error = screen.getByTestId('fsp-error');
    expect(error).toHaveTextContent('Permission required: dealer_kit.page.view');
    expect(screen.getByRole('link', { name: 'All flyer proposals' })).toHaveAttribute(
      'href',
      '/master-data-management/flyer-spec-proposals',
    );
  });
});

describe('FlyerSpecReviewScreen, status none (AC-D.5)', () => {
  it('says the flyer has no spec proposals yet, with a Propose specs button', () => {
    setQuery({ data: batch({ status: 'none', id: null }) });

    renderScreen();

    const none = screen.getByTestId('fsp-none');
    expect(none).toHaveTextContent('This flyer has no spec proposals yet');
    expect(screen.getByTestId('fsp-propose')).toHaveTextContent('Propose specs from this flyer');
  });
});

describe('FlyerSpecReviewScreen, status proposing (AC-D.5)', () => {
  it('shows the spinner and no rows', () => {
    setQuery({ data: batch({ status: 'proposing' }) });

    renderScreen();

    expect(screen.getByTestId('fsp-proposing')).toBeInTheDocument();
    expect(screen.queryByTestId('fsp-empty')).toBeNull();
  });
});

describe('FlyerSpecReviewScreen, status failed (AC-D.5)', () => {
  it('shows the error and a Try again action', () => {
    setQuery({
      data: batch({
        status: 'failed',
        error_message: 'The specification rules could not be loaded while reading this flyer',
      }),
    });

    renderScreen();

    const failed = screen.getByTestId('fsp-failed');
    expect(failed).toHaveTextContent(
      'The specification rules could not be loaded while reading this flyer',
    );
    expect(screen.getByTestId('fsp-retry')).toHaveTextContent('Try again');
  });
});

describe('FlyerSpecReviewScreen, proposed with zero rows (AC-D.5)', () => {
  it('says the flyer stated nothing the master does not already hold', () => {
    setQuery({ data: countedBatch([]) });

    renderScreen();

    expect(screen.getByTestId('fsp-empty')).toHaveTextContent(
      'The flyer stated nothing the master does not already hold',
    );
  });
});

describe('FlyerSpecReviewScreen, default selection (AC-D.3)', () => {
  it('ticks exactly the new rows across every product, and nothing else', () => {
    setQuery({ data: countedBatch([MIXED_GROUP, SECOND_GROUP]) });

    renderScreen();

    // seat_material (new) + dim_length (new) = 2. Change/conflict/unchanged/
    // suppressed are not in the default selection.
    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent('2 ticked');

    const newCell = screen.getAllByText('New')[0];
    const newRow = newCell.closest('tr');
    expect(within(newRow as HTMLElement).getByLabelText('Select row')).toBeChecked();

    const changeCell = screen.getByText('Changes 750 mm to 770 mm');
    const changeRow = changeCell.closest('tr');
    expect(within(changeRow as HTMLElement).getByLabelText('Select row')).not.toBeChecked();
  });

  it('disables Apply at zero selection', () => {
    setQuery({ data: countedBatch([]) });

    renderScreen();

    // Zero-row batch renders the empty state instead of the footer; assert
    // through a batch with rows but nothing selectable/selected instead.
    const onlySettled: FlyerSpecProductGroup = {
      ...MIXED_GROUP,
      proposals: MIXED_GROUP.proposals.map((p) => ({ ...p, kind: 'unchanged' as const })),
    };
    setQuery({ data: countedBatch([onlySettled]) });

    renderScreen();

    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent('Nothing ticked');
    expect(screen.getByTestId('fsp-apply')).toBeDisabled();
  });
});

describe('FlyerSpecReviewScreen, the change-confirmation dialog (AC-D.4)', () => {
  it('applies directly, no dialog, when only new rows are ticked', () => {
    setQuery({ data: countedBatch([MIXED_GROUP, SECOND_GROUP]) });

    renderScreen();

    fireEvent.click(screen.getByTestId('fsp-apply'));

    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(apply.mutate).toHaveBeenCalledWith(
      expect.arrayContaining(['p-new', 'p-new-2']),
      expect.anything(),
    );
  });

  it('opens an AlertDialog naming the count when a change row is ticked, and does not apply until confirmed', () => {
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    const changeCell = screen.getByText('Changes 750 mm to 770 mm');
    const changeRow = changeCell.closest('tr') as HTMLElement;
    fireEvent.click(within(changeRow).getByLabelText('Select row'));

    fireEvent.click(screen.getByTestId('fsp-apply'));

    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('Replace 1 master value?');
    expect(apply.mutate).not.toHaveBeenCalled();
  });

  it('applies once the dialog is confirmed', () => {
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    const changeCell = screen.getByText('Changes 750 mm to 770 mm');
    const changeRow = changeCell.closest('tr') as HTMLElement;
    fireEvent.click(within(changeRow).getByLabelText('Select row'));
    fireEvent.click(screen.getByTestId('fsp-apply'));
    fireEvent.click(screen.getByTestId('fsp-confirm'));

    expect(apply.mutate).toHaveBeenCalledWith(
      expect.arrayContaining(['p-new', 'p-change']),
      expect.anything(),
    );
  });
});

describe('FlyerSpecReviewScreen, the result table (AC-D.4)', () => {
  it('lists applied and refused rows with reasons after apply', () => {
    applyResult = {
      applied: [
        { proposal_id: 'p-new', product_code: 'SRTWC8066', spec_key: 'seat_material', value: 'pp' },
      ],
      refused: [
        {
          proposal_id: 'p-conflict',
          product_code: 'SRTWC8066',
          spec_key: 'finish',
          reason: 'conflict_not_confirmed',
          message: 'A person set this value, so a bulk apply will not replace it.',
        },
      ],
    };
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    fireEvent.click(screen.getByTestId('fsp-apply'));

    const result = screen.getByTestId('fsp-result');
    expect(result).toHaveTextContent('1 specification value written to the product master');
    expect(result).toHaveTextContent('SRTWC8066');
    expect(result).toHaveTextContent('1 not written');
    expect(result).toHaveTextContent('A person set this value, so a bulk apply will not replace it.');
  });

  it('says nothing was written when every selected row is refused', () => {
    applyResult = {
      applied: [],
      refused: [
        {
          proposal_id: 'p-new',
          product_code: 'SRTWC8066',
          spec_key: 'seat_material',
          reason: 'already_matches',
          message: 'The product already holds this value',
        },
      ],
    };
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    fireEvent.click(screen.getByTestId('fsp-apply'));

    expect(screen.getByTestId('fsp-result')).toHaveTextContent(
      'Nothing was written to the product master',
    );
  });
});

describe('FlyerSpecReviewScreen, "Show more" keeps selection (AC-D.8)', () => {
  function manyGroups(count: number): FlyerSpecProductGroup[] {
    return Array.from({ length: count }, (_, i) => ({
      product_id: `product-${i}`,
      product_code: `SRT${String(i).padStart(4, '0')}`,
      product_name: `Product ${i}`,
      pages: [i + 1],
      proposals: [
        proposalRow({ id: `p-new-${i}`, spec_key: `key_${i}`, label: `Key ${i}`, kind: 'new' }),
      ],
    }));
  }

  it('reveals the next products without losing the tally of what is ticked', () => {
    setQuery({ data: countedBatch(manyGroups(26)) });

    renderScreen();

    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent('26 ticked');
    expect(screen.queryByText('SRT0025')).toBeNull();

    fireEvent.click(screen.getByTestId('fsp-show-more'));

    expect(screen.getByText('SRT0025')).toBeInTheDocument();
    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent('26 ticked');
  });
});

describe('FlyerSpecReviewScreen, without master_data.products.edit (AC-D.2)', () => {
  it('shows the rows read-only and offers no Apply control', () => {
    hasPermission.mockReturnValue(false);
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    expect(screen.getByTestId('fsp-readonly')).toBeInTheDocument();
    expect(screen.queryByTestId('fsp-apply')).toBeNull();
  });
});

describe('FlyerSpecReviewScreen, a re-propose (AC-A.5, AC-D.3)', () => {
  // A reading has exactly ONE batch row - `flyer_reading_id` is unique and
  // `start_batch` wipes it in place - so a re-propose keeps `id` and replaces
  // every proposal under it. Seeding on the id alone would therefore never
  // re-seed: the screen would hold ids the re-propose deleted, show nothing
  // ticked, offer to apply them anyway, and get them all back `not_in_batch`.
  const SECOND_PASS: FlyerSpecProductGroup = {
    ...MIXED_GROUP,
    proposals: [
      proposalRow({
        id: 'p-new-second-pass',
        spec_key: 'seat_material',
        label: 'Seat cover material',
        kind: 'new',
      }),
      proposalRow({
        id: 'p-change-second-pass',
        spec_key: 'dim_height',
        label: 'Height',
        kind: 'change',
        value: 770,
        unit: 'mm',
        stored_value: 750,
        stored_unit: 'mm',
        stored_source: 'derived',
      }),
    ],
  };

  it('re-seeds the default selection on the new rows, and drops the old result', () => {
    applyResult = {
      applied: [
        { proposal_id: 'p-new', product_code: 'SRTWC8066', spec_key: 'seat_material', value: 'pp' },
      ],
      refused: [],
    };
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    const { rerender } = renderScreen();

    fireEvent.click(screen.getByTestId('fsp-apply'));
    expect(screen.getByTestId('fsp-result')).toBeInTheDocument();

    // Propose again: same batch id, no finish stamp while the pass runs.
    setQuery({
      data: batch({ status: 'proposing', finished_at: null, groups: [] }),
    });
    rerender(<FlyerSpecReviewScreen readingId="r-1" />);
    expect(screen.getByTestId('fsp-proposing')).toBeInTheDocument();

    // The pass settles: same batch row, a later stamp, entirely new proposal ids.
    setQuery({
      data: { ...countedBatch([SECOND_PASS]), finished_at: '2026-08-16T11:41:07' },
    });
    rerender(<FlyerSpecReviewScreen readingId="r-1" />);

    // Exactly the new pass's `new` row, and nothing carried over from the old one.
    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent('1 ticked');
    const newRow = screen.getAllByText('New')[0].closest('tr') as HTMLElement;
    expect(within(newRow).getByLabelText('Select row')).toBeChecked();
    expect(screen.getByTestId('fsp-apply')).toHaveTextContent('Apply 1 selected');

    // The previous apply described rows that no longer exist.
    expect(screen.queryByTestId('fsp-result')).toBeNull();
  });
});
