/**
 * The approval queue's contract.
 *
 * SCOPE, stated rather than hidden: the shared `DataGridTable` does not mount
 * its row body under jsdom, so rows, status pills and the empty message are NOT
 * asserted here - they would pass vacuously. This was measured, not assumed:
 * with one edition loaded, the search box and the toolbar button render and
 * `queryByText('Spring 2026')` is still null. `PagesList.test.tsx` carries the
 * same note for the same reason.
 *
 * What IS this component's own: which toolbar action exists, what the query is
 * narrowed to, and what the start dialog sends. That is what is pinned.
 *
 * The decision most likely to be undone by accident, so it leads: **"Start an
 * edition" appears only when a catalogue is in scope.** An Edition belongs to
 * exactly one page, so the whole-queue view has nothing to start one against,
 * and a button that is always visible and 409s half the time is worse than a
 * button that is not there.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const push = vi.fn();
let searchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/editions',
  useSearchParams: () => searchParams,
}));

vi.mock('../../services/editionService', () => ({
  listEditions: vi.fn(),
  createEdition: vi.fn(),
  getEdition: vi.fn(),
  getEditionReview: vi.fn(),
  submitEdition: vi.fn(),
  approveEdition: vi.fn(),
  rejectEdition: vi.fn(),
  reopenEdition: vi.fn(),
  publishEdition: vi.fn(),
}));

import {
  createEdition,
  listEditions,
  type Edition,
  type EditionStatus,
} from '../../services/editionService';
import { EditionsList } from './EditionsList';

const mockList = vi.mocked(listEditions);
const mockCreate = vi.mocked(createEdition);

const LABELS: Record<EditionStatus, string> = {
  draft: 'Draft',
  pending_approval: 'Pending approval',
  approved: 'Approved',
  rejected: 'Rejected',
  done: 'Done',
};

function edition(id: string, status: EditionStatus, extra: Partial<Edition> = {}): Edition {
  return {
    id,
    pageId: 'pg-1',
    pageName: 'Sorento Catalogue 2026',
    name: 'Spring 2026',
    status,
    statusLabel: LABELS[status],
    approvedVersionId: null,
    doneVersionId: null,
    previousEditionId: null,
    submittedAt: null,
    approvedAt: null,
    rejectionReason: null,
    createdAt: '2026-08-01T02:00:00',
    ...extra,
  };
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <EditionsList />
    </QueryClientProvider>,
  );
}

/** The grid only mounts once the queue has resolved. */
const grid = () => screen.findByPlaceholderText(/edition or catalogue/i);

beforeEach(() => {
  vi.clearAllMocks();
  push.mockReset();
  searchParams = new URLSearchParams();
});

describe('EditionsList, before the queue arrives', () => {
  it('shows a skeleton while it loads', () => {
    mockList.mockReturnValue(new Promise(() => {}));

    const { container } = renderList();

    expect(container.querySelector('[data-slot="skeleton"]')).not.toBeNull();
    expect(screen.queryByPlaceholderText(/edition or catalogue/i)).toBeNull();
  });

  it('replaces the grid with the failure rather than showing an empty one', async () => {
    // An error beside a blank grid reads as "no editions", which is a
    // different and much calmer statement than "we could not ask".
    mockList.mockRejectedValue(new Error('Backend unavailable'));

    renderList();

    const alert = await screen.findByTestId('dk-ed-error');
    expect(alert).toHaveTextContent(/could not load editions/i);
    expect(alert).toHaveTextContent(/backend unavailable/i);
    expect(screen.queryByPlaceholderText(/edition or catalogue/i)).toBeNull();
  });
});

describe('EditionsList, scoped to a catalogue or not', () => {
  it('asks for the whole queue and offers no way to start one', async () => {
    mockList.mockResolvedValue([edition('ed-1', 'draft')]);

    renderList();
    await grid();

    expect(mockList).toHaveBeenCalledWith(undefined);
    expect(screen.queryByRole('button', { name: /start an edition/i })).toBeNull();
  });

  it('narrows the query to the catalogue it arrived from', async () => {
    searchParams = new URLSearchParams('pageId=pg-9');
    mockList.mockResolvedValue([]);

    renderList();
    await grid();

    expect(mockList).toHaveBeenCalledWith('pg-9');
    expect(screen.getByRole('button', { name: /start an edition/i })).toBeInTheDocument();
  });
});

describe('EditionsList, starting one', () => {
  beforeEach(() => {
    searchParams = new URLSearchParams('pageId=pg-9');
    mockList.mockResolvedValue([]);
  });

  it('will not start one without a name', async () => {
    renderList();
    await grid();
    fireEvent.click(screen.getByRole('button', { name: /start an edition/i }));

    expect(await screen.findByRole('button', { name: /^start$/i })).toBeDisabled();
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it('sends the trimmed name against the catalogue in scope', async () => {
    mockCreate.mockResolvedValue(edition('ed-new', 'draft'));

    renderList();
    await grid();
    fireEvent.click(screen.getByRole('button', { name: /start an edition/i }));

    fireEvent.change(await screen.findByPlaceholderText('Spring 2027'), {
      target: { value: '  Spring 2027  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^start$/i }));

    // The payload only. React Query v5 hands the mutation function a second
    // context argument, so a whole-call match would be asserting their shape.
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(mockCreate.mock.calls[0][0]).toEqual({ pageId: 'pg-9', name: 'Spring 2027' });
  });

  it('lands on the new edition rather than back on the queue', async () => {
    // The next thing anybody does with a fresh Edition is edit it, so the
    // create closes by navigating instead of by refreshing a list.
    mockCreate.mockResolvedValue(edition('ed-new', 'draft'));

    renderList();
    await grid();
    fireEvent.click(screen.getByRole('button', { name: /start an edition/i }));
    fireEvent.change(await screen.findByPlaceholderText('Spring 2027'), {
      target: { value: 'Spring 2027' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^start$/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith('/dealer-kit/editions/ed-new'));
  });

  it('stays put when the server refuses, so the typed name is not lost', async () => {
    // A 409 means a catalogue already has one open. Closing the dialog on
    // failure would throw away what they typed for no reason.
    mockCreate.mockRejectedValue(new Error('Finish or reject the one in progress'));

    renderList();
    await grid();
    fireEvent.click(screen.getByRole('button', { name: /start an edition/i }));
    fireEvent.change(await screen.findByPlaceholderText('Spring 2027'), {
      target: { value: 'Spring 2027' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^start$/i }));

    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText('Spring 2027')).toHaveValue('Spring 2027');
  });
});
