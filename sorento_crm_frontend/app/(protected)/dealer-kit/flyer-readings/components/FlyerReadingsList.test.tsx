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

import { statusPillClass } from '@/lib/status-pill';

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
    status: 'done',
    errorMessage: null,
    finishedAt: '2026-08-01T02:00:41',
  },
  {
    id: 'r-2',
    filename: 'kitchen-sink-promo.pdf',
    byteSize: 3_000_000,
    pageCount: 4,
    codeCount: 61,
    uploadedAt: '2026-07-30T02:00:00',
    status: 'done',
    errorMessage: null,
    finishedAt: '2026-07-30T02:00:09',
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
    expect(empty).toHaveTextContent(/read a printed flyer from a pdf/i);
    // Both ways in are named, because the flyer is usually already in the files.
    expect(empty).toHaveTextContent(/upload one/i);
    expect(empty).toHaveTextContent(/pick a flyer already in your files/i);
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

describe('FlyerReadingsList, status pills (AC-FE.2 / AC-FE.6)', () => {
  const MIXED_ROWS: FlyerReadingSummary[] = [
    {
      id: 'r-p',
      filename: 'processing-flyer.pdf',
      byteSize: 0,
      pageCount: 0,
      codeCount: 0,
      uploadedAt: '2026-08-10T00:00:00',
      status: 'processing',
      errorMessage: null,
      finishedAt: null,
    },
    {
      id: 'r-d',
      filename: 'done-flyer.pdf',
      byteSize: 1_000_000,
      pageCount: 4,
      codeCount: 61,
      uploadedAt: '2026-08-09T00:00:00',
      status: 'done',
      errorMessage: null,
      finishedAt: '2026-08-09T00:01:00',
    },
    {
      id: 'r-f',
      filename: 'failed-flyer.pdf',
      byteSize: 500_000,
      pageCount: 0,
      codeCount: 0,
      uploadedAt: '2026-08-08T00:00:00',
      status: 'failed',
      errorMessage: 'That file is not a PDF. Export the flyer as a PDF and upload it again.',
      finishedAt: '2026-08-08T00:00:05',
    },
  ];

  it('shows all three pills - Processing / Done / Failed - in the shared palette (AC-FE.2)', async () => {
    listFlyerReadings.mockResolvedValue(MIXED_ROWS);

    renderList();

    const pills = await screen.findAllByTestId('dk-fr-status-pill');
    expect(pills.map((p) => p.textContent)).toEqual(
      expect.arrayContaining(['Processing', 'Done', 'Failed']),
    );

    const processingPill = pills.find((p) => p.textContent === 'Processing')!;
    const donePill = pills.find((p) => p.textContent === 'Done')!;
    const failedPill = pills.find((p) => p.textContent === 'Failed')!;
    // The pill colour comes straight off the shared palette, not a local copy.
    expect(processingPill.className).toContain(statusPillClass('processing'));
    expect(donePill.className).toContain(statusPillClass('done'));
    expect(failedPill.className).toContain(statusPillClass('failed'));
  });

  it('shows the failure reason beside a Failed pill, and only when one was recorded (AC-FE.2)', async () => {
    const rows: FlyerReadingSummary[] = [
      MIXED_ROWS[2],
      {
        id: 'r-f2',
        filename: 'failed-no-reason.pdf',
        byteSize: 0,
        pageCount: 0,
        codeCount: 0,
        uploadedAt: '2026-08-07T00:00:00',
        status: 'failed',
        errorMessage: null,
        finishedAt: '2026-08-07T00:00:05',
      },
    ];
    listFlyerReadings.mockResolvedValue(rows);

    renderList();

    await screen.findByText('failed-flyer.pdf');
    // Only the row that has a message gets a reason span; the other failed
    // row has none rather than an empty one.
    const reasons = screen.getAllByTestId('dk-fr-status-reason');
    expect(reasons).toHaveLength(1);
    expect(reasons[0]).toHaveTextContent(/not a pdf/i);
    expect(reasons[0]).toHaveAttribute(
      'title',
      'That file is not a PDF. Export the flyer as a PDF and upload it again.',
    );
  });

  it('still offers delete on a row that is Processing (AC-FE.5)', async () => {
    listFlyerReadings.mockResolvedValue(MIXED_ROWS);
    deleteFlyerReading.mockResolvedValue(undefined);

    renderList();

    const deleteButton = await screen.findByRole('button', {
      name: /delete processing-flyer\.pdf/i,
    });
    expect(deleteButton).toBeEnabled();
    fireEvent.click(deleteButton);

    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));

    await waitFor(() => expect(deleteFlyerReading).toHaveBeenCalledWith('r-p'));
  });

  it('opens the review screen from a Done row (AC-FE.4)', async () => {
    listFlyerReadings.mockResolvedValue(MIXED_ROWS);

    renderList();

    fireEvent.click(await screen.findByText('done-flyer.pdf'));

    await waitFor(() => expect(push).toHaveBeenCalledWith('/dealer-kit/flyer-readings/r-d'));
  });
});

describe('FlyerReadingsList, the upload dialog', () => {
  it('opens, accepts a PDF, and asks nobody to wait for it', async () => {
    listFlyerReadings.mockResolvedValue([]);

    renderList();

    fireEvent.click((await screen.findAllByRole('button', { name: /read a flyer/i }))[0]);

    const dialog = await screen.findByRole('dialog');
    // The read is a queued job, so there is nothing to sit through and the
    // dialog must not say there is.
    expect(dialog).not.toHaveTextContent(/read straight away/i);
    expect(dialog).not.toHaveTextContent(/up to a minute/i);
    expect(dialog).toHaveTextContent(/report of what was found/i);
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

  it('closes and leaves the designer on the list once the flyer is handed over', async () => {
    listFlyerReadings.mockResolvedValue([]);
    uploadFlyerReading.mockResolvedValue({
      id: 'r-9',
      filename: 'flyer.pdf',
      byteSize: 1,
      pageCount: 0,
      codeCount: 0,
      uploadedAt: '',
      status: 'processing',
      errorMessage: null,
      finishedAt: null,
    });

    renderList();

    fireEvent.click((await screen.findAllByRole('button', { name: /read a flyer/i }))[0]);
    const input = (await screen.findByLabelText('Flyer PDF')) as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['%PDF-1.4'], 'flyer.pdf', { type: 'application/pdf' })] },
    });
    fireEvent.click(screen.getByTestId('dk-fr-upload-submit'));

    // The dialog goes, and nothing navigates: the row is on the list being
    // read, and a review screen would have nothing on it yet.
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(push).not.toHaveBeenCalled();
  });
});
