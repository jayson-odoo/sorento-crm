/**
 * Applying the flyer's printed sizes to the product master (S7.6).
 *
 * Written before the component.
 *
 * This is the first control on the review screen that CHANGES anything outside
 * the Kit, so the tests are about restraint rather than function:
 *
 * - nothing is applied that was not ticked, and nothing is ticked by default
 * - a row that disagrees with the master is visibly a different thing from a row
 *   the master has no size for, BEFORE anybody commits
 * - overwriting a value somebody entered is confirmed, and the confirmation
 *   names the value being destroyed
 * - a partial result names every code that did not apply, with its reason. "20
 *   applied" over three silent failures is the outcome this screen must not
 *   produce
 * - somebody without the master-data permission gets no control at all
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

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

const { applyDimensions, hasPermission } = vi.hoisted(() => ({
  applyDimensions: vi.fn(),
  hasPermission: vi.fn(),
}));

vi.mock('../../services/flyerReadingService', () => ({
  applyDimensions,
  getFlyerReading: vi.fn(),
  listFlyerReadings: vi.fn(),
  uploadFlyerReading: vi.fn(),
  deleteFlyerReading: vi.fn(),
  seedFromFlyerReading: vi.fn(),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasPermission(slug),
  useHasAnyPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

import type { DimensionCandidate } from '../../services/flyerReadingService';
import { DimensionReviewSection } from './DimensionReviewSection';

const CONFLICT: DimensionCandidate = {
  code: 'SRTJC8041',
  productId: 'p-1',
  pages: [2],
  printedLengthMm: 1700,
  printedWidthMm: 800,
  printedHeightMm: 590,
  currentLengthMm: 1700,
  currentWidthMm: 800,
  currentHeightMm: 592,
  verdict: 'conflicts',
};

const MISSING: DimensionCandidate = {
  code: 'SRTJC2023',
  productId: 'p-2',
  pages: [2],
  printedLengthMm: 1700,
  printedWidthMm: 850,
  printedHeightMm: 600,
  currentLengthMm: null,
  currentWidthMm: null,
  currentHeightMm: null,
  verdict: 'missing',
};

const AGREES: DimensionCandidate = {
  code: 'SRTJC8037',
  productId: 'p-3',
  pages: [2],
  printedLengthMm: 1600,
  printedWidthMm: 750,
  printedHeightMm: 600,
  currentLengthMm: 1600,
  currentWidthMm: 750,
  currentHeightMm: 600,
  verdict: 'agrees',
};

function renderSection(candidates: DimensionCandidate[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DimensionReviewSection readingId="r-1" candidates={candidates} />
    </QueryClientProvider>,
  );
}

/** The checkbox on the row for `code`, by the code it sits beside. */
function rowCheckbox(code: string): HTMLElement {
  const cell = screen.getByText(code);
  const row = cell.closest('tr');
  if (!row) throw new Error(`no row for ${code}`);
  return within(row as HTMLElement).getByRole('checkbox');
}

beforeEach(() => {
  vi.clearAllMocks();
  hasPermission.mockReturnValue(true);
});

describe('DimensionReviewSection, before anything is applied', () => {
  it('renders the section with an empty state when no card printed a size', () => {
    renderSection([]);

    expect(document.querySelector('[data-dk-fr-section="dimensions"]')).not.toBeNull();
    expect(screen.getByText(/no card on this flyer printed a size/i)).toBeInTheDocument();
  });

  it('shows both sizes side by side and says which disagrees', () => {
    renderSection([CONFLICT, MISSING, AGREES]);

    const grid = screen.getByTestId('dk-fr-dimensions-grid');
    expect(within(grid).getByText('1700 x 800 x 590 mm')).toBeInTheDocument();
    expect(within(grid).getByText('1700 x 800 x 592 mm')).toBeInTheDocument();
    expect(within(grid).getByText('Disagrees with the master')).toBeInTheDocument();
    expect(within(grid).getByText('Master has no size')).toBeInTheDocument();
  });

  it('starts with nothing selected, and cannot apply', () => {
    renderSection([CONFLICT, MISSING]);

    expect(rowCheckbox('SRTJC8041')).not.toBeChecked();
    expect(screen.getByTestId('dk-fr-dimensions-apply')).toBeDisabled();
  });

  it('says how many rows disagree, which is the number that matters', () => {
    renderSection([CONFLICT, MISSING, AGREES]);

    const section = document.querySelector('[data-dk-fr-section="dimensions"]');
    expect(section).toHaveTextContent('1 of 3 disagree with what the master holds');
  });

  it('offers no tick on a row the master already agrees with', () => {
    renderSection([CONFLICT, AGREES]);

    // Nothing to apply, so nothing to select. An enabled tick that silently
    // does nothing is worse than no tick.
    expect(rowCheckbox('SRTJC8037')).toBeDisabled();
    expect(rowCheckbox('SRTJC8041')).toBeEnabled();
  });

  it('never prints a product id', () => {
    renderSection([CONFLICT, MISSING, AGREES]);

    expect(document.body.textContent ?? '').not.toMatch(/\bp-\d\b/);
  });
});

describe('DimensionReviewSection, applying', () => {
  it('writes only the rows that were ticked', async () => {
    applyDimensions.mockResolvedValue({
      applied: [
        {
          code: 'SRTJC2023',
          productCode: 'SRTJC2023',
          productName: 'Bathtub',
          pages: [2],
          lengthMm: 1700,
          widthMm: 850,
          heightMm: 600,
          previousLengthMm: null,
          previousWidthMm: null,
          previousHeightMm: null,
          wasConflict: false,
        },
      ],
      refused: [],
      appliedCount: 1,
      refusedCount: 0,
    });

    renderSection([CONFLICT, MISSING]);

    fireEvent.click(rowCheckbox('SRTJC2023'));
    fireEvent.click(screen.getByTestId('dk-fr-dimensions-apply'));
    fireEvent.click(await screen.findByTestId('dk-fr-dimensions-confirm'));

    await waitFor(() =>
      expect(applyDimensions).toHaveBeenCalledWith('r-1', {
        codes: ['SRTJC2023'],
        // Nothing conflicting was ticked, so nothing is being overwritten and
        // the request must not claim otherwise.
        overwriteConflicts: false,
      }),
    );
  });

  it('confirms before writing, naming what is about to happen', async () => {
    renderSection([MISSING]);

    fireEvent.click(rowCheckbox('SRTJC2023'));
    fireEvent.click(screen.getByTestId('dk-fr-dimensions-apply'));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent(/product master/i);
    expect(dialog).toHaveTextContent('SRTJC2023');
    // Not sent until the confirmation is taken.
    expect(applyDimensions).not.toHaveBeenCalled();
  });

  it('names the value it is about to destroy when a conflict is selected', async () => {
    renderSection([CONFLICT, MISSING]);

    fireEvent.click(rowCheckbox('SRTJC8041'));
    fireEvent.click(screen.getByTestId('dk-fr-dimensions-apply'));

    const dialog = await screen.findByRole('alertdialog');
    // The old value AND the new one, side by side. "This cannot be undone" with
    // no numbers in it is not a decision anybody can make.
    expect(dialog).toHaveTextContent('1700 x 800 x 592 mm');
    expect(dialog).toHaveTextContent('1700 x 800 x 590 mm');
    expect(dialog).toHaveTextContent(/cannot be undone/i);
  });

  it('asks the server to overwrite only when a conflicting row was ticked', async () => {
    applyDimensions.mockResolvedValue({
      applied: [],
      refused: [],
      appliedCount: 0,
      refusedCount: 0,
    });

    renderSection([CONFLICT, MISSING]);

    fireEvent.click(rowCheckbox('SRTJC8041'));
    fireEvent.click(rowCheckbox('SRTJC2023'));
    fireEvent.click(screen.getByTestId('dk-fr-dimensions-apply'));
    fireEvent.click(await screen.findByTestId('dk-fr-dimensions-confirm'));

    await waitFor(() =>
      expect(applyDimensions).toHaveBeenCalledWith('r-1', {
        codes: ['SRTJC8041', 'SRTJC2023'],
        overwriteConflicts: true,
      }),
    );
  });

  it('closes without sending anything when the confirmation is refused', async () => {
    renderSection([MISSING]);

    fireEvent.click(rowCheckbox('SRTJC2023'));
    fireEvent.click(screen.getByTestId('dk-fr-dimensions-apply'));
    fireEvent.click(await screen.findByRole('button', { name: /cancel/i }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(applyDimensions).not.toHaveBeenCalled();
  });
});

describe('DimensionReviewSection, what came back', () => {
  it('reports what applied and what did not, naming every refusal', async () => {
    applyDimensions.mockResolvedValue({
      applied: [
        {
          code: 'SRTJC2023',
          productCode: 'SRTJC2023',
          productName: 'Bathtub',
          pages: [2],
          lengthMm: 1700,
          widthMm: 850,
          heightMm: 600,
          previousLengthMm: null,
          previousWidthMm: null,
          previousHeightMm: null,
          wasConflict: false,
        },
      ],
      refused: [
        {
          code: 'SRTJC8041',
          reason: 'product_not_found',
          message: 'No product in this company carries that code any more.',
        },
      ],
      appliedCount: 1,
      refusedCount: 1,
    });

    renderSection([CONFLICT, MISSING]);

    fireEvent.click(rowCheckbox('SRTJC2023'));
    fireEvent.click(screen.getByTestId('dk-fr-dimensions-apply'));
    fireEvent.click(await screen.findByTestId('dk-fr-dimensions-confirm'));

    const result = await screen.findByTestId('dk-fr-dimensions-result');
    expect(result).toHaveTextContent('1 size written to the product master');
    // The refusals are the point. A screen that shows only the successes is how
    // three products stay wrong forever.
    expect(result).toHaveTextContent('SRTJC8041');
    expect(result).toHaveTextContent('No product in this company carries that code any more.');
  });

  it('does not claim a success when nothing was written', async () => {
    applyDimensions.mockResolvedValue({
      applied: [],
      refused: [
        {
          code: 'SRTJC8041',
          reason: 'conflict_not_confirmed',
          message: 'The product master holds 1700 x 800 x 592 mm.',
        },
      ],
      appliedCount: 0,
      refusedCount: 1,
    });

    renderSection([CONFLICT]);

    fireEvent.click(rowCheckbox('SRTJC8041'));
    fireEvent.click(screen.getByTestId('dk-fr-dimensions-apply'));
    fireEvent.click(await screen.findByTestId('dk-fr-dimensions-confirm'));

    const result = await screen.findByTestId('dk-fr-dimensions-result');
    expect(result).toHaveTextContent('Nothing was written to the product master');
    expect(result).toHaveTextContent('SRTJC8041');
  });

  it('says what went wrong when the request itself failed', async () => {
    applyDimensions.mockRejectedValue(new Error('Permission required: master_data.products.edit'));

    renderSection([MISSING]);

    fireEvent.click(rowCheckbox('SRTJC2023'));
    fireEvent.click(screen.getByTestId('dk-fr-dimensions-apply'));
    fireEvent.click(await screen.findByTestId('dk-fr-dimensions-confirm'));

    const failure = await screen.findByTestId('dk-fr-dimensions-error');
    expect(failure).toHaveTextContent('Permission required: master_data.products.edit');
    // And nothing anywhere says a size was written.
    expect(screen.queryByTestId('dk-fr-dimensions-result')).toBeNull();
  });
});

describe('DimensionReviewSection, without the master-data permission', () => {
  it('offers no way to write, and says why the ticks are missing', () => {
    hasPermission.mockReturnValue(false);

    renderSection([CONFLICT, MISSING]);

    expect(screen.queryByTestId('dk-fr-dimensions-apply')).toBeNull();
    expect(screen.getByTestId('dk-fr-dimensions-readonly')).toHaveTextContent(
      /product master/i,
    );
    // The report itself is still readable: knowing the flyer disagrees is
    // useful to somebody who cannot fix it.
    expect(screen.getByText('Disagrees with the master')).toBeInTheDocument();
  });
});
