/**
 * Step three, and the two sentences it must never stop saying (S7.4).
 *
 * 1. **Unmatched codes are dropped.** Named before the seed and again in the
 *    result. Each one is a product the paper advertises that the brochure will
 *    not carry, and the result screen is the last moment anybody is still
 *    thinking about the flyer.
 * 2. **Re-seeding never overwrites.** "Seed into an existing brochure" reads
 *    like an overwrite to anybody who has not read the plan. It writes a new
 *    version and leaves the published one exactly where it is (PLAN D10).
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/flyer-readings/r-1',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

const { listPages, seedFromFlyerReading } = vi.hoisted(() => ({
  listPages: vi.fn(),
  seedFromFlyerReading: vi.fn(),
}));

vi.mock('../../services/dealerKitService', () => ({ listPages }));
vi.mock('../../services/flyerReadingService', () => ({ seedFromFlyerReading }));

import type { FlyerSeedResult, UnmatchedCode } from '../../services/flyerReadingService';
import { SeedPanel, SeedResult } from './SeedPanel';

const UNMATCHED: UnmatchedCode[] = [
  { code: 'SRTKS7850', pages: [2], suggestion: null },
  { code: 'FG-CW13', pages: [3], suggestion: null },
];

const PAGES = [
  {
    id: 'pg-1',
    name: 'Sorento Catalogue 2026',
    slug: 'sorento-2026',
    updatedAt: '2026-08-01T00:00:00',
    publishedVersion: 4,
    latestVersion: 7,
    publicPath: '/c/sorento-2026',
    promotionId: null,
    promotionLabel: null,
  },
  {
    id: 'pg-2',
    name: 'Draft Only Brochure',
    slug: 'draft-only',
    updatedAt: '2026-08-01T00:00:00',
    publishedVersion: null,
    latestVersion: 1,
    publicPath: '/c/draft-only',
    promotionId: null,
    promotionLabel: null,
  },
];

const RESULT: FlyerSeedResult = {
  pageId: 'pg-9',
  name: 'zzt A3 Flyer',
  slug: 'zzt-a3-flyer',
  publicPath: '/c/zzt-a3-flyer',
  versionId: 'v-1',
  version: 1,
  sectionCount: 3,
  collectionCount: 9,
  seededProductCount: 55,
  skipped: UNMATCHED,
};

function renderPanel(props: Partial<React.ComponentProps<typeof SeedPanel>> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SeedPanel
        readingId="r-1"
        filename="flyer.pdf"
        unmatched={UNMATCHED}
        matchedCount={55}
        promotionId={null}
        promotionLabel={null}
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listPages.mockResolvedValue(PAGES);
});

describe('SeedPanel, before the seed', () => {
  it('names the codes it is about to leave out', () => {
    renderPanel();

    const warning = screen.getByTestId('dk-fr-seed-skip-warning');
    expect(warning).toHaveTextContent('2 printed codes will be left out');
    expect(warning).toHaveTextContent('SRTKS7850');
    expect(warning).toHaveTextContent('FG-CW13');
  });

  it('says nothing about dropped codes when none were dropped', () => {
    renderPanel({ unmatched: [] });

    expect(screen.queryByTestId('dk-fr-seed-skip-warning')).toBeNull();
  });

  it('says the draft reaches no reader until somebody approves it', () => {
    renderPanel();

    expect(screen.getByTestId('dk-fr-seed-panel')).toHaveTextContent(
      /nothing is published/i,
    );
  });

  it('says list prices are a finished answer when no promotion is chosen', () => {
    renderPanel();

    expect(screen.getByTestId('dk-fr-seed-promotion')).toHaveTextContent(/no promotion/i);
    expect(screen.getByTestId('dk-fr-seed-promotion')).toHaveTextContent(/list price/i);
  });

  it('names the promotion the review step chose, never its id', () => {
    renderPanel({ promotionId: 'promo-1', promotionLabel: 'A3 Flyer 2026' });

    const line = screen.getByTestId('dk-fr-seed-promotion');
    expect(line).toHaveTextContent('A3 Flyer 2026');
    expect(line.textContent ?? '').not.toMatch(/promo-1/);
  });

  it('will not seed until a new brochure has a name', () => {
    renderPanel();

    expect(screen.getByTestId('dk-fr-seed-button')).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'zzt A3 Flyer' } });

    expect(screen.getByTestId('dk-fr-seed-button')).toBeEnabled();
  });

  it('derives the address from the name so nobody types it twice', () => {
    renderPanel();

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'zzt A3 Flyer 2026' } });

    expect(screen.getByLabelText('Address')).toHaveValue('zzt-a3-flyer-2026');
  });
});

describe('SeedPanel, seeding into an existing brochure', () => {
  it('says which version it will create and that the live one is untouched', async () => {
    renderPanel();

    fireEvent.click(screen.getByLabelText('An existing brochure'));
    // The trigger stays disabled until the brochures arrive, and a disabled
    // trigger swallows the click without ever opening.
    await waitFor(() => expect(screen.getByRole('combobox')).toBeEnabled());

    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByText('Sorento Catalogue 2026'));

    const note = await screen.findByTestId('dk-fr-reseed-note');
    // max(version)+1, and the published label does not move.
    expect(note).toHaveTextContent('Creates version 8 as a draft');
    expect(note).toHaveTextContent(/live version 4 is untouched/i);
  });

  it('says nothing is published when the brochure has never been published', async () => {
    renderPanel();

    fireEvent.click(screen.getByLabelText('An existing brochure'));
    // The trigger stays disabled until the brochures arrive, and a disabled
    // trigger swallows the click without ever opening.
    await waitFor(() => expect(screen.getByRole('combobox')).toBeEnabled());

    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByText('Draft Only Brochure'));

    expect(await screen.findByTestId('dk-fr-reseed-note')).toHaveTextContent(
      /nothing is published for this brochure yet/i,
    );
  });

  it('sends only the page as the target', async () => {
    seedFromFlyerReading.mockResolvedValue(RESULT);
    renderPanel({ promotionId: 'promo-1', promotionLabel: 'A3 Flyer 2026' });

    fireEvent.click(screen.getByLabelText('An existing brochure'));
    await waitFor(() => expect(screen.getByRole('combobox')).toBeEnabled());
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByText('Sorento Catalogue 2026'));

    fireEvent.click(screen.getByTestId('dk-fr-seed-button'));

    await waitFor(() =>
      expect(seedFromFlyerReading).toHaveBeenCalledWith('r-1', {
        pageId: 'pg-1',
        promotionId: 'promo-1',
        commitMessage: 'Seeded from flyer.pdf',
      }),
    );
  });
});

describe('SeedPanel, creating a new brochure', () => {
  it('sends the name and address, and the promotion the review step chose', async () => {
    seedFromFlyerReading.mockResolvedValue(RESULT);
    renderPanel({ promotionId: 'promo-1', promotionLabel: 'A3 Flyer 2026' });

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'zzt A3 Flyer' } });
    fireEvent.click(screen.getByTestId('dk-fr-seed-button'));

    await waitFor(() =>
      expect(seedFromFlyerReading).toHaveBeenCalledWith('r-1', {
        name: 'zzt A3 Flyer',
        slug: 'zzt-a3-flyer',
        promotionId: 'promo-1',
        commitMessage: 'Seeded from flyer.pdf',
      }),
    );
  });

  it('shows the failure and keeps the form rather than pretending it worked', async () => {
    seedFromFlyerReading.mockRejectedValue(new Error('Address is already taken'));
    renderPanel();

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'zzt A3 Flyer' } });
    fireEvent.click(screen.getByTestId('dk-fr-seed-button'));

    const { toast } = await import('sonner');
    await waitFor(() =>
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith('Address is already taken'),
    );
    expect(screen.getByTestId('dk-fr-seed-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('dk-fr-seed-result')).toBeNull();
  });

  it('replaces the form with the result once the draft exists', async () => {
    seedFromFlyerReading.mockResolvedValue(RESULT);
    renderPanel();

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'zzt A3 Flyer' } });
    fireEvent.click(screen.getByTestId('dk-fr-seed-button'));

    expect(await screen.findByTestId('dk-fr-seed-result')).toBeInTheDocument();
    expect(screen.queryByTestId('dk-fr-seed-panel')).toBeNull();
  });
});

describe('SeedResult', () => {
  it('repeats what did not make it into the brochure', () => {
    render(<SeedResult result={RESULT} />);

    const skipped = screen.getByTestId('dk-fr-result-skipped');
    expect(skipped).toHaveTextContent('2 printed codes did not make it into the brochure');
    expect(skipped).toHaveTextContent('SRTKS7850');
    expect(skipped).toHaveTextContent(/create the products and seed again/i);
  });

  it('says so when nothing was left out, rather than showing nothing', () => {
    render(<SeedResult result={{ ...RESULT, skipped: [] }} />);

    expect(screen.getByTestId('dk-fr-result-nothing-skipped')).toHaveTextContent(
      /every printed code reached a tile/i,
    );
  });

  it('says the draft is a draft and offers the way into the builder', () => {
    render(<SeedResult result={RESULT} />);

    expect(screen.getByText('Draft v1')).toBeInTheDocument();
    expect(screen.getByTestId('dk-fr-seed-result')).toHaveTextContent(/nothing is published/i);
    expect(screen.getByRole('link', { name: /open the draft/i })).toHaveAttribute(
      'href',
      '/dealer-kit/pages/pg-9',
    );
  });

  it('warns that the headings are the first thing to fix', () => {
    render(<SeedResult result={RESULT} />);

    expect(screen.getByTestId('dk-fr-seed-result')).toHaveTextContent(
      /check the headings first/i,
    );
  });

  it('shows what was built without printing an id', () => {
    render(<SeedResult result={RESULT} />);

    const card = screen.getByTestId('dk-fr-seed-result');
    expect(card).toHaveTextContent('3 sections');
    expect(card).toHaveTextContent('9 printed rows');
    expect(card).toHaveTextContent('55 products');
    expect(card.textContent ?? '').not.toMatch(/v-1|pg-9/);
  });
});
