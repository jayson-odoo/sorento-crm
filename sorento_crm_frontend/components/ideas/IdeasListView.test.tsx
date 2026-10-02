/**
 * IDEATION-IN-CRM Phase 2 red tests for the Ideas list (AC-C-01..C-06).
 *
 * Real DataGrid, real hooks; the service is the seam. The column-preference hook is stubbed as
 * "loaded" (the pattern every list test here uses) and records the listing key it was given, which
 * is how AC-C-02 (per-user persistence under `ideation.board.view`) is pinned.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
const replace = vi.hoisted(() => vi.fn());
const urlState = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace, prefetch: vi.fn(), back: vi.fn() }),
  usePathname: () => '/ideas',
  useSearchParams: () => new URLSearchParams(urlState.search),
}));

const prefsCalls = vi.hoisted(() => [] as Array<{ listingKey?: string | null }>);
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: (args: { listingKey?: string | null }) => {
    prefsCalls.push({ listingKey: args.listingKey });
    return { resetToDefaults: vi.fn(), isLoading: false };
  },
}));

// Container reads the app-wide SettingsProvider; the page chrome is not under test.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Pat Staff' } }, status: 'authenticated' }),
}));

const svc = vi.hoisted(() => ({
  listIdeas: vi.fn(),
  voteIdea: vi.fn(),
  createIdea: vi.fn(),
  getIdea: vi.fn(),
  getBoard: vi.fn(),
  getMergedChildren: vi.fn(),
  listComments: vi.fn(),
  updateIdea: vi.fn(),
  moveIdeaToStatus: vi.fn(),
  restoreIdea: vi.fn(),
  reorderIdeas: vi.fn(),
  mergeIdeas: vi.fn(),
  unmergeIdea: vi.fn(),
  promoteIdea: vi.fn(),
  uploadAttachment: vi.fn(),
  addComment: vi.fn(),
  editComment: vi.fn(),
  IDEA_STATUS_FILTER_OPTIONS: [
    { value: 'new', label: 'New' },
    { value: 'archived', label: 'Archived' },
  ],
}));
vi.mock('@/services/ideasService', () => svc);

import { formatDate } from '@/lib/helpers';
import { IdeasListView } from './IdeasListView';

function idea(over: Record<string, unknown> = {}) {
  return {
    id: 'idea-1',
    productName: 'Sorento CRM',
    status: 'new',
    statusId: 'st-new',
    statusLabel: 'New',
    statusColor: 'info',
    statusIsArchived: false,
    transitions: [],
    advanceTransitionId: null,
    title: 'Faster quotes',
    problem: 'Quotes take too long',
    proposedSolution: null,
    impact: null,
    department: null,
    rawText: '',
    source: 'manual',
    submitterName: 'Jane Lim',
    upvotes: 3,
    myVote: null,
    priority: 1,
    rank: 1,
    attachments: [],
    createdAt: '2026-07-21T09:05:00Z',
    ideaNumber: 'IDEA-0042',
    mergedIntoId: null,
    mergedInto: null,
    mergedCount: 0,
    ...over,
  };
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IdeasListView />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  urlState.search = '';
  prefsCalls.length = 0;
  svc.listIdeas.mockResolvedValue([idea(), idea({ id: 'idea-2', title: 'Merged child', mergedIntoId: 'idea-1', ideaNumber: 'IDEA-0043' })]);
});

describe('AC-C-01 columns', () => {
  it('shows Votes, Idea, No., Submitter, Channel, Status, Captured and HIDES Product by default', async () => {
    renderList();
    await screen.findByText('Faster quotes');
    for (const title of ['Votes', 'Idea', 'No.', 'Submitter', 'Channel', 'Status', 'Captured']) {
      expect(screen.getByRole('columnheader', { name: new RegExp(title) })).toBeInTheDocument();
    }
    expect(screen.queryByRole('columnheader', { name: /Product/ })).toBeNull();
  });

  it('Product is still available from the Columns menu', async () => {
    renderList();
    await screen.findByText('Faster quotes');
    fireEvent.pointerDown(screen.getByRole('button', { name: /Columns/ }), { button: 0, ctrlKey: false });
    expect(await screen.findByRole('menuitemcheckbox', { name: /Product/ })).toBeInTheDocument();
  });

  it('renders the capture date as dd/MM/yyyy', async () => {
    renderList();
    await screen.findByText('Faster quotes');
    expect(screen.getAllByText(formatDate('2026-07-21T09:05:00Z')).length).toBeGreaterThan(0);
    expect(formatDate('2026-07-21T09:05:00Z')).toMatch(/^\d{2}\/\d{2}\/\d{4}$/);
  });

  it('uses the fixed resizable layout (columns carry explicit widths)', async () => {
    const { container } = renderList();
    await screen.findByText('Faster quotes');
    const table = container.querySelector('table') as HTMLTableElement;
    expect(table.className).toMatch(/table-fixed/);
    const widths = Array.from(table.querySelectorAll('th')).map((th) => th.style.width);
    expect(widths.every((w) => /px$/.test(w))).toBe(true);
  });
});

describe('AC-C-02 column preferences persist per user under ideation.board.view', () => {
  it('the grid persists its columns under the board permission slug', async () => {
    renderList();
    await screen.findByText('Faster quotes');
    expect(prefsCalls.length).toBeGreaterThan(0);
    expect(prefsCalls.every((c) => c.listingKey === 'ideation.board.view')).toBe(true);
  });
});

describe('AC-C-03 vote box', () => {
  it('a click votes through the service and does NOT open the row', async () => {
    svc.voteIdea.mockResolvedValue(idea({ upvotes: 4, myVote: 'up' }));
    renderList();
    await screen.findByText('Faster quotes');
    const [firstVote] = screen.getAllByRole('button', { name: /upvote/i });
    fireEvent.click(firstVote);
    await waitFor(() => expect(svc.voteIdea).toHaveBeenCalledWith('idea-1'));
    expect(push).not.toHaveBeenCalled();
  });

  it('a merged child has a disabled vote box', async () => {
    renderList();
    await screen.findByText('Merged child');
    const row = screen.getByText('Merged child').closest('tr') as HTMLElement;
    expect(within(row).getByRole('button', { name: /upvote/i })).toBeDisabled();
  });

  it('shows the filled state when the viewer has voted', async () => {
    svc.listIdeas.mockResolvedValue([idea({ myVote: 'up' })]);
    renderList();
    await screen.findByText('Faster quotes');
    expect(screen.getByRole('button', { name: /remove your upvote/i })).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('AC-C-04 filters', () => {
  it('lists Archived in the clearable status filter and asks the service for it', async () => {
    renderList();
    await screen.findByText('Faster quotes');
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: 'Archived' }));
    await waitFor(() =>
      expect(svc.listIdeas).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'archived' })),
    );
  });

  it('the first request defaults to active ideas (no status filter)', async () => {
    renderList();
    await screen.findByText('Faster quotes');
    const first = svc.listIdeas.mock.calls[0][0];
    expect(first.status || '').toBe('');
  });
});

describe('AC-C-05 Capture idea', () => {
  it('the header CTA opens a modal with the five fields and no Product picker', async () => {
    renderList();
    await screen.findByText('Faster quotes');
    fireEvent.click(screen.getByRole('button', { name: /Capture idea/ }));
    const dialog = await screen.findByRole('dialog');
    for (const label of ['Problem statement', 'Proposed solution', 'Impact', 'Department', 'Attachments']) {
      expect(within(dialog).getByLabelText(label)).toBeInTheDocument();
    }
    expect(within(dialog).queryByLabelText(/Product/)).toBeNull();
  });

  it('saving without a problem statement shows "Problem statement is required" and calls nothing', async () => {
    renderList();
    await screen.findByText('Faster quotes');
    fireEvent.click(screen.getByRole('button', { name: /Capture idea/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Capture' }));
    expect(await within(dialog).findByText('Problem statement is required')).toBeInTheDocument();
    expect(svc.createIdea).not.toHaveBeenCalled();
  });

  it('saving hands the fields and the dropped files to the service, then the list refreshes', async () => {
    svc.createIdea.mockResolvedValue(idea({ id: 'idea-9', title: 'Brand new' }));
    renderList();
    await screen.findByText('Faster quotes');
    fireEvent.click(screen.getByRole('button', { name: /Capture idea/ }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Problem statement'), { target: { value: 'Brand new problem' } });
    const file = new File(['x'], 'shot.png', { type: 'image/png' });
    fireEvent.change(within(dialog).getByLabelText('Attachments'), { target: { files: [file] } });
    const before = svc.listIdeas.mock.calls.length;
    fireEvent.click(within(dialog).getByRole('button', { name: 'Capture' }));
    await waitFor(() => expect(svc.createIdea).toHaveBeenCalled());
    // react-query hands the mutation function a second (context) argument; only the first is ours.
    expect(svc.createIdea.mock.calls[0][0]).toMatchObject({ problem: 'Brand new problem', files: [file] });
    await waitFor(() => expect(svc.listIdeas.mock.calls.length).toBeGreaterThan(before));
  });
});

describe('AC-C-06 empty and error states', () => {
  it('empty: a heading and a hint, with no button of its own', async () => {
    svc.listIdeas.mockResolvedValue([]);
    renderList();
    expect(await screen.findByText('No ideas yet')).toBeInTheDocument();
    expect(screen.getByText(/Captured ideas appear here/)).toBeInTheDocument();
    const empty = screen.getByText('No ideas yet').parentElement as HTMLElement;
    expect(within(empty).queryByRole('button')).toBeNull();
  });

  it('gateway error: an error state with a Retry that asks again', async () => {
    svc.listIdeas.mockRejectedValueOnce(new Error("The Ideas workspace isn't reachable right now."));
    renderList();
    expect(await screen.findByText("The Ideas workspace isn't reachable right now.")).toBeInTheDocument();
    svc.listIdeas.mockResolvedValue([idea()]);
    fireEvent.click(screen.getByRole('button', { name: /Retry/ }));
    expect(await screen.findByText('Faster quotes')).toBeInTheDocument();
  });
});

describe('AC-C-06 error OR empty, never both', () => {
  it('a gateway error shows the error state and not the empty-state heading', async () => {
    svc.listIdeas.mockRejectedValue(new Error("The Ideas workspace isn't reachable right now."));
    renderList();
    expect(await screen.findByText("The Ideas workspace isn't reachable right now.")).toBeInTheDocument();
    expect(screen.queryByText('No ideas yet')).toBeNull();
  });
});

describe('AC-B-02 the list shows no row actions beyond voting', () => {
  it('has no Edit, Move, Archive or Delete controls in a row', async () => {
    renderList();
    await screen.findByText('Faster quotes');
    const row = screen.getByText('Faster quotes').closest('tr') as HTMLElement;
    const names = within(row)
      .getAllByRole('button')
      .map((b) => b.getAttribute('aria-label') || b.textContent || '');
    expect(names.every((n) => /vote/i.test(n))).toBe(true);
  });
});

describe('IDEATION-CAPTURE My ideas / All ideas toggle', () => {
  const selected = (el: HTMLElement) =>
    el.getAttribute('aria-checked') === 'true' || el.getAttribute('data-state') === 'on';
  const navigated = () =>
    [...push.mock.calls, ...replace.mock.calls].map((c) => String(c[0]));

  it('shows a two-option toggle, All ideas selected, and queries without mine', async () => {
    renderList();
    await screen.findByText('Faster quotes');
    const mine = screen.getByRole('radio', { name: 'My ideas' });
    const all = screen.getByRole('radio', { name: 'All ideas' });
    expect(selected(all)).toBe(true);
    expect(selected(mine)).toBe(false);
    expect(svc.listIdeas.mock.calls[0][0].mine).toBeFalsy();
  });

  it('clicking My ideas re-queries with mine true and puts view=mine in the URL', async () => {
    renderList();
    await screen.findByText('Faster quotes');
    fireEvent.click(screen.getByRole('radio', { name: 'My ideas' }));
    await waitFor(() =>
      expect(svc.listIdeas).toHaveBeenLastCalledWith(expect.objectContaining({ mine: true })),
    );
    expect(navigated().some((u) => u.includes('view=mine'))).toBe(true);
    expect(selected(screen.getByRole('radio', { name: 'My ideas' }))).toBe(true);
  });

  it('with ?view=mine in the URL, My ideas is selected on first render and the first query has mine true', async () => {
    urlState.search = 'view=mine';
    renderList();
    await screen.findByText('Faster quotes');
    expect(selected(screen.getByRole('radio', { name: 'My ideas' }))).toBe(true);
    expect(selected(screen.getByRole('radio', { name: 'All ideas' }))).toBe(false);
    expect(svc.listIdeas.mock.calls[0][0].mine).toBe(true);
  });
});
