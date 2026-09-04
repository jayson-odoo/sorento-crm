/**
 * The review screen as a whole (S7.4, plus the states a queued read added).
 *
 * The panel-level honesty lives in `MatchReportSections.test.tsx` and
 * `SeedPanel.test.tsx`. What this file owes is the screen's own states and
 * the one wire it owns: the promotion chosen at the top is the promotion the
 * report is computed against AND the promotion the seed applies. A screen that
 * reported the gaps of one promotion and then seeded with another would be
 * telling the truth about a brochure it did not build.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/flyer-readings/r-1',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const { getFlyerReading, seedFromFlyerReading, listPages, listPromotionOptions } = vi.hoisted(
  () => ({
    getFlyerReading: vi.fn(),
    seedFromFlyerReading: vi.fn(),
    listPages: vi.fn(),
    listPromotionOptions: vi.fn(),
  }),
);

vi.mock('../../../services/flyerReadingService', () => ({
  getFlyerReading,
  seedFromFlyerReading,
  listFlyerReadings: vi.fn(),
  uploadFlyerReading: vi.fn(),
  deleteFlyerReading: vi.fn(),
  applyDimensions: vi.fn(),
}));

// The sizes section asks whether this user may write the product master (S7.6),
// which goes through NextAuth. Stubbed rather than wrapped in a SessionProvider:
// what this file pins is the promotion wire, not RBAC.
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  useHasAnyPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

vi.mock('../../../services/dealerKitService', () => ({ listPages }));

vi.mock('../../../services/brochureImageService', () => ({
  PROMOTION_PAGE_SIZE: 50,
  listBrochureImagePromotionOptions: listPromotionOptions,
  listBrochureImages: vi.fn(),
}));

import type { FlyerReading } from '../../../services/flyerReadingService';
import { FlyerReviewScreen } from './FlyerReviewScreen';

const READING: FlyerReading = {
  id: 'r-1',
  filename: '_SORENTO A3 FLYER 2025-2026_compressed.pdf',
  byteSize: 20_000_000,
  pageCount: 36,
  codeCount: 998,
  uploadedAt: '2026-08-01T02:00:00',
  status: 'done',
  errorMessage: null,
  finishedAt: '2026-08-01T02:00:41',
  headings: [
    { page: 1, text: 'Inspiring Designs, Exciting Promotions' },
    // The known misread: the paper says "BATHTUB COLLECTION".
    { page: 2, text: 'Transforming Your' },
  ],
  report: {
    matched: [
      {
        code: 'SRTWC286-SH',
        productId: 'p-1',
        productCode: 'SRTWC286-SH',
        productName: 'One Piece Water Closet',
        pages: [1],
        adopted: false,
      },
    ],
    unmatched: [{ code: 'SRTKS7850', pages: [2], suggestion: null }],
    notPromoted: [],
    dimensionCandidates: [],
    duplicates: {},
    promotionId: null,
  },
  codeOverridesChangedAt: null,
};

/** A row that exists but has not been read yet - the queued-job state (AC-FE.4). */
const PROCESSING_READING: FlyerReading = {
  id: 'r-1',
  filename: 'flyer-being-read.pdf',
  byteSize: 20_000_000,
  pageCount: 0,
  codeCount: 0,
  uploadedAt: '2026-08-10T02:00:00',
  status: 'processing',
  errorMessage: null,
  finishedAt: null,
  headings: [],
  report: {
    matched: [],
    unmatched: [],
    notPromoted: [],
    dimensionCandidates: [],
    duplicates: {},
    promotionId: null,
  },
  codeOverridesChangedAt: null,
};

/** A row whose job ran and refused the file, in the request's own words. */
const FAILED_READING: FlyerReading = {
  id: 'r-1',
  filename: 'flyer-that-failed.pdf',
  byteSize: 0,
  pageCount: 0,
  codeCount: 0,
  uploadedAt: '2026-08-10T02:00:00',
  status: 'failed',
  errorMessage: 'That file is not a PDF. Export the flyer as a PDF and upload it again.',
  finishedAt: '2026-08-10T02:00:05',
  headings: [],
  report: {
    matched: [],
    unmatched: [],
    notPromoted: [],
    dimensionCandidates: [],
    duplicates: {},
    promotionId: null,
  },
  codeOverridesChangedAt: null,
};

function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FlyerReviewScreen readingId="r-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listPages.mockResolvedValue([]);
  listPromotionOptions.mockResolvedValue([
    { value: 'promo-1', label: 'A3 FLYER 2025-2026 DEALER', description: '883 products' },
  ]);
});

describe('FlyerReviewScreen', () => {
  it('shows a placeholder while the report is being computed', () => {
    getFlyerReading.mockReturnValue(new Promise(() => {}));

    renderScreen();

    expect(screen.getByTestId('dk-fr-loading')).toBeInTheDocument();
  });

  it('says the reading could not be opened, with a way back', async () => {
    getFlyerReading.mockRejectedValue(new Error('Flyer reading not found'));

    renderScreen();

    await waitFor(() => expect(screen.getByTestId('dk-fr-error')).toBeInTheDocument(), {
      timeout: 4000,
    });
    expect(screen.getByText(/flyer reading not found/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to flyers/i })).toHaveAttribute(
      'href',
      '/dealer-kit/flyer-readings',
    );
  });

  it('names the flyer and what was read off it', async () => {
    getFlyerReading.mockResolvedValue(READING);

    renderScreen();

    expect(await screen.findByTestId('dk-fr-filename')).toHaveTextContent(
      '_SORENTO A3 FLYER 2025-2026_compressed.pdf',
    );
    expect(screen.getByText(/36 pages, 998 product codes/i)).toBeInTheDocument();
  });

  it('renders the report and the seed panel on one screen, in that order', async () => {
    getFlyerReading.mockResolvedValue(READING);

    renderScreen();

    await screen.findByTestId('dk-fr-filename');
    // Reviewing then seeding is the journey, and the seed sits under the report
    // rather than beside it so nobody clicks it without scrolling past the misses.
    const report = document.querySelector('[data-dk-fr-section="unmatched"]');
    const seed = screen.getByTestId('dk-fr-seed-panel');
    expect(report).not.toBeNull();
    expect(report!.compareDocumentPosition(seed) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('starts with no promotion, and reports against one once it is chosen', async () => {
    getFlyerReading.mockResolvedValue(READING);

    renderScreen();

    await screen.findByTestId('dk-fr-filename');
    expect(getFlyerReading).toHaveBeenCalledWith('r-1', null);

    fireEvent.click(screen.getByRole('combobox', { name: '' }));
    fireEvent.click(await screen.findByText('A3 FLYER 2025-2026 DEALER'));

    // The report is derived per promotion, so choosing one re-asks for it.
    await waitFor(() => expect(getFlyerReading).toHaveBeenCalledWith('r-1', 'promo-1'));
  });

  it('keeps the report on screen while it is recomputed against a promotion', async () => {
    getFlyerReading.mockResolvedValueOnce(READING);
    // The second answer never arrives, so the screen is caught mid-recompute.
    getFlyerReading.mockReturnValueOnce(new Promise(() => {}));

    renderScreen();

    await screen.findByTestId('dk-fr-filename');
    fireEvent.click(screen.getByRole('combobox', { name: '' }));
    fireEvent.click(await screen.findByText('A3 FLYER 2025-2026 DEALER'));

    // The reviewer keeps what they were reading, and is told why the figures
    // are about to move. A skeleton here would throw away a half-filled form.
    expect(await screen.findByTestId('dk-fr-recomputing')).toBeInTheDocument();
    expect(screen.getByTestId('dk-fr-figure-printed')).toHaveTextContent('998');
    expect(screen.queryByTestId('dk-fr-loading')).toBeNull();
  });

  it('carries the chosen promotion into the seed by name, never by id', async () => {
    getFlyerReading.mockResolvedValue(READING);

    renderScreen();

    await screen.findByTestId('dk-fr-filename');
    fireEvent.click(screen.getByRole('combobox', { name: '' }));
    fireEvent.click(await screen.findByText('A3 FLYER 2025-2026 DEALER'));

    await waitFor(() =>
      expect(screen.getByTestId('dk-fr-seed-promotion')).toHaveTextContent(
        'A3 FLYER 2025-2026 DEALER',
      ),
    );
    expect(screen.getByTestId('dk-fr-seed-promotion').textContent ?? '').not.toMatch(/promo-1/);
  });

  it('seeds with the promotion the review step reported against', async () => {
    getFlyerReading.mockResolvedValue(READING);
    seedFromFlyerReading.mockResolvedValue({
      pageId: 'pg-9',
      name: 'zzt A3 Flyer',
      slug: 'zzt-a3-flyer',
      publicPath: '/c/zzt-a3-flyer',
      versionId: 'v-1',
      version: 1,
      sectionCount: 36,
      collectionCount: 347,
      seededProductCount: 960,
      skipped: READING.report.unmatched,
    });

    renderScreen();

    await screen.findByTestId('dk-fr-filename');
    fireEvent.click(screen.getByRole('combobox', { name: '' }));
    fireEvent.click(await screen.findByText('A3 FLYER 2025-2026 DEALER'));
    await waitFor(() => expect(getFlyerReading).toHaveBeenCalledWith('r-1', 'promo-1'));

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'zzt A3 Flyer' } });
    fireEvent.click(screen.getByTestId('dk-fr-seed-button'));

    await waitFor(() =>
      expect(seedFromFlyerReading).toHaveBeenCalledWith('r-1', {
        name: 'zzt A3 Flyer',
        slug: 'zzt-a3-flyer',
        promotionId: 'promo-1',
        commitMessage: 'Seeded from _SORENTO A3 FLYER 2025-2026_compressed.pdf',
      }),
    );
    // And the codes that did not make it are said again, on the last screen
    // before somebody opens the builder and stops thinking about the flyer.
    expect(await screen.findByTestId('dk-fr-result-skipped')).toHaveTextContent('SRTKS7850');
  });

  it('never prints an id anywhere on the screen', async () => {
    getFlyerReading.mockResolvedValue(READING);

    renderScreen();

    await screen.findByTestId('dk-fr-filename');
    expect(document.body.textContent ?? '').not.toMatch(/\bp-1\b|\br-1\b/);
  });
});

describe('FlyerReviewScreen, the queued-job states (AC-FE.4 / AC-FE.6)', () => {
  it('shows a waiting state while the reading is processing, with none of the report chrome', async () => {
    getFlyerReading.mockResolvedValue(PROCESSING_READING);

    renderScreen();

    expect(await screen.findByTestId('dk-fr-review-processing')).toBeInTheDocument();
    // The report, seed panel and promotion picker are all questions about a
    // report that has not been computed yet - none of them appear.
    expect(screen.queryByTestId('dk-fr-seed-panel')).not.toBeInTheDocument();
    expect(document.querySelector('[data-dk-fr-section]')).toBeNull();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dk-fr-recomputing')).not.toBeInTheDocument();
  });

  it('shows the failure reason and a way back when the reading failed', async () => {
    getFlyerReading.mockResolvedValue(FAILED_READING);

    renderScreen();

    const failed = await screen.findByTestId('dk-fr-review-failed');
    expect(failed).toHaveTextContent(/is not a pdf/i);

    const link = screen.getByRole('link', { name: /read another flyer/i });
    expect(link).toHaveAttribute('href', '/dealer-kit/flyer-readings');

    // Same as the processing state: nothing about a report that never ran.
    expect(screen.queryByTestId('dk-fr-seed-panel')).not.toBeInTheDocument();
    expect(document.querySelector('[data-dk-fr-section]')).toBeNull();
  });

  it('still renders the report sections and the seed panel once the reading is done', async () => {
    getFlyerReading.mockResolvedValue(READING);

    renderScreen();

    await screen.findByTestId('dk-fr-filename');
    expect(document.querySelector('[data-dk-fr-section="unmatched"]')).not.toBeNull();
    expect(screen.getByTestId('dk-fr-seed-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('dk-fr-review-processing')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dk-fr-review-failed')).not.toBeInTheDocument();
  });
});
