/**
 * The review step, which is the point of the whole screen (S7.4).
 *
 * The tests are all of the same shape: does the screen tell the truth about
 * what the reader got wrong. A green tick over a report with 38 misses is the
 * failure this slice exists to prevent, so the assertions pin the honesty
 * rather than the layout:
 *
 * - unmatched codes are named as products the brochure will NOT contain
 * - a suggestion is shown with its score and is never applied
 * - dimension candidates are shown with both sizes side by side, and nothing is
 *   written unless somebody ticks a row (the section's own behaviour is pinned
 *   in `DimensionReviewSection.test.tsx`, S7.6)
 * - the section still renders when it is empty, and says so as a good result
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// The shared DataGrid reads the route to key column preferences on it.
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/flyer-readings/r-1',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

// `dismiss` too: Undo now parks a deferred action, and the countdown toast is
// dismissed from an effect when the row settles - a stub without it throws out
// of an effect no assertion here can catch.
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));

// Undo goes through the deferred-action mechanism (D7): mocked at the network
// boundary, same convention `FlyerReadingsList.test.tsx` uses, so the real
// `useDeferredRowAction` hook runs and this file proves what it PARKS rather
// than re-testing the countdown machinery itself.
const { createPendingAction } = vi.hoisted(() => ({
  createPendingAction: vi.fn().mockResolvedValue({
    id: 'pa-1',
    action_key: 'flyer_reading.undo_code_adopt',
    entity_type: 'flyer_code_adoption',
    entity_id: 'r-1:SRTBT1835',
    commit_at: '2026-08-31T00:00:05',
    window_seconds: 5,
  }),
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

// The sizes section can write to the product master now (S7.6), so it asks
// whether this user may - as does the adopt/undo action column below. A single
// controllable flag, so the permission-gating tests can flip it per test
// without a hidden control making every other assertion in this file vacuous.
const { hasPermission } = vi.hoisted(() => ({ hasPermission: { value: true } }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => hasPermission.value,
  useHasAnyPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

import type { MatchReport, PageHeading } from '../../services/flyerReadingService';
import { MatchReportSections } from './MatchReportSections';

const EMPTY: MatchReport = {
  matched: [],
  unmatched: [],
  notPromoted: [],
  dimensionCandidates: [],
  duplicates: {},
  promotionId: null,
};

/** Modelled on the real flyer: the codes and misreads below are its own. */
const FULL: MatchReport = {
  matched: [
    { code: 'SRTWC286-SH', productId: 'p-1', productCode: 'SRTWC286-SH', productName: 'One Piece Water Closet', pages: [1], adopted: false },
    { code: 'SRTBF11620', productId: 'p-2', productCode: 'SRTBF11620', productName: 'Basin Faucet', pages: [2], adopted: false },
  ],
  unmatched: [
    {
      code: 'SRTKS7850',
      pages: [2, 3],
      suggestion: {
        productId: 'p-9',
        productCode: 'SRTKS7851',
        productName: 'Kitchen Sink 850',
        similarity: 0.94,
      },
    },
    { code: 'FG-CW13', pages: [3], suggestion: null },
  ],
  notPromoted: [
    { code: 'SRTBF11620', productId: 'p-2', productCode: 'SRTBF11620', productName: 'Basin Faucet', pages: [2], adopted: false },
  ],
  dimensionCandidates: [
    {
      code: 'SRTWC286-SH',
      productId: 'p-1',
      pages: [1],
      printedLengthMm: 680,
      printedWidthMm: 380,
      printedHeightMm: 760,
      currentLengthMm: 700,
      currentWidthMm: 380,
      currentHeightMm: 760,
      verdict: 'conflicts',
    },
    {
      code: 'SRTBF11620',
      productId: 'p-2',
      pages: [2],
      printedLengthMm: 120,
      printedWidthMm: 50,
      printedHeightMm: 180,
      currentLengthMm: null,
      currentWidthMm: null,
      currentHeightMm: null,
      verdict: 'missing',
    },
  ],
  duplicates: { 'SRTBF11620': [2, 7] },
  promotionId: 'promo-1',
};

/** The fixture flyer's own three pages: page 2 is the known misread. */
const HEADINGS: PageHeading[] = [
  { page: 1, text: 'Inspiring Designs, Exciting Promotions' },
  { page: 2, text: 'Transforming Your' },
  { page: 3, text: 'WATER CLOSET' },
];

/**
 * FULL, plus one adopted code printed on page 1 - EARLIER than both of FULL's
 * own unmatched rows (pages 2 and 3) - so a page-order assertion has to reach
 * past the report's own array boundary to pass.
 */
const WITH_ADOPTED: MatchReport = {
  ...FULL,
  matched: [
    {
      code: 'SRTBT1835',
      productId: 'p-9',
      productCode: 'SRTBT1835-16',
      productName: 'Corner Bathtub 1835',
      pages: [1],
      adopted: true,
    },
    ...FULL.matched,
  ],
};

function renderReport(
  report: MatchReport,
  promotionLabel: string | null = null,
  codeCount = 61,
  headings: PageHeading[] = HEADINGS,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <MatchReportSections
        readingId="r-1"
        report={report}
        codeCount={codeCount}
        promotionLabel={promotionLabel}
        headings={headings}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  hasPermission.value = true;
  createPendingAction.mockClear();
});

describe('MatchReportSections, the counts', () => {
  it('counts what was read, matched, missed and printed twice', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    expect(screen.getByTestId('dk-fr-figure-printed')).toHaveTextContent('61');
    expect(screen.getByTestId('dk-fr-figure-matched')).toHaveTextContent('2');
    expect(screen.getByTestId('dk-fr-figure-unmatched')).toHaveTextContent('2');
    expect(screen.getByTestId('dk-fr-figure-duplicates')).toHaveTextContent('1');
  });

  it('says plainly that unmatched codes will not be in the brochure', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    const warning = screen.getByTestId('dk-fr-unmatched-warning');
    expect(warning).toHaveTextContent('2 of 61 printed codes are not in the product master');
    expect(warning).toHaveTextContent(/will\s+not\s+be in the brochure/i);
  });

  it('does not warn when nothing was missed, which is a real answer', () => {
    renderReport(EMPTY, null, 61);

    expect(screen.queryByTestId('dk-fr-unmatched-warning')).toBeNull();
  });
});

describe('MatchReportSections, codes the master does not have', () => {
  it('lists each one with the pages it was printed on', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    const grid = screen.getByTestId('dk-fr-unmatched-grid');
    expect(within(grid).getByText('SRTKS7850')).toBeInTheDocument();
    // A reviewer is holding the paper, so "somewhere in the flyer" is not a
    // correction anybody can make.
    expect(within(grid).getByText('p. 2, 3')).toBeInTheDocument();
  });

  it('shows a suggestion with its score, and offers no way to apply it', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    const grid = screen.getByTestId('dk-fr-unmatched-grid');
    expect(within(grid).getByText('SRTKS7851')).toBeInTheDocument();
    // The number is the point: a suggestion with nothing behind it reads as a
    // fact, and swapping SRTKS7850 for SRTKS7851 silently is worse than a gap.
    expect(within(grid).getByText('94% alike')).toBeInTheDocument();
    expect(within(grid).queryByRole('button', { name: /apply/i })).toBeNull();
  });

  it('says so rather than leaving a blank when there is nothing close', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    expect(screen.getByText(/nothing close enough to suggest/i)).toBeInTheDocument();
  });

  it('renders the section as a good result when every code resolved', () => {
    renderReport(EMPTY);

    expect(screen.getByText(/every printed code resolved to a product/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing will be dropped from the brochure/i)).toBeInTheDocument();
  });
});

describe('MatchReportSections, the promotion gap', () => {
  it('names the promotion rather than its id', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    const section = document.querySelector('[data-dk-fr-section="not-promoted"]');
    expect(section).not.toBeNull();
    expect(section).toHaveTextContent('A3 Flyer 2026');
    expect(section?.textContent ?? '').not.toMatch(/promo-1/);
  });

  it('still renders with no promotion chosen, and says what to do', () => {
    renderReport({ ...FULL, notPromoted: [] }, null);

    expect(screen.getByText(/no promotion chosen/i)).toBeInTheDocument();
    // A page with no promotion is a finished answer, not a missing one.
    expect(screen.getByText(/list prices to everybody/i)).toBeInTheDocument();
  });

  it('says the promotion carries everything when the gap is empty', () => {
    renderReport({ ...FULL, notPromoted: [] }, 'A3 Flyer 2026');

    expect(screen.getByText(/carries every printed product/i)).toBeInTheDocument();
  });
});

describe('MatchReportSections, sizes', () => {
  it('reports conflicts first, and says only ticked rows are written', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    const section = document.querySelector('[data-dk-fr-section="dimensions"]');
    expect(section).toHaveTextContent('1 of 2 disagree with what the master holds');
    // The promise this screen makes CHANGED with S7.6 and had to change here in
    // the same breath: it used to say nothing is ever written, which stopped
    // being true the moment the section grew an apply. What it may never say is
    // that a row is written without being ticked.
    expect(section).toHaveTextContent(/only the rows you tick are written/i);
  });

  it('shows both sizes side by side so a human can decide which is wrong', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    const grid = screen.getByTestId('dk-fr-dimensions-grid');
    expect(within(grid).getByText('680 x 380 x 760 mm')).toBeInTheDocument();
    expect(within(grid).getByText('700 x 380 x 760 mm')).toBeInTheDocument();
    expect(within(grid).getByText('Disagrees with the master')).toBeInTheDocument();
  });

  it('cannot write anything until a row is ticked', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    // The apply exists, and starts inert. Nothing is preselected, so landing on
    // this screen and clicking the only button on it writes nothing.
    expect(screen.getByTestId('dk-fr-dimensions-apply')).toBeDisabled();
  });

  it('renders the section when no card printed a size', () => {
    renderReport(EMPTY);

    expect(screen.getByText(/no card on this flyer printed a size/i)).toBeInTheDocument();
  });
});

describe('MatchReportSections, what the draft gets wrong', () => {
  it('names the three things the draft will get wrong', () => {
    // The warning, not the lesson. This used to be four bullets explaining how
    // the extractor works, which is a feature explanation inside the UI - the
    // repo's cursor rules ban those. What a reviewer needs before they seed is
    // WHICH things need correcting, and that is what is asserted.
    renderReport(FULL, 'A3 Flyer 2026');

    const gaps = screen.getByTestId('dk-fr-known-gaps');
    expect(gaps).toHaveTextContent(/headings are guessed/i);
    expect(gaps).toHaveTextContent(/no photo until one is chosen/i);
    expect(gaps).toHaveTextContent(/rows\s+split/i);
  });

  it('promises that reading a flyer writes nothing on its own', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    const gaps = screen.getByTestId('dk-fr-known-gaps');
    expect(gaps).toHaveTextContent(/reading a flyer changes no product/i);
    expect(screen.getByRole('link', { name: /choose brochure photos/i })).toHaveAttribute(
      'href',
      '/dealer-kit/brochure-images',
    );
  });

  it('is shown even when the report is clean, because the gaps are not in the report', () => {
    renderReport(EMPTY);

    expect(screen.getByTestId('dk-fr-known-gaps')).toBeInTheDocument();
  });
});

describe('MatchReportSections, what each page will be called', () => {
  it('lists every page in printed order, so the list reads beside the paper', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    const section = screen.getByTestId('dk-fr-headings');
    const text = section.textContent ?? '';
    expect(text).toContain('Page 1');
    expect(text).toContain('Page 2');
    expect(text).toContain('Page 3');
    expect(text.indexOf('Page 1')).toBeLessThan(text.indexOf('Page 2'));
    expect(text.indexOf('Page 2')).toBeLessThan(text.indexOf('Page 3'));
  });

  it('shows the misread heading rather than hiding it', () => {
    // Fixture page 2 is headed "BATHTUB COLLECTION" on the paper and the
    // heuristic reads "Transforming Your". Showing the WRONG value is the point
    // of the section: a reviewer can only correct what they can see.
    renderReport(FULL, 'A3 Flyer 2026');

    expect(screen.getByTestId('dk-fr-headings')).toHaveTextContent('Transforming Your');
  });

  it('says what happens to a page the reader found no heading on', () => {
    renderReport(FULL, 'A3 Flyer 2026', 61, [
      { page: 1, text: null },
      { page: 2, text: 'WATER CLOSET' },
    ]);

    const section = screen.getByTestId('dk-fr-headings');
    expect(section).toHaveTextContent('Page 1');
    expect(section).toHaveTextContent(/no heading found/i);
    expect(section).toHaveTextContent(/named after its page/i);
  });

  it('renders as an empty state rather than a blank block when nothing was read', () => {
    renderReport(EMPTY, null, 0, []);

    expect(screen.getByText(/no pages were read/i)).toBeInTheDocument();
  });
});

describe('MatchReportSections, every section renders', () => {
  it('shows all six sections on an empty report', () => {
    renderReport(EMPTY);

    for (const id of [
      'unmatched',
      'not-promoted',
      'dimensions',
      'duplicates',
      'headings',
      'known-gaps',
    ]) {
      expect(document.querySelector(`[data-dk-fr-section="${id}"]`)).not.toBeNull();
    }
  });

  it('never prints a product id anywhere', () => {
    renderReport(FULL, 'A3 Flyer 2026');

    expect(document.body.textContent ?? '').not.toMatch(/\bp-\d\b/);
  });
});

describe('MatchReportSections, a product named after its own code', () => {
  it('prints the code once rather than twice', () => {
    renderReport(
      {
        ...EMPTY,
        unmatched: [
          {
            code: 'SRTWC8066-S',
            pages: [3],
            suggestion: {
              productId: 'p-7',
              productCode: 'SRTWC8066',
              productName: 'SRTWC8066',
              similarity: 0.91,
            },
          },
        ],
      },
      null,
      41,
    );

    const grid = screen.getByTestId('dk-fr-unmatched-grid');
    // "SRTWC8066 SRTWC8066" reads as a rendering fault, not as a product whose
    // name happens to be its code. Half the live catalogue is named this way.
    expect(within(grid).getAllByText('SRTWC8066')).toHaveLength(1);
    expect(within(grid).getByText('91% alike')).toBeInTheDocument();
  });
});

describe('MatchReportSections, an adopted row (AC-A.9)', () => {
  it('lists the adopted code in the SAME grid as the unmatched ones, in page order', () => {
    renderReport(WITH_ADOPTED, 'A3 Flyer 2026');

    const grid = screen.getByTestId('dk-fr-unmatched-grid');
    expect(within(grid).getByText('SRTBT1835-16')).toBeInTheDocument();
    expect(within(grid).getByText('Adopted')).toBeInTheDocument();

    // Page 1 (the adopted row) comes before page 2 and page 3 (the still
    // unmatched rows) - one grid, printed order, not two separate lists.
    const text = grid.textContent ?? '';
    expect(text.indexOf('SRTBT1835')).toBeGreaterThan(-1);
    expect(text.indexOf('SRTBT1835')).toBeLessThan(text.indexOf('SRTKS7850'));
    expect(text.indexOf('SRTKS7850')).toBeLessThan(text.indexOf('FG-CW13'));
  });

  it('counts codes and how many are adopted in the section header', () => {
    renderReport(WITH_ADOPTED, 'A3 Flyer 2026');

    // 2 still-unmatched + 1 adopted = 3 rows in the grid, 1 of them adopted.
    expect(screen.getByTestId('dk-fr-unmatched-counts')).toHaveTextContent('3 codes, 1 adopted');
  });
});

describe('MatchReportSections, action buttons follow the edit permission', () => {
  it('hides This is... and Undo without the permission, but keeps the adopted state visible', () => {
    hasPermission.value = false;
    renderReport(WITH_ADOPTED, 'A3 Flyer 2026');

    expect(screen.queryByTestId('dk-fr-adopt')).toBeNull();
    expect(screen.queryByTestId('dk-fr-undo')).toBeNull();
    // The row itself - "Adopted as ..." - is not behind the permission.
    expect(screen.getByText('SRTBT1835-16')).toBeInTheDocument();
    expect(screen.getByText('Adopted')).toBeInTheDocument();
  });

  it('shows This is... on unmatched rows and Undo on the adopted one, with the permission', () => {
    hasPermission.value = true;
    renderReport(WITH_ADOPTED, 'A3 Flyer 2026');

    expect(screen.getAllByTestId('dk-fr-adopt').length).toBe(2);
    expect(screen.getByTestId('dk-fr-undo')).toBeInTheDocument();
  });
});

describe('MatchReportSections, undo is a deferred action (D7, not a confirmation dialog)', () => {
  it('parks the undo on the server rather than deleting on the click', async () => {
    renderReport(WITH_ADOPTED, 'A3 Flyer 2026');

    fireEvent.click(screen.getByTestId('dk-fr-undo'));

    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith({
        actionKey: 'flyer_reading.undo_code_adopt',
        entityType: 'flyer_code_adoption',
        entityId: 'r-1:SRTBT1835',
        payload: { reading_id: 'r-1', printed_code: 'SRTBT1835' },
      }),
    );
    // No confirmation dialog stands between the click and the park.
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('disables Undo while its own countdown is counting down', async () => {
    renderReport(WITH_ADOPTED, 'A3 Flyer 2026');

    fireEvent.click(screen.getByTestId('dk-fr-undo'));

    await waitFor(() => expect(screen.getByTestId('dk-fr-undo')).toBeDisabled());
  });
});
