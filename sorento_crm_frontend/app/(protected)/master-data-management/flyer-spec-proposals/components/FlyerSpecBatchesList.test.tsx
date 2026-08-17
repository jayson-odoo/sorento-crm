/**
 * The Master Data list of flyer spec proposal batches (AC-D.6, AC-D.8).
 *
 * `DataGrid` calls `useListingColumnPreferences`, which never answers under
 * jsdom - mocked before the import that pulls `DataGrid` in transitively (see
 * CLAUDE.md: "`DataGridTable` DOES mount rows under jsdom").
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/master-data-management/flyer-spec-proposals',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const { listFlyerSpecBatches } = vi.hoisted(() => ({ listFlyerSpecBatches: vi.fn() }));

vi.mock('../services/flyerSpecProposalService', () => ({
  listFlyerSpecBatches,
  getFlyerSpecProposals: vi.fn(),
  proposeFlyerSpecs: vi.fn(),
  applyFlyerSpecProposals: vi.fn(),
}));

import type { FlyerSpecBatch } from '../services/flyerSpecProposalService';
import { FlyerSpecBatchesList } from './FlyerSpecBatchesList';

function batch(overrides: Partial<FlyerSpecBatch> = {}): FlyerSpecBatch {
  return {
    id: 'batch-1',
    reading_id: 'r-1',
    filename: 'Sorento Bathroom Collection 2026 A3.pdf',
    status: 'proposed',
    error_message: null,
    product_count: 3,
    proposal_count: 12,
    new_count: 7,
    change_count: 3,
    conflict_count: 2,
    unchanged_count: 0,
    suppressed_count: 0,
    applied_count: 0,
    read_at: '2026-08-16T09:12:00',
    created_at: '2026-08-16T10:02:00',
    finished_at: '2026-08-16T10:02:41',
    applied_at: null,
    created_by_name: 'Aisyah Rahman',
    applied_by_name: null,
    ...overrides,
  };
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FlyerSpecBatchesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('FlyerSpecBatchesList, rows (AC-D.6)', () => {
  it('lists the batch, by filename, with its counts', async () => {
    listFlyerSpecBatches.mockResolvedValue([batch()]);

    renderList();

    expect(
      await screen.findByText('Sorento Bathroom Collection 2026 A3.pdf'),
    ).toBeInTheDocument();
    // The batch's own products/values/new figures - `3` also matches the
    // `change_count`, so this asserts the full set of figure cells is present
    // rather than any one of them in isolation.
    expect(screen.getAllByText('3')).toHaveLength(2); // product_count and change_count
    expect(screen.getByText('12')).toBeInTheDocument(); // proposal_count
    expect(screen.getByText('7')).toBeInTheDocument(); // new_count
    expect(screen.getByText('2')).toBeInTheDocument(); // conflict_count
  });

  it('opens the review screen from a row click', async () => {
    listFlyerSpecBatches.mockResolvedValue([batch()]);

    renderList();

    fireEvent.click(await screen.findByText('Sorento Bathroom Collection 2026 A3.pdf'));

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/master-data-management/flyer-spec-proposals/r-1'),
    );
  });

  it('filters on the file name without asking the server again', async () => {
    listFlyerSpecBatches.mockResolvedValue([
      batch({ reading_id: 'r-1', filename: 'Kitchen Sinks Reprint March.pdf' }),
      batch({ reading_id: 'r-2', filename: 'Showroom Poster Set.pdf' }),
    ]);

    renderList();

    await screen.findByText('Kitchen Sinks Reprint March.pdf');
    fireEvent.change(screen.getByLabelText('Search flyers'), {
      target: { value: 'showroom' },
    });

    await waitFor(() =>
      expect(screen.queryByText('Kitchen Sinks Reprint March.pdf')).toBeNull(),
    );
    expect(screen.getByText('Showroom Poster Set.pdf')).toBeInTheDocument();
    expect(listFlyerSpecBatches).toHaveBeenCalledTimes(1);
  });
});

describe('FlyerSpecBatchesList, the Applied status derivation (AC-D.6)', () => {
  it('reads "Proposing" while a pass is running', async () => {
    listFlyerSpecBatches.mockResolvedValue([batch({ status: 'proposing', applied_count: 0 })]);

    renderList();

    expect(await screen.findByTestId('fsp-status-pill')).toHaveTextContent('Proposing');
  });

  it('reads "Failed" with the error message alongside it', async () => {
    listFlyerSpecBatches.mockResolvedValue([
      batch({
        status: 'failed',
        error_message: 'The specification rules could not be loaded',
      }),
    ]);

    renderList();

    expect(await screen.findByTestId('fsp-status-pill')).toHaveTextContent('Failed');
    expect(
      screen.getByText('The specification rules could not be loaded'),
    ).toBeInTheDocument();
  });

  it('reads "Proposed" when settled but nothing has been applied yet', async () => {
    listFlyerSpecBatches.mockResolvedValue([batch({ status: 'proposed', applied_count: 0 })]);

    renderList();

    expect(await screen.findByTestId('fsp-status-pill')).toHaveTextContent('Proposed');
  });

  it('reads "Applied" the moment at least one row has been written, even mid-batch', async () => {
    // A batch with rows still ticked-but-unapplied is still `proposed` server
    // side; `applied_count > 0` is what flips the pill, not the batch status.
    listFlyerSpecBatches.mockResolvedValue([
      batch({ status: 'proposed', applied_count: 4, applied_at: '2026-08-16T11:00:00' }),
    ]);

    renderList();

    expect(await screen.findByTestId('fsp-status-pill')).toHaveTextContent('Applied');
  });
});

describe('FlyerSpecBatchesList, empty state (AC-D.6)', () => {
  it('says no flyer has been proposed yet, and what to do about it', async () => {
    listFlyerSpecBatches.mockResolvedValue([]);

    renderList();

    const empty = await screen.findByTestId('fsp-list-empty');
    expect(empty).toHaveTextContent('No flyer has been proposed yet');
    expect(empty).toHaveTextContent('Read a flyer in Dealer Kit and press Propose specs.');
  });

  it('says a search matched nothing rather than reading as an empty account', async () => {
    listFlyerSpecBatches.mockResolvedValue([batch()]);

    renderList();

    await screen.findByText('Sorento Bathroom Collection 2026 A3.pdf');
    fireEvent.change(screen.getByLabelText('Search flyers'), { target: { value: 'zzzz' } });

    expect(await screen.findByText(/no flyer matches that search/i)).toBeInTheDocument();
  });

  it('replaces the grid with the failure instead of an empty account', async () => {
    listFlyerSpecBatches.mockRejectedValue(
      new Error('Permission required: master_data.products.edit'),
    );

    renderList();

    await waitFor(() => expect(screen.getByTestId('fsp-list-error')).toBeInTheDocument(), {
      timeout: 4000,
    });
    expect(screen.getByText(/permission required/i)).toBeInTheDocument();
    expect(screen.queryByTestId('fsp-list-empty')).toBeNull();
  });
});

describe('FlyerSpecBatchesList, sorting (AC-D.6)', () => {
  // The header offered a sort the table never performed: the arrow toggled and
  // `sorting` updated, but with no sorted row model the rows stayed where they
  // were. Asserting on the ORDER of the rendered rows, not on the arrow.
  it('moves the rows when a sortable header is clicked', async () => {
    listFlyerSpecBatches.mockResolvedValue([
      batch({ reading_id: 'r-1', filename: 'Zinc Taps Winter.pdf' }),
      batch({ reading_id: 'r-2', filename: 'Alpha Basins Spring.pdf' }),
    ]);

    renderList();

    await screen.findByText('Zinc Taps Winter.pdf');

    const flyerColumn = () =>
      screen
        .getAllByRole('row')
        .map((row) => row.textContent ?? '')
        .filter((text) => text.includes('.pdf'));

    expect(flyerColumn()[0]).toContain('Zinc Taps Winter.pdf');

    fireEvent.click(screen.getByRole('button', { name: 'Flyer' }));

    await waitFor(() =>
      expect(flyerColumn()[0]).toContain('Alpha Basins Spring.pdf'),
    );
    expect(flyerColumn()[1]).toContain('Zinc Taps Winter.pdf');
  });
});
