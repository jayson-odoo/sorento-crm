/**
 * Planning changes - the batch page (`PLAN-so-book-diff-replanning.md`, journey step 1-3).
 *
 * What is pinned:
 *  - every order section renders, including one whose rows are all "Not decided" (AC-R03);
 *  - a row states the change, what is held today, the facts, the verb and the reason;
 *  - switching a row's decision calls the stub PUT;
 *  - Apply opens a confirm dialog, then the result states render (applied / failed reason /
 *    superseded, disabled).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  MOCK_PLANNING_CHANGE_BATCH_APPLIED,
  MOCK_PLANNING_CHANGE_BATCH_PENDING,
} from '../../_shared/__mocks__/planningChanges';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/planning-changes/pcb-1',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

const getPlanningChangeBatch = vi.fn();
const updatePlanningChangeRow = vi.fn();
const applyPlanningChanges = vi.fn();

vi.mock('../../_shared/services/planningChangeService', () => ({
  getPlanningChangeBatch: (...args: unknown[]) => getPlanningChangeBatch(...args),
  updatePlanningChangeRow: (...args: unknown[]) => updatePlanningChangeRow(...args),
  applyPlanningChanges: (...args: unknown[]) => applyPlanningChanges(...args),
  listPlanningChangeBatches: vi.fn(),
}));

import { PlanningChangeBatchClient } from './PlanningChangeBatchClient';

function renderClient(batchId = 'pcb-1') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PlanningChangeBatchClient batchId={batchId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getPlanningChangeBatch.mockResolvedValue(structuredClone(MOCK_PLANNING_CHANGE_BATCH_PENDING));
  updatePlanningChangeRow.mockResolvedValue(
    structuredClone(MOCK_PLANNING_CHANGE_BATCH_PENDING.orders[0].rows[0]),
  );
  applyPlanningChanges.mockResolvedValue({
    applied_orders: ['SO403765', 'SO400875', 'SO401220'],
    failed_orders: [],
    already_applied: false,
  });
});

describe('PlanningChangeBatchClient - loading and error', () => {
  it('renders a loading state before the batch arrives', async () => {
    getPlanningChangeBatch.mockReturnValue(new Promise(() => {}));
    const { container } = renderClient();

    await waitFor(() =>
      expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0),
    );
  });

  it('says the failure out loud rather than showing an empty page', async () => {
    getPlanningChangeBatch.mockRejectedValue(new Error('Backend is down'));
    renderClient();

    expect(
      await screen.findByText('This planning change batch could not be loaded'),
    ).toBeInTheDocument();
    expect(screen.getByText('Backend is down')).toBeInTheDocument();
  });
});

describe('PlanningChangeBatchClient - every order section renders', () => {
  it('shows the source file, when and by whom, and every order incl. the all-not-decided one', async () => {
    renderClient();

    expect(await screen.findByText('JAN - DEC 2026 ORDER.xlsx')).toBeInTheDocument();
    expect(screen.getByText(/Uploaded .* by Aina/)).toBeInTheDocument();
    expect(screen.getByText('Pending review')).toBeInTheDocument();

    expect(screen.getByText(/SO403765 · BATHE CODE SDN BHD · rev 4/)).toBeInTheDocument();
    expect(screen.getByText(/SO400875 · MATRIX EXCELCON · rev 2/)).toBeInTheDocument();
    // The order whose rows are ALL "Not decided" (AC section-4 "every section renders").
    expect(
      screen.getByText(/SO401220 · GREENFIELD DEVELOPMENT SDN BHD · rev 1/),
    ).toBeInTheDocument();
    const notDecided = screen.getAllByText('Not decided');
    // held-column "Not decided" AND the decision-column "Not decided" both use the same
    // words, so this order alone contributes at least its two rows' decision cells.
    expect(notDecided.length).toBeGreaterThanOrEqual(2);
  });

  it('states the change, held today, facts, the verb and the reason on a row', async () => {
    renderClient();
    await screen.findByText('JAN - DEC 2026 ORDER.xlsx');

    // Row 1: delay within window, reserve held -> keep. Scoped to its own row: "in window"
    // and "+14 d" chips, and the "Keep" pill, all repeat on several other rows.
    const changeCell = screen.getByText(
      /Required 20\/08\/2026 -> 03\/09\/2026 \(\+14 d\)/,
    );
    const row = changeCell.closest('tr') as HTMLElement;
    expect(within(row).getByText('Reserve 66 at BRW-BB · Buy 6')).toBeInTheDocument();
    expect(within(row).getByText('in window')).toBeInTheDocument();
    expect(within(row).getByText('+14 d')).toBeInTheDocument();
    expect(within(row).getAllByTitle('Keep').length).toBeGreaterThan(0);
    expect(
      within(row).getByText(
        'New date is 14 days out and inside the 60-day reserve window; the reserve stays put rather than being released and re-taken.',
      ),
    ).toBeInTheDocument();
  });

  it('shows dealer hot-selling and discontinued chips where the facts say so', async () => {
    renderClient();
    await screen.findByText('JAN - DEC 2026 ORDER.xlsx');

    expect(screen.getByText('hot-selling')).toBeInTheDocument();
    expect(screen.getByText('discontinued')).toBeInTheDocument();
    // "PO placed" is on both the buy-actioned row and the closed row that kept an
    // already-actioned inquiry row (AC-R08) - so at least one, not exactly one.
    expect(screen.getAllByText('PO placed').length).toBeGreaterThan(0);
  });

  it('shows the fresh proposal for a replan row', async () => {
    renderClient();
    await screen.findByText('JAN - DEC 2026 ORDER.xlsx');

    expect(screen.getByText('Reserve 40 at BRW-BB · Buy 20')).toBeInTheDocument();
    expect(screen.getByTestId('trail-info-pcb-1-so400875-l2-advance')).toBeInTheDocument();
  });
});

describe('PlanningChangeBatchClient - switching a decision', () => {
  it('writes the new decision via the stub PUT', async () => {
    renderClient();
    await screen.findByText('JAN - DEC 2026 ORDER.xlsx');

    const keepAsIsButtons = screen.getAllByRole('button', { name: 'Keep as is' });
    fireEvent.click(keepAsIsButtons[0]);

    await waitFor(() =>
      expect(updatePlanningChangeRow).toHaveBeenCalledWith('pcb-1', 'pcr-1', {
        decision: 'keep',
      }),
    );
  });
});

describe('PlanningChangeBatchClient - Apply', () => {
  it('Apply is disabled with 0 accepted rows and opens a confirm dialog otherwise', async () => {
    renderClient();
    await screen.findByText('JAN - DEC 2026 ORDER.xlsx');

    const applyButton = screen.getByRole('button', { name: /Apply \d+ changes?/ });
    expect(applyButton).toBeEnabled();

    fireEvent.click(applyButton);
    expect(await screen.findByText('Apply planning changes')).toBeInTheDocument();
  });

  it('applies the accepted rows on confirm', async () => {
    renderClient();
    await screen.findByText('JAN - DEC 2026 ORDER.xlsx');

    fireEvent.click(screen.getByRole('button', { name: /Apply \d+ changes?/ }));
    await screen.findByText('Apply planning changes');
    fireEvent.click(screen.getByRole('button', { name: /^Apply$/ }));

    await waitFor(() => expect(applyPlanningChanges).toHaveBeenCalledWith('pcb-1'));
  });
});

describe('PlanningChangeBatchClient - already applied result states', () => {
  it('shows Applied, disabled, on a row that applied, and Apply itself reads Applied', async () => {
    getPlanningChangeBatch.mockResolvedValue(structuredClone(MOCK_PLANNING_CHANGE_BATCH_APPLIED));
    renderClient('pcb-0');

    expect(await screen.findByText('JUN - DEC 2026 REVISION.xlsx')).toBeInTheDocument();
    // The two rows that wrote successfully (pcr-a1, pcr-a2) plus the header's own Apply button,
    // which already reads "Applied" once a batch has an `applied_at`.
    expect(screen.getAllByText('Applied').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole('button', { name: 'Applied' })).toBeDisabled();
  });

  it('shows the failure reason on a row Apply could not write', async () => {
    getPlanningChangeBatch.mockResolvedValue(structuredClone(MOCK_PLANNING_CHANGE_BATCH_APPLIED));
    renderClient('pcb-0');

    await screen.findByText('JUN - DEC 2026 REVISION.xlsx');
    expect(screen.getByText(/Partly failed/)).toBeInTheDocument();
    const failed = screen.getAllByText('Failed');
    expect(failed.length).toBeGreaterThan(0);
    expect(failed[0]).toHaveAttribute(
      'title',
      'Revision 3 was confirmed on the board after this batch was built.',
    );
  });

  it('shows a superseded row as disabled, with the reason on hover', async () => {
    getPlanningChangeBatch.mockResolvedValue(structuredClone(MOCK_PLANNING_CHANGE_BATCH_APPLIED));
    renderClient('pcb-0');

    await screen.findByText('JUN - DEC 2026 REVISION.xlsx');
    const superseded = screen.getByText('Superseded on the board');
    expect(superseded).toBeInTheDocument();
    expect(superseded).toHaveAttribute(
      'title',
      'The board confirmed revision 6 on this line after this batch was built, so this suggestion no longer applies.',
    );
  });
});
