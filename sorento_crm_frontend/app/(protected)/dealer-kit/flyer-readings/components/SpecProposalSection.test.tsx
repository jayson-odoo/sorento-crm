/**
 * SpecProposalSection - the one-button propose control on the reading page
 * (AC-D.1, AC-D.8).
 *
 * The HOOK is mocked, not the service: the section reads its state entirely off
 * `useFlyerSpecProposalsQuery` / `useProposeFlyerSpecs`, and every state in
 * AC-D.1 (none / proposing / proposed / failed, plus the not-yet-`done` reading
 * and the missing-permission case) is reachable by controlling what those two
 * hooks return, without a network layer in the loop.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const {
  useFlyerSpecProposalsQuery,
  useProposeFlyerSpecs,
  hasPermission,
  permissionsLoading,
} = vi.hoisted(() => ({
  useFlyerSpecProposalsQuery: vi.fn(),
  useProposeFlyerSpecs: vi.fn(),
  hasPermission: vi.fn(),
  permissionsLoading: { value: false },
}));

vi.mock(
  '../../../master-data-management/flyer-spec-proposals/hooks/useFlyerSpecProposals',
  () => ({
    useFlyerSpecProposalsQuery,
    useProposeFlyerSpecs,
  }),
);

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasPermission(slug),
  useHasAnyPermission: () => true,
  usePermissions: () => ({
    permissions: [],
    permissionSet: new Set(),
    isLoading: permissionsLoading.value,
  }),
}));

import type { FlyerSpecBatch } from '../../../master-data-management/flyer-spec-proposals/services/flyerSpecProposalService';
import { SpecProposalSection } from './SpecProposalSection';

function batch(overrides: Partial<FlyerSpecBatch> = {}): FlyerSpecBatch {
  return {
    id: null,
    reading_id: 'r-1',
    filename: 'flyer.pdf',
    status: 'none',
    error_message: null,
    product_count: 0,
    proposal_count: 0,
    new_count: 0,
    change_count: 0,
    conflict_count: 0,
    unchanged_count: 0,
    suppressed_count: 0,
    applied_count: 0,
    read_at: null,
    created_at: null,
    finished_at: null,
    applied_at: null,
    created_by_name: null,
    applied_by_name: null,
    ...overrides,
  };
}

const propose = { mutate: vi.fn(), isPending: false };

const refetch = vi.fn();

function setQuery(
  data: FlyerSpecBatch | undefined,
  isLoading = false,
  error: Error | null = null,
) {
  useFlyerSpecProposalsQuery.mockReturnValue({
    data,
    isLoading,
    isError: error !== null,
    error,
    refetch,
  });
}

function renderSection(
  readingStatus: 'processing' | 'done' | 'failed' = 'done',
  codeOverridesChangedAt: string | null = null,
) {
  return render(
    <SpecProposalSection
      readingId="r-1"
      readingStatus={readingStatus}
      codeOverridesChangedAt={codeOverridesChangedAt}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  hasPermission.mockReturnValue(true);
  permissionsLoading.value = false;
  propose.mutate = vi.fn();
  propose.isPending = false;
  useProposeFlyerSpecs.mockReturnValue(propose);
});

describe('SpecProposalSection, before the batch answers and when it refuses (AC-D.1)', () => {
  it('shows a checking line and a disabled button while the batch is loading, not the not-read copy', () => {
    setQuery(undefined, true);

    renderSection('done');

    expect(screen.getByTestId('dk-fr-spec-loading')).toBeInTheDocument();
    expect(
      screen.queryByText('This flyer has not been read for specifications'),
    ).toBeNull();
    expect(screen.getByTestId('dk-fr-spec-propose')).toBeDisabled();
  });

  it('shows the refusal with a retry, and does not offer to propose over it', () => {
    setQuery(
      undefined,
      false,
      new Error('Permission required: dealer_kit.page.view'),
    );

    renderSection('done');

    const failure = screen.getByTestId('dk-fr-spec-error');
    expect(failure).toHaveTextContent(
      'Permission required: dealer_kit.page.view',
    );
    expect(
      screen.queryByText('This flyer has not been read for specifications'),
    ).toBeNull();
    expect(screen.getByTestId('dk-fr-spec-propose')).toBeDisabled();

    fireEvent.click(screen.getByTestId('dk-fr-spec-error-retry'));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('shows the refusal, not a stale proposing spinner, when a poll fails with data still cached', () => {
    setQuery(
      batch({ status: 'proposing', id: 'batch-1' }),
      false,
      new Error('boom'),
    );

    renderSection('done');

    expect(screen.getByTestId('dk-fr-spec-error')).toBeInTheDocument();
    expect(screen.queryByTestId('dk-fr-spec-proposing')).toBeNull();
  });
});

describe('SpecProposalSection, status none (AC-D.1)', () => {
  it('shows the propose button, enabled, once the flyer is done', () => {
    setQuery(batch({ status: 'none' }));

    renderSection('done');

    const button = screen.getByTestId('dk-fr-spec-propose');
    expect(button).toHaveTextContent('Propose specs from this flyer');
    expect(button).toBeEnabled();
    expect(
      screen.getByText('This flyer has not been read for specifications'),
    ).toBeInTheDocument();
  });
});

describe('SpecProposalSection, a reading that is not yet done (AC-D.1)', () => {
  it('disables the button with "Read the flyer first", whatever status the batch answers with', () => {
    setQuery(batch({ status: 'none' }));

    renderSection('processing');

    const button = screen.getByTestId('dk-fr-spec-propose');
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent('Read the flyer first');
    expect(button).toHaveAttribute('title', 'Read the flyer first');
  });
});

describe('SpecProposalSection, status proposing (AC-D.1)', () => {
  it('shows the spinner and no counts', () => {
    setQuery(batch({ status: 'proposing', id: 'batch-1' }));

    renderSection('done');

    expect(screen.getByTestId('dk-fr-spec-proposing')).toBeInTheDocument();
    expect(screen.queryByTestId('dk-fr-spec-proposed')).toBeNull();
    expect(screen.queryByTestId('dk-fr-spec-failed')).toBeNull();
  });
});

describe('SpecProposalSection, status proposed (AC-D.1)', () => {
  it('shows the counts sentence, a Review proposals link, and a Propose again action', () => {
    setQuery(
      batch({
        status: 'proposed',
        id: 'batch-1',
        product_count: 2,
        proposal_count: 5,
        new_count: 2,
        change_count: 1,
        conflict_count: 1,
        unchanged_count: 1,
        suppressed_count: 0,
      }),
    );

    renderSection('done');

    const proposed = screen.getByTestId('dk-fr-spec-proposed');
    expect(proposed).toHaveTextContent(
      'This flyer states 5 specification values across 2 products: 2 new, 1 change what the master says, 1 conflict with a value a person set, 1 unchanged, 0 suppressed.',
    );

    const link = screen.getByRole('link', { name: 'Review proposals' });
    expect(link).toHaveAttribute(
      'href',
      '/master-data-management/flyer-spec-proposals/r-1',
    );

    const button = screen.getByTestId('dk-fr-spec-propose');
    expect(button).toHaveTextContent('Propose again');
    expect(button).toBeEnabled();
  });

  it('says nothing new was found when the batch proposed zero rows', () => {
    setQuery(batch({ status: 'proposed', id: 'batch-1', proposal_count: 0 }));

    renderSection('done');

    expect(
      screen.getByText(
        'This flyer states nothing the product master does not already hold.',
      ),
    ).toBeInTheDocument();
  });
});

describe('SpecProposalSection, status failed (AC-D.1)', () => {
  it('shows the error message and a Try again action', () => {
    setQuery(
      batch({
        status: 'failed',
        id: 'batch-1',
        error_message:
          'The specification rules could not be loaded while reading this flyer',
      }),
    );

    renderSection('done');

    const failed = screen.getByTestId('dk-fr-spec-failed');
    expect(failed).toHaveTextContent(
      'The specification rules could not be loaded while reading this flyer',
    );
    expect(screen.getByTestId('dk-fr-spec-retry')).toHaveTextContent(
      'Try again',
    );
  });

  it('falls back to a generic message when none was recorded', () => {
    setQuery(batch({ status: 'failed', id: 'batch-1', error_message: null }));

    renderSection('done');

    expect(screen.getByTestId('dk-fr-spec-failed')).toHaveTextContent(
      'The specifications could not be read, and no reason was recorded.',
    );
  });
});

describe('SpecProposalSection, while the permissions are still being fetched (AC-D.1)', () => {
  it('shows the checking line, not the permission refusal, and fires no request yet', () => {
    permissionsLoading.value = true;
    hasPermission.mockReturnValue(false);
    setQuery(undefined);

    renderSection('done');

    expect(screen.getByTestId('dk-fr-spec-loading')).toBeInTheDocument();
    expect(screen.queryByText('No spec proposals yet')).toBeNull();
    expect(screen.queryByTestId('dk-fr-spec-propose')).toBeNull();
    expect(useFlyerSpecProposalsQuery).toHaveBeenCalledWith('r-1', {
      enabled: false,
    });
  });
});

describe('SpecProposalSection, the adoption hint (AC-C.4)', () => {
  it('shows the hint when a code was adopted or undone after a proposed batch', () => {
    setQuery(
      batch({
        status: 'proposed',
        id: 'batch-1',
        created_at: '2026-08-30T10:00:00',
      }),
    );

    renderSection('done', '2026-08-30T11:00:00');

    expect(
      screen.getByTestId('dk-fr-spec-adoption-hint'),
    ).toHaveTextContent(
      'Codes were adopted or undone after this proposal. Propose again to reflect them.',
    );
  });

  it('shows the hint on a failed batch too, when the code moved after it', () => {
    setQuery(
      batch({
        status: 'failed',
        id: 'batch-1',
        created_at: '2026-08-30T10:00:00',
      }),
    );

    renderSection('done', '2026-08-30T11:00:00');

    expect(screen.getByTestId('dk-fr-spec-adoption-hint')).toBeInTheDocument();
  });

  it('hides the hint when there is no batch at all', () => {
    setQuery(batch({ status: 'none' }));

    renderSection('done', '2026-08-30T11:00:00');

    expect(screen.queryByTestId('dk-fr-spec-adoption-hint')).toBeNull();
  });

  it('hides the hint while the batch is still proposing', () => {
    setQuery(
      batch({
        status: 'proposing',
        id: 'batch-1',
        created_at: '2026-08-30T10:00:00',
      }),
    );

    renderSection('done', '2026-08-30T11:00:00');

    expect(screen.queryByTestId('dk-fr-spec-adoption-hint')).toBeNull();
  });

  it('hides the hint when the code changed before the batch was created', () => {
    setQuery(
      batch({
        status: 'proposed',
        id: 'batch-1',
        created_at: '2026-08-30T11:00:00',
      }),
    );

    renderSection('done', '2026-08-30T10:00:00');

    expect(screen.queryByTestId('dk-fr-spec-adoption-hint')).toBeNull();
  });

  it('hides the hint when the timestamps are equal', () => {
    setQuery(
      batch({
        status: 'proposed',
        id: 'batch-1',
        created_at: '2026-08-30T10:00:00',
      }),
    );

    renderSection('done', '2026-08-30T10:00:00');

    expect(screen.queryByTestId('dk-fr-spec-adoption-hint')).toBeNull();
  });

  it('hides the hint when no code has ever been adopted or undone', () => {
    setQuery(
      batch({
        status: 'proposed',
        id: 'batch-1',
        created_at: '2026-08-30T10:00:00',
      }),
    );

    renderSection('done', null);

    expect(screen.queryByTestId('dk-fr-spec-adoption-hint')).toBeNull();
  });
});

describe('SpecProposalSection, without master_data.products.edit (AC-D.1)', () => {
  it('never shows the hint to someone who cannot propose', () => {
    hasPermission.mockReturnValue(false);
    setQuery(
      batch({
        status: 'proposed',
        id: 'batch-1',
        created_at: '2026-08-30T10:00:00',
      }),
    );

    renderSection('done', '2026-08-30T11:00:00');

    expect(screen.queryByTestId('dk-fr-spec-adoption-hint')).toBeNull();
  });

  it('shows the empty copy and offers no button at all', () => {
    hasPermission.mockReturnValue(false);
    setQuery(batch({ status: 'none' }));

    renderSection('done');

    expect(screen.getByText('No spec proposals yet')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Reading a flyer for specifications needs the product master permission, which your role does not have.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('dk-fr-spec-propose')).toBeNull();
  });

  it('offers no button even once a batch is proposed', () => {
    hasPermission.mockReturnValue(false);
    setQuery(batch({ status: 'proposed', id: 'batch-1', proposal_count: 3 }));

    renderSection('done');

    expect(screen.getByText('No spec proposals yet')).toBeInTheDocument();
    expect(screen.queryByTestId('dk-fr-spec-propose')).toBeNull();
    expect(screen.queryByTestId('dk-fr-spec-proposed')).toBeNull();
  });

  it('does not fire the proposals request at all', () => {
    // The route needs the product-master permission as well, so a request from
    // here could only come back 403. The section says what it is without asking.
    hasPermission.mockReturnValue(false);
    setQuery(undefined);

    renderSection('done');

    expect(useFlyerSpecProposalsQuery).toHaveBeenCalledWith('r-1', {
      enabled: false,
    });
  });

  it('does fire it for somebody who holds the permission', () => {
    hasPermission.mockReturnValue(true);
    setQuery(batch({ status: 'none' }));

    renderSection('done');

    expect(useFlyerSpecProposalsQuery).toHaveBeenCalledWith('r-1', {
      enabled: true,
    });
  });
});
