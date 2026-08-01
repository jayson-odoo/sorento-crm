/**
 * The review screen as a whole (S7.4).
 *
 * The panel-level honesty lives in `MatchReportSections.test.tsx` and
 * `SeedPanel.test.tsx`. What this file owes is the screen's own four states and
 * the one wire it owns: the promotion chosen at the top is the promotion the
 * report is computed against AND the promotion the seed applies. A screen that
 * reported the gaps of one promotion and then seeded with another would be
 * telling the truth about a brochure it did not build.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

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
  report: {
    matched: [
      {
        code: 'SRTWC286-SH',
        productId: 'p-1',
        productCode: 'SRTWC286-SH',
        productName: 'One Piece Water Closet',
        pages: [1],
      },
    ],
    unmatched: [{ code: 'SRTKS7850', pages: [2], suggestion: null }],
    notPromoted: [],
    dimensionCandidates: [],
    duplicates: {},
    promotionId: null,
  },
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
