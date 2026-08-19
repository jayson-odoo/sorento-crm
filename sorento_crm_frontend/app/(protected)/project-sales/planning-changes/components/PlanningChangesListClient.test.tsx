/**
 * Planning changes - the list (AC-R10). Every batch, newest first, with a filter for
 * pending / applied and an empty state naming where a batch is born.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MOCK_PLANNING_CHANGE_BATCHES } from '../../_shared/__mocks__/planningChanges';
import type { PlanningChangeBatchSummary } from '../../_shared/types/planningChange.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/planning-changes',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const listPlanningChangeBatches = vi.fn();
vi.mock('../../_shared/services/planningChangeService', () => ({
  listPlanningChangeBatches: (...args: unknown[]) => listPlanningChangeBatches(...args),
  getPlanningChangeBatch: vi.fn(),
  updatePlanningChangeRow: vi.fn(),
  applyPlanningChanges: vi.fn(),
}));

import { PlanningChangesListClient } from './PlanningChangesListClient';

function envelope(rows: PlanningChangeBatchSummary[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
}

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PlanningChangesListClient />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listPlanningChangeBatches.mockResolvedValue(envelope(MOCK_PLANNING_CHANGE_BATCHES));
});

/** The state pill on a row, never the tab button or the column's own sort-header text. */
function statePill(text: string): HTMLElement {
  const match = screen
    .getAllByText(text)
    .find((el) => el.closest('[data-slot="badge"]'));
  if (!match) throw new Error(`No "${text}" badge found`);
  return match;
}

describe('PlanningChangesListClient - rows', () => {
  it('lists every batch with its file, uploader, counts and state', async () => {
    renderClient();

    expect(await screen.findByText('JAN - DEC 2026 ORDER.xlsx')).toBeInTheDocument();
    expect(screen.getByText('JUN - DEC 2026 REVISION.xlsx')).toBeInTheDocument();
    expect(screen.getByText('Aina')).toBeInTheDocument();
    expect(screen.getByText('Ravi')).toBeInTheDocument();
    // The trigger is visible in the list too - what got uploaded, not just its file name.
    expect(screen.getAllByText('SO book upload').length).toBe(2);
    expect(statePill('Pending')).toBeInTheDocument();
    expect(statePill('Partly failed')).toBeInTheDocument();
  });

  it('goes to the batch page on row click', async () => {
    renderClient();
    const row = (await screen.findByText('JAN - DEC 2026 ORDER.xlsx')).closest('tr');
    expect(row).not.toBeNull();

    fireEvent.click(row as HTMLElement);

    expect(push).toHaveBeenCalledWith('/project-sales/planning-changes/pcb-1');
  });
});

describe('PlanningChangesListClient - filter', () => {
  it('sends the state tab to the service', async () => {
    renderClient();
    await screen.findByText('JAN - DEC 2026 ORDER.xlsx');

    const stateNav = screen.getByRole('navigation', { name: 'State' });
    fireEvent.click(within(stateNav).getByRole('button', { name: 'Applied' }));

    await waitFor(() =>
      expect(listPlanningChangeBatches).toHaveBeenCalledWith(
        expect.objectContaining({ state: 'applied' }),
      ),
    );
  });
});

describe('PlanningChangesListClient - empty state', () => {
  it('names where a batch is born', async () => {
    listPlanningChangeBatches.mockResolvedValue(envelope([]));
    renderClient();

    expect(await screen.findByText('No planning changes yet')).toBeInTheDocument();
    expect(
      screen.getByText(
        'A re-uploaded sales order book that moves a planned line will appear here.',
      ),
    ).toBeInTheDocument();
  });
});

describe('PlanningChangesListClient - error state', () => {
  it('says the failure out loud', async () => {
    listPlanningChangeBatches.mockRejectedValue(new Error('Backend is down'));
    renderClient();

    expect(await screen.findByText('Planning changes could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('Backend is down')).toBeInTheDocument();
  });
});
