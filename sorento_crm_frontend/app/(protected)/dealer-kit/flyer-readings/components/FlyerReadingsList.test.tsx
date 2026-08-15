/**
 * The flyer list, step one of the journey (S7.4).
 *
 * The list itself is thin on purpose - it carries no report, because a report
 * is a match run against 998 codes. What it owes is the four states, an empty
 * state that says what to do next, and a delete confirmation that says what
 * deleting a reading does NOT take with it.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/flyer-readings',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

// Saved column widths are a per-user preference fetched over the network. Left
// real, the grid sits in its loading state forever under jsdom and every
// assertion below passes or fails for a reason that has nothing to do with it.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const { listFlyerReadings, deleteFlyerReading, uploadFlyerReading } = vi.hoisted(() => ({
  listFlyerReadings: vi.fn(),
  deleteFlyerReading: vi.fn(),
  uploadFlyerReading: vi.fn(),
}));

vi.mock('../../services/flyerReadingService', () => ({
  listFlyerReadings,
  deleteFlyerReading,
  uploadFlyerReading,
  getFlyerReading: vi.fn(),
  seedFromFlyerReading: vi.fn(),
}));

import type { FlyerReadingSummary } from '../../services/flyerReadingService';
import { FlyerReadingsList } from './FlyerReadingsList';

const ROWS: FlyerReadingSummary[] = [
  {
    id: 'r-1',
    filename: '_SORENTO A3 FLYER 2025-2026_compressed.pdf',
    byteSize: 20_000_000,
    pageCount: 36,
    codeCount: 998,
    uploadedAt: '2026-08-01T02:00:00',
  },
  {
    id: 'r-2',
    filename: 'kitchen-sink-promo.pdf',
    byteSize: 3_000_000,
    pageCount: 4,
    codeCount: 61,
    uploadedAt: '2026-07-30T02:00:00',
  },
];

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FlyerReadingsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('FlyerReadingsList', () => {
  it('shows placeholders while the flyers are loading', async () => {
    listFlyerReadings.mockReturnValue(new Promise(() => {}));

    const { container } = renderList();

    await waitFor(() =>
      expect(container.querySelector('[data-slot="skeleton"], .animate-pulse')).toBeTruthy(),
    );
  });

  it('replaces the table with the failure instead of a blank grid', async () => {
    listFlyerReadings.mockRejectedValue(new Error('Permission required: dealer_kit.page.view'));

    renderList();

    // The query retries once before giving up, so the error state is a moment
    // away rather than immediate.
    await waitFor(() => expect(screen.getByTestId('dk-fr-list-error')).toBeInTheDocument(), {
      timeout: 4000,
    });
    // An empty grid next to an error reads as "no flyers have been read", which
    // is a different and much more comfortable lie.
    expect(screen.getByText(/permission required/i)).toBeInTheDocument();
  });

  it('says what to do next when nothing has been read yet', async () => {
    listFlyerReadings.mockResolvedValue([]);

    renderList();

    const empty = await screen.findByTestId('dk-fr-list-empty');
    expect(empty).toHaveTextContent(/no flyer has been read yet/i);
    expect(empty).toHaveTextContent(/upload a printed flyer as a pdf/i);
    // The next step is a button, not a sentence telling somebody to find one.
    expect(screen.getAllByRole('button', { name: /read a flyer/i }).length).toBeGreaterThan(0);
  });

  it('lists what was read, by name and not by id', async () => {
    listFlyerReadings.mockResolvedValue(ROWS);

    renderList();

    expect(
      await screen.findByText('_SORENTO A3 FLYER 2025-2026_compressed.pdf'),
    ).toBeInTheDocument();
    expect(screen.getByText('998')).toBeInTheDocument();
    expect(document.body.textContent ?? '').not.toMatch(/\br-1\b/);
  });

  it('opens the review screen from a row, because reading is the point', async () => {
    listFlyerReadings.mockResolvedValue(ROWS);

    renderList();

    fireEvent.click(await screen.findByText('kitchen-sink-promo.pdf'));

    await waitFor(() => expect(push).toHaveBeenCalledWith('/dealer-kit/flyer-readings/r-2'));
  });

  it('confirms a delete, and says the brochure it seeded survives it', async () => {
    listFlyerReadings.mockResolvedValue(ROWS);

    renderList();

    fireEvent.click(
      await screen.findByRole('button', { name: /delete kitchen-sink-promo\.pdf/i }),
    );

    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    expect(screen.getByText(/this action cannot be undone/i)).toBeInTheDocument();
    // "Delete" beside a flyer that produced a live catalogue reads like it takes
    // the catalogue with it. Nothing links the two, and the copy says so.
    expect(screen.getByText(/left exactly as it is/i)).toBeInTheDocument();
    // Confirming is a second, deliberate act.
    expect(deleteFlyerReading).not.toHaveBeenCalled();
  });

  it('deletes only the row that was confirmed', async () => {
    listFlyerReadings.mockResolvedValue(ROWS);
    deleteFlyerReading.mockResolvedValue(undefined);

    renderList();

    fireEvent.click(
      await screen.findByRole('button', { name: /delete kitchen-sink-promo\.pdf/i }),
    );
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }));

    await waitFor(() => expect(deleteFlyerReading).toHaveBeenCalledWith('r-2'));
    expect(deleteFlyerReading).toHaveBeenCalledTimes(1);
  });

  it('filters on the file name rather than asking the server again', async () => {
    listFlyerReadings.mockResolvedValue(ROWS);

    renderList();

    await screen.findByText('kitchen-sink-promo.pdf');
    fireEvent.change(screen.getByLabelText('Search flyers'), { target: { value: 'kitchen' } });

    await waitFor(() =>
      expect(screen.queryByText('_SORENTO A3 FLYER 2025-2026_compressed.pdf')).toBeNull(),
    );
    expect(screen.getByText('kitchen-sink-promo.pdf')).toBeInTheDocument();
    expect(listFlyerReadings).toHaveBeenCalledTimes(1);
  });

  it('says a search matched nothing rather than reading as an empty account', async () => {
    listFlyerReadings.mockResolvedValue(ROWS);

    renderList();

    await screen.findByText('kitchen-sink-promo.pdf');
    fireEvent.change(screen.getByLabelText('Search flyers'), { target: { value: 'zzzz' } });

    expect(await screen.findByText(/no flyer matches that search/i)).toBeInTheDocument();
  });
});

describe('FlyerReadingsList, the upload dialog', () => {
  it('opens, accepts a PDF, and says extraction happens now rather than later', async () => {
    listFlyerReadings.mockResolvedValue([]);

    renderList();

    fireEvent.click((await screen.findAllByRole('button', { name: /read a flyer/i }))[0]);

    const dialog = await screen.findByRole('dialog');
    // No queue, no job to watch: it is read straight away.
    expect(dialog).toHaveTextContent(/read straight away/i);
    expect(screen.getByLabelText('Flyer PDF')).toHaveAttribute('accept', 'application/pdf,.pdf');
    // Nothing to upload yet, so nothing to submit.
    expect(screen.getByTestId('dk-fr-upload-submit')).toBeDisabled();
  });

  it('shows the backend refusal in words instead of a generic failure', async () => {
    listFlyerReadings.mockResolvedValue([]);
    uploadFlyerReading.mockRejectedValue(
      new Error('That file is not a PDF. Export the flyer as a PDF and upload it again.'),
    );

    renderList();

    fireEvent.click((await screen.findAllByRole('button', { name: /read a flyer/i }))[0]);

    const input = (await screen.findByLabelText('Flyer PDF')) as HTMLInputElement;
    const file = new File(['not a pdf'], 'flyer.docx', { type: 'application/msword' });
    fireEvent.change(input, { target: { files: [file] } });

    fireEvent.click(screen.getByTestId('dk-fr-upload-submit'));

    expect(await screen.findByTestId('dk-fr-upload-error')).toHaveTextContent(/is not a pdf/i);
    expect(push).not.toHaveBeenCalled();
  });

  it('lands on the review screen once the flyer has been read', async () => {
    listFlyerReadings.mockResolvedValue([]);
    uploadFlyerReading.mockResolvedValue({
      id: 'r-9',
      filename: 'flyer.pdf',
      byteSize: 1,
      pageCount: 3,
      codeCount: 61,
      uploadedAt: '',
      report: {
        matched: [],
        unmatched: [],
        notPromoted: [],
        dimensionCandidates: [],
        duplicates: {},
        promotionId: null,
      },
    });

    renderList();

    fireEvent.click((await screen.findAllByRole('button', { name: /read a flyer/i }))[0]);
    const input = (await screen.findByLabelText('Flyer PDF')) as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['%PDF-1.4'], 'flyer.pdf', { type: 'application/pdf' })] },
    });
    fireEvent.click(screen.getByTestId('dk-fr-upload-submit'));

    // Reading a flyer and never looking at what came back is the one path this
    // feature must not have.
    await waitFor(() => expect(push).toHaveBeenCalledWith('/dealer-kit/flyer-readings/r-9'));
  });
});
