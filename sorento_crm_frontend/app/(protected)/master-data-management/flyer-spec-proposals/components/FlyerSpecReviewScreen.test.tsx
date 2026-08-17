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
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

const {
  useFlyerSpecProposalsQuery,
  useProposeFlyerSpecs,
  useApplyFlyerSpecProposals,
  useEditFlyerSpecProposal,
  useAddFlyerSpecProposalRow,
  useDismissFlyerSpecProposal,
  useApplicableSpecKeysQuery,
  hasPermission,
  permissionsLoading,
} = vi.hoisted(() => ({
  useFlyerSpecProposalsQuery: vi.fn(),
  useProposeFlyerSpecs: vi.fn(),
  useApplyFlyerSpecProposals: vi.fn(),
  useEditFlyerSpecProposal: vi.fn(),
  useAddFlyerSpecProposalRow: vi.fn(),
  useDismissFlyerSpecProposal: vi.fn(),
  useApplicableSpecKeysQuery: vi.fn(),
  hasPermission: vi.fn(),
  permissionsLoading: { value: false },
}));

vi.mock('../hooks/useFlyerSpecProposals', () => ({
  useFlyerSpecProposalsQuery,
  useProposeFlyerSpecs,
  useApplyFlyerSpecProposals,
  useEditFlyerSpecProposal,
  useAddFlyerSpecProposalRow,
  useDismissFlyerSpecProposal,
  useApplicableSpecKeysQuery,
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasPermission(slug),
  useHasAnyPermission: () => true,
  usePermissions: () => ({
    permissions: [],
    permissionSet: new Set(),
    isLoading: permissionsLoading.value,
  }),
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
    allowed_values: null,
    origin: 'flyer',
    edited: false,
    outcome: null,
    applied_at: null,
    ...overrides,
  };
}

function batch(
  overrides: Partial<FlyerSpecProposals> = {},
): FlyerSpecProposals {
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
    proposalRow({
      id: 'p-new',
      spec_key: 'seat_material',
      label: 'Seat cover material',
      kind: 'new',
    }),
    proposalRow({
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
    proposalRow({
      id: 'p-new-2',
      spec_key: 'dim_length',
      label: 'Length',
      kind: 'new',
      value: 1700,
      unit: 'mm',
    }),
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
const editValue = { mutateAsync: vi.fn(), isPending: false };
const addRow = { mutateAsync: vi.fn(), isPending: false };
const dismiss = { mutateAsync: vi.fn(), isPending: false };
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

function setQuery(
  overrides: Partial<{
    data: FlyerSpecProposals;
    isLoading: boolean;
    isError: boolean;
    error: Error;
  }>,
) {
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
  permissionsLoading.value = false;
  propose.mutate = vi.fn();
  propose.isPending = false;
  apply.isPending = false;
  applyResult = { applied: [], refused: [] };
  useProposeFlyerSpecs.mockReturnValue(propose);
  useApplyFlyerSpecProposals.mockReturnValue(apply);
  editValue.mutateAsync = vi.fn().mockResolvedValue(undefined);
  addRow.mutateAsync = vi.fn().mockResolvedValue(undefined);
  dismiss.mutateAsync = vi.fn().mockResolvedValue(undefined);
  useEditFlyerSpecProposal.mockReturnValue(editValue);
  useAddFlyerSpecProposalRow.mockReturnValue(addRow);
  useDismissFlyerSpecProposal.mockReturnValue(dismiss);
  useApplicableSpecKeysQuery.mockReturnValue({
    data: { code: '', keys: [] },
    isLoading: false,
  });
});

describe('FlyerSpecReviewScreen, loading and error (AC-D.5)', () => {
  it('shows a loading skeleton before the batch answers', () => {
    setQuery({ isLoading: true });

    renderScreen();

    expect(screen.getByTestId('fsp-loading')).toBeInTheDocument();
  });

  it('shows the failure and a way back to the list, not a blank screen', () => {
    setQuery({
      isError: true,
      error: new Error('Permission required: dealer_kit.page.view'),
    });

    renderScreen();

    const error = screen.getByTestId('fsp-error');
    expect(error).toHaveTextContent(
      'Permission required: dealer_kit.page.view',
    );
    expect(
      screen.getByRole('link', { name: 'All flyer proposals' }),
    ).toHaveAttribute('href', '/master-data-management/flyer-spec-proposals');
  });
});

describe('FlyerSpecReviewScreen, status none (AC-D.5)', () => {
  it('says the flyer has no spec proposals yet, with a Propose specs button', () => {
    setQuery({ data: batch({ status: 'none', id: null }) });

    renderScreen();

    const none = screen.getByTestId('fsp-none');
    expect(none).toHaveTextContent('This flyer has no spec proposals yet');
    expect(screen.getByTestId('fsp-propose')).toHaveTextContent(
      'Propose specs from this flyer',
    );
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
        error_message:
          'The specification rules could not be loaded while reading this flyer',
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

    // seat_material (new) + dim_length (new) = 2. Change and conflict are
    // tickable (AC-F.4) but never ticked by default; unchanged and suppressed
    // are neither.
    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '2 ticked',
    );

    const newCell = screen.getAllByText('New')[0];
    const newRow = newCell.closest('tr');
    expect(
      within(newRow as HTMLElement).getByLabelText('Select row'),
    ).toBeChecked();

    const changeCell = screen.getByText('Changes 750 mm to 770 mm');
    const changeRow = changeCell.closest('tr');
    expect(
      within(changeRow as HTMLElement).getByLabelText('Select row'),
    ).not.toBeChecked();
  });

  it('disables Apply at zero selection', () => {
    setQuery({ data: countedBatch([]) });

    renderScreen();

    // Zero-row batch renders the empty state instead of the footer; assert
    // through a batch with rows but nothing selectable/selected instead.
    const onlySettled: FlyerSpecProductGroup = {
      ...MIXED_GROUP,
      proposals: MIXED_GROUP.proposals.map((p) => ({
        ...p,
        kind: 'unchanged' as const,
      })),
    };
    setQuery({ data: countedBatch([onlySettled]) });

    renderScreen();

    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      'Nothing ticked',
    );
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

  it('names BOTH counts when a conflict is ticked - K replaced, D of them set by a person (AC-F.4)', () => {
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    const changeRow = screen
      .getByText('Changes 750 mm to 770 mm')
      .closest('tr') as HTMLElement;
    fireEvent.click(within(changeRow).getByLabelText('Select row'));
    const conflictRow = screen
      .getByText('Conflicts with your value Chrome')
      .closest('tr') as HTMLElement;
    fireEvent.click(within(conflictRow).getByLabelText('Select row'));

    fireEvent.click(screen.getByTestId('fsp-apply'));

    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent(
      'Replace 2 master values, 1 of them set by a person?',
    );
  });

  it('applies the ticked conflict once confirmed - a tick IS the confirmation (AC-F.1, AC-F.4)', () => {
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    const conflictRow = screen
      .getByText('Conflicts with your value Chrome')
      .closest('tr') as HTMLElement;
    fireEvent.click(within(conflictRow).getByLabelText('Select row'));
    fireEvent.click(screen.getByTestId('fsp-apply'));
    fireEvent.click(screen.getByTestId('fsp-confirm'));

    expect(apply.mutate).toHaveBeenCalledWith(
      expect.arrayContaining(['p-new', 'p-conflict']),
      expect.anything(),
    );
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
        {
          proposal_id: 'p-new',
          product_code: 'SRTWC8066',
          spec_key: 'seat_material',
          value: 'pp',
        },
      ],
      refused: [
        {
          proposal_id: 'p-conflict',
          product_code: 'SRTWC8066',
          spec_key: 'finish',
          reason: 'conflict_not_confirmed',
          message:
            'A person set this value, so a bulk apply will not replace it.',
        },
      ],
    };
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    fireEvent.click(screen.getByTestId('fsp-apply'));

    const result = screen.getByTestId('fsp-result');
    expect(result).toHaveTextContent(
      '1 specification value written to the product master',
    );
    expect(result).toHaveTextContent('SRTWC8066');
    expect(result).toHaveTextContent('1 not written');
    expect(result).toHaveTextContent(
      'A person set this value, so a bulk apply will not replace it.',
    );
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
        proposalRow({
          id: `p-new-${i}`,
          spec_key: `key_${i}`,
          label: `Key ${i}`,
          kind: 'new',
        }),
      ],
    }));
  }

  it('reveals the next products without losing the tally of what is ticked', () => {
    setQuery({ data: countedBatch(manyGroups(26)) });

    renderScreen();

    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '26 ticked',
    );
    expect(screen.queryByText('SRT0025')).toBeNull();

    fireEvent.click(screen.getByTestId('fsp-show-more'));

    expect(screen.getByText('SRT0025')).toBeInTheDocument();
    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '26 ticked',
    );
  });
});

describe('FlyerSpecReviewScreen, without master_data.products.edit (AC-D.2)', () => {
  it('does not ask for the batch, says the permission is missing, and offers no Apply control', () => {
    // The route refuses without the product-master permission, so the query
    // is withheld and the screen says why - it does not fire a request that can
    // only come back 403 and then show the server's refusal.
    hasPermission.mockReturnValue(false);
    setQuery({});

    renderScreen();

    expect(useFlyerSpecProposalsQuery).toHaveBeenCalledWith('r-1', {
      enabled: false,
    });
    expect(screen.getByTestId('fsp-readonly')).toBeInTheDocument();
    expect(screen.queryByTestId('fsp-loading')).toBeNull();
    expect(screen.queryByTestId('fsp-apply')).toBeNull();
    expect(
      screen.getByRole('link', { name: 'All flyer proposals' }),
    ).toHaveAttribute('href', '/master-data-management/flyer-spec-proposals');
  });

  it('shows the loading skeleton, not the refusal, while the permissions are still being fetched', () => {
    // `useHasPermission` answers false until the permissions query settles.
    // That is "not known yet", and the screen must not tell a permitted user
    // their role is wanting for the length of a round trip.
    permissionsLoading.value = true;
    hasPermission.mockReturnValue(false);
    setQuery({});

    renderScreen();

    expect(screen.getByTestId('fsp-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('fsp-readonly')).toBeNull();
    expect(useFlyerSpecProposalsQuery).toHaveBeenCalledWith('r-1', {
      enabled: false,
    });
  });

  it('asks for the batch for somebody who holds it', () => {
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    expect(useFlyerSpecProposalsQuery).toHaveBeenCalledWith('r-1', {
      enabled: true,
    });
  });
});

describe('FlyerSpecReviewScreen, a tick on a row the batch no longer lets anybody tick', () => {
  it('drops a ticked change row from the selection once an edit turns it unchanged', () => {
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    const { rerender } = renderScreen();

    const changeRow = screen
      .getByText('Changes 750 mm to 770 mm')
      .closest('tr') as HTMLElement;
    fireEvent.click(within(changeRow).getByLabelText('Select row'));
    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '2 ticked, 1 replacing a value the master holds',
    );

    // The refetch after a PATCH: the same batch, the row now `unchanged`.
    const edited: FlyerSpecProductGroup = {
      ...MIXED_GROUP,
      proposals: MIXED_GROUP.proposals.map((row) =>
        row.id === 'p-change'
          ? { ...row, kind: 'unchanged' as const, value: 750, edited: true }
          : row,
      ),
    };
    setQuery({ data: countedBatch([edited]) });
    rerender(<FlyerSpecReviewScreen readingId="r-1" />);

    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '1 ticked',
    );
    expect(screen.getByTestId('fsp-selection-count')).not.toHaveTextContent(
      'replacing',
    );

    fireEvent.click(screen.getByTestId('fsp-apply'));
    expect(apply.mutate).toHaveBeenCalledWith(['p-new'], expect.anything());
  });

  it('drops a ticked row the batch no longer holds', () => {
    setQuery({ data: countedBatch([MIXED_GROUP, SECOND_GROUP]) });

    const { rerender } = renderScreen();

    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '2 ticked',
    );

    setQuery({ data: countedBatch([MIXED_GROUP]) });
    rerender(<FlyerSpecReviewScreen readingId="r-1" />);

    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '1 ticked',
    );
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
        {
          proposal_id: 'p-new',
          product_code: 'SRTWC8066',
          spec_key: 'seat_material',
          value: 'pp',
        },
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
      data: {
        ...countedBatch([SECOND_PASS]),
        finished_at: '2026-08-16T11:41:07',
      },
    });
    rerender(<FlyerSpecReviewScreen readingId="r-1" />);

    // Exactly the new pass's `new` row, and nothing carried over from the old one.
    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '1 ticked',
    );
    const newRow = screen.getAllByText('New')[0].closest('tr') as HTMLElement;
    expect(within(newRow).getByLabelText('Select row')).toBeChecked();
    expect(screen.getByTestId('fsp-apply')).toHaveTextContent(
      'Apply 1 selected',
    );

    // The previous apply described rows that no longer exist.
    expect(screen.queryByTestId('fsp-result')).toBeNull();
  });
});

describe('FlyerSpecReviewScreen, the search box (AC-G.5)', () => {
  it('offers no search when the batch holds a single product', () => {
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    expect(screen.queryByTestId('fsp-search')).toBeNull();
  });

  it('filters the product groups by code, by name and by specification label', () => {
    setQuery({ data: countedBatch([MIXED_GROUP, SECOND_GROUP]) });

    renderScreen();

    const search = screen.getByTestId('fsp-search');

    fireEvent.change(search, { target: { value: 'SRTBT' } });
    expect(screen.queryByText('SRTWC8066')).toBeNull();
    expect(screen.getByText('SRTBT1700')).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'wall hung' } });
    expect(screen.getByText('SRTWC8066')).toBeInTheDocument();
    expect(screen.queryByText('SRTBT1700')).toBeNull();

    // The specification label, which is the third thing a reviewer knows about
    // the row they are hunting for.
    fireEvent.change(search, { target: { value: 'Length' } });
    expect(screen.getByText('SRTBT1700')).toBeInTheDocument();
    expect(screen.queryByText('SRTWC8066')).toBeNull();
  });

  it('keeps the selection of hidden rows intact, and applies them (AC-G.5)', () => {
    setQuery({ data: countedBatch([MIXED_GROUP, SECOND_GROUP]) });

    renderScreen();

    // Both `new` rows are ticked by default, one per product.
    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '2 ticked',
    );

    fireEvent.change(screen.getByTestId('fsp-search'), {
      target: { value: 'SRTBT' },
    });

    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '2 ticked',
    );

    fireEvent.click(screen.getByTestId('fsp-apply'));

    expect(apply.mutate).toHaveBeenCalledWith(
      expect.arrayContaining(['p-new', 'p-new-2']),
      expect.anything(),
    );
  });

  it('says so when nothing matches, and says the ticks are still ticked', () => {
    setQuery({ data: countedBatch([MIXED_GROUP, SECOND_GROUP]) });

    renderScreen();

    fireEvent.change(screen.getByTestId('fsp-search'), {
      target: { value: 'zzz-nothing' },
    });

    expect(screen.getByTestId('fsp-search-empty')).toHaveTextContent(
      'Ticked rows are still ticked',
    );
  });

  it('forgets the search once the batch is down to one product, so the last product is not hidden behind a box that is gone', () => {
    setQuery({ data: countedBatch([MIXED_GROUP, SECOND_GROUP]) });

    const { rerender } = renderScreen();

    fireEvent.change(screen.getByTestId('fsp-search'), {
      target: { value: 'zzz-nothing' },
    });
    expect(screen.getByTestId('fsp-search-empty')).toBeInTheDocument();

    // Every row of the second product dismissed: the refetch answers one group.
    setQuery({ data: countedBatch([MIXED_GROUP]) });
    rerender(<FlyerSpecReviewScreen readingId="r-1" />);

    expect(screen.queryByTestId('fsp-search')).toBeNull();
    expect(screen.queryByTestId('fsp-search-empty')).toBeNull();
    expect(screen.getByText('SRTWC8066')).toBeInTheDocument();
  });
});

describe('FlyerSpecReviewScreen, clearing the search (AC-G.5)', () => {
  function pagedGroups(count: number): FlyerSpecProductGroup[] {
    return Array.from({ length: count }, (_, i) => ({
      product_id: `paged-${i}`,
      product_code: `SRTP${String(i).padStart(4, '0')}`,
      product_name: `Paged product ${i}`,
      pages: [i + 1],
      proposals: [
        proposalRow({
          id: `paged-new-${i}`,
          spec_key: `paged_key_${i}`,
          label: `Paged key ${i}`,
          kind: 'new',
        }),
      ],
    }));
  }

  function shownProductCodes(): string[] {
    return Array.from(
      document.querySelectorAll('[data-flyer-spec-product]'),
    ).map((node) => node.getAttribute('data-flyer-spec-product') ?? '');
  }

  it('restores the full first page and the Show more button', () => {
    setQuery({ data: countedBatch(pagedGroups(34)) });

    renderScreen();

    expect(shownProductCodes()).toHaveLength(25);
    expect(screen.getByTestId('fsp-show-more')).toHaveTextContent('9 left');

    fireEvent.change(screen.getByTestId('fsp-search'), {
      target: { value: 'SRTP0003' },
    });

    expect(shownProductCodes()).toEqual(['SRTP0003']);
    expect(screen.queryByTestId('fsp-show-more')).toBeNull();

    fireEvent.change(screen.getByTestId('fsp-search'), {
      target: { value: '' },
    });

    expect(shownProductCodes()).toHaveLength(25);
    expect(screen.getByTestId('fsp-show-more')).toHaveTextContent('9 left');
  });

  it('pages the restored list from the top, not from the filtered page depth', () => {
    setQuery({ data: countedBatch(pagedGroups(34)) });

    renderScreen();

    fireEvent.change(screen.getByTestId('fsp-search'), {
      target: { value: 'Paged product' },
    });
    fireEvent.click(screen.getByTestId('fsp-show-more'));
    expect(shownProductCodes()).toHaveLength(34);

    fireEvent.change(screen.getByTestId('fsp-search'), {
      target: { value: '' },
    });

    expect(shownProductCodes()).toHaveLength(25);
    expect(screen.getByTestId('fsp-show-more')).toHaveTextContent('9 left');
  });

  it('clears the box from its own button, and the whole list comes back', () => {
    setQuery({ data: countedBatch(pagedGroups(34)) });

    renderScreen();

    fireEvent.change(screen.getByTestId('fsp-search'), {
      target: { value: 'SRTP0003' },
    });
    expect(shownProductCodes()).toEqual(['SRTP0003']);

    fireEvent.click(screen.getByTestId('fsp-search-clear'));

    expect(screen.getByTestId('fsp-search')).toHaveValue('');
    expect(shownProductCodes()).toHaveLength(25);
    expect(screen.getByTestId('fsp-show-more')).toHaveTextContent('9 left');
  });
});

describe('FlyerSpecReviewScreen, the row acts reach the hooks (AC-F.3, AC-G.4)', () => {
  it('sends a corrected value to the edit hook, naming the proposal id', async () => {
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    fireEvent.click(screen.getByLabelText('Edit Height'));
    const input = screen.getByLabelText('Height');
    fireEvent.change(input, { target: { value: '780' } });
    fireEvent.click(screen.getByLabelText('Save Height'));

    await waitFor(() =>
      expect(editValue.mutateAsync).toHaveBeenCalledWith({
        proposalId: 'p-change',
        value: 780,
      }),
    );
  });

  it('sends a dismissal to the dismiss hook once confirmed', () => {
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    fireEvent.click(screen.getByLabelText('Dismiss Seat cover material'));
    fireEvent.click(screen.getByTestId('fsp-dismiss-confirm'));

    expect(dismiss.mutateAsync).toHaveBeenCalledWith('p-new');
  });

  it('drops a dismissed row from the selection, so the bar cannot count it', async () => {
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    // The `new` row arrives ticked, and it is the one being dismissed.
    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '1 ticked',
    );

    fireEvent.click(screen.getByLabelText('Dismiss Seat cover material'));
    fireEvent.click(screen.getByTestId('fsp-dismiss-confirm'));

    await waitFor(() =>
      expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
        'Nothing ticked',
      ),
    );
    expect(dismiss.mutateAsync).toHaveBeenCalledWith('p-new');
  });

  it('keeps a ticked row ticked when the dismissal is refused', async () => {
    dismiss.mutateAsync = vi.fn().mockRejectedValue(new Error('nope'));
    useDismissFlyerSpecProposal.mockReturnValue(dismiss);
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    fireEvent.click(screen.getByLabelText('Dismiss Seat cover material'));
    fireEvent.click(screen.getByTestId('fsp-dismiss-confirm'));

    await waitFor(() => expect(dismiss.mutateAsync).toHaveBeenCalled());
    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '1 ticked',
    );
  });

  it('ticks a row somebody just added, so Apply carries what they typed', async () => {
    useApplicableSpecKeysQuery.mockReturnValue({
      data: {
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
        ],
      },
      isLoading: false,
    });
    addRow.mutateAsync = vi.fn().mockResolvedValue(
      proposalRow({
        id: 'p-added',
        spec_key: 'flush_volume',
        label: 'Flush volume',
        data_type: 'numeric',
        kind: 'new',
        value: 4.5,
        unit: 'l',
        origin: 'manual',
        edited: true,
      }),
    );
    useAddFlyerSpecProposalRow.mockReturnValue(addRow);
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
      '1 ticked',
    );

    fireEvent.click(screen.getByText('Add specification'));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(dialog).getByRole('combobox', { name: /specification/i }),
    );
    fireEvent.click(screen.getByText('Flush volume'));
    fireEvent.change(within(dialog).getByLabelText('Flush volume'), {
      target: { value: '4.5' },
    });
    fireEvent.click(screen.getByTestId('fsp-add-row-submit'));

    await waitFor(() =>
      expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
        '2 ticked',
      ),
    );

    fireEvent.click(screen.getByTestId('fsp-apply'));
    expect(apply.mutate).toHaveBeenCalledWith(
      expect.arrayContaining(['p-new', 'p-added']),
      expect.anything(),
    );
  });

  it('counts a just-added conflict row as a replacement, so Apply asks before overwriting a person', async () => {
    useApplicableSpecKeysQuery.mockReturnValue({
      data: {
        code: 'SRTWC8066',
        keys: [
          {
            spec_key: 'seat_material_2',
            label: 'Seat ring material',
            data_type: 'text',
            unit: null,
            allowed_values: [],
            synonyms: {},
            applicable: true,
            held: true,
          },
        ],
      },
      isLoading: false,
    });
    const addedConflict = proposalRow({
      id: 'p-added-conflict',
      spec_key: 'seat_material_2',
      label: 'Seat ring material',
      kind: 'conflict',
      value: 'pp',
      stored_value: 'uf',
      stored_source: 'human',
      origin: 'manual',
      edited: true,
    });
    // The real hook writes the returned row into the cached batch before the
    // call resolves (useAddFlyerSpecProposalRow); the mock does the same by
    // handing the screen the batch with the row in it on its next render.
    addRow.mutateAsync = vi.fn().mockImplementation(async () => {
      setQuery({
        data: countedBatch([
          {
            ...MIXED_GROUP,
            proposals: [...MIXED_GROUP.proposals, addedConflict],
          },
        ]),
      });
      return addedConflict;
    });
    useAddFlyerSpecProposalRow.mockReturnValue(addRow);
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    fireEvent.click(screen.getByText('Add specification'));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(
      within(dialog).getByRole('combobox', { name: /specification/i }),
    );
    fireEvent.click(screen.getByText('Seat ring material'));
    fireEvent.change(within(dialog).getByLabelText('Seat ring material'), {
      target: { value: 'pp' },
    });
    fireEvent.click(screen.getByTestId('fsp-add-row-submit'));

    await waitFor(() =>
      expect(screen.getByTestId('fsp-selection-count')).toHaveTextContent(
        '2 ticked, 1 replacing a value the master holds',
      ),
    );

    fireEvent.click(screen.getByTestId('fsp-apply'));

    expect(screen.getByRole('alertdialog')).toHaveTextContent(
      'Replace 1 master value, 1 of them set by a person?',
    );
    expect(apply.mutate).not.toHaveBeenCalled();
  });

  it('offers neither act to a reader who may not write the master', () => {
    hasPermission.mockReturnValue(false);
    setQuery({ data: countedBatch([MIXED_GROUP]) });

    renderScreen();

    expect(screen.queryByLabelText('Edit Height')).toBeNull();
    expect(screen.queryByLabelText('Dismiss Seat cover material')).toBeNull();
    expect(screen.queryByText('Add specification')).toBeNull();
  });
});
