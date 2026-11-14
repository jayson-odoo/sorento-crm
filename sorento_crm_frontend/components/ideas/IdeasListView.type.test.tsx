/**
 * WA-COMPLAINT-INTAKE B-1, B-2: the Ideas list has a Type column (Feature request / Issue) and a Type
 * multi-select filter. Harness mirrors IdeasListView.multiFilters.test.tsx. The URL query is not
 * asserted: the list's existing filters are component state and nothing in IdeasListView reads or
 * writes the address bar today (captain to confirm B-2 "address bar" wording).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  usePathname: () => '/ideas',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: vi.fn(() => 'toast-1'),
  dismissDeferredToast: vi.fn(),
}));
const held = new Set<string>();
vi.mock('@/hooks/usePermissions', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, useHasPermission: (slug: string) => held.has(slug) };
});
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Pat Staff' } }, status: 'authenticated' }),
}));
const svc = vi.hoisted(() => ({
  listIdeas: vi.fn(), voteIdea: vi.fn(), createIdea: vi.fn(), getIdea: vi.fn(), getBoard: vi.fn(),
  getMergedChildren: vi.fn(), listComments: vi.fn(), updateIdea: vi.fn(), moveIdeaToStatus: vi.fn(),
  restoreIdea: vi.fn(), reorderIdeas: vi.fn(), mergeIdeas: vi.fn(), unmergeIdea: vi.fn(),
  promoteIdea: vi.fn(), promoteIdeas: vi.fn(), uploadAttachment: vi.fn(), addComment: vi.fn(),
  editComment: vi.fn(),
  IDEA_STATUS_FILTER_OPTIONS: [{ value: 'new', label: 'New' }, { value: 'archived', label: 'Archived' }],
}));
vi.mock('@/services/ideasService', () => svc);
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import { IdeasListView } from './IdeasListView';

function mk(id: string, title: string, type: string | undefined) {
  return {
    id, productName: 'Sorento CRM', status: 'new', statusId: 'st-new', statusLabel: 'ZZT New', statusColor: 'info',
    statusIsArchived: false, transitions: [], advanceTransitionId: null, title, problem: 'p',
    proposedSolution: null, impact: null, department: null, rawText: '', source: 'manual', submitterName: 'Jane Lim',
    upvotes: 0, myVote: null, priority: 1, rank: 1, attachments: [], createdAt: '2026-07-21T09:05:00Z',
    ideaNumber: `IDEA-${id}`, mergedIntoId: null, mergedInto: null, mergedCount: 0,
    ...(type === undefined ? {} : { type }),
  };
}

beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  vi.clearAllMocks();
  held.clear();
  held.add('ideation.board.view');
  svc.listIdeas.mockResolvedValue([
    mk('a', 'ZZT idea A', 'idea'),
    mk('b', 'ZZT idea B', 'issue'),
    mk('c', 'ZZT idea C', undefined),
    mk('d', 'ZZT idea D', 'issue'),
  ]);
});
afterEach(() => cleanup());

async function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <IdeasListView />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT idea A');
}
const shown = () => ['A', 'B', 'C', 'D'].filter((k) => screen.queryByText(`ZZT idea ${k}`) !== null).join('');
const rowOf = (t: string) => screen.getByText(t).closest('tr') as HTMLElement;
const rowTitles = () =>
  Array.from(document.querySelectorAll('tbody tr'))
    .map((r) => /ZZT idea [A-D]/.exec(r.textContent ?? '')?.[0] ?? '')
    .filter(Boolean);
async function typeBox(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /^filters/i }));
  const boxes = await screen.findAllByRole('listbox');
  const found = boxes.find((b) => within(b).queryByText('Feature request'));
  if (!found) throw new Error('no Type multi control offers Feature request');
  return found as HTMLSelectElement;
}

describe('B-1 Type column', () => {
  it('has a Type header and shows Feature request / Issue per row, missing type reading Feature request', async () => {
    await open();
    const titles = Array.from(document.querySelectorAll('table th')).map((th) => th.textContent?.trim());
    expect(titles).toContain('Type');
    expect(within(rowOf('ZZT idea A')).getByText('Feature request')).toBeInTheDocument();
    expect(within(rowOf('ZZT idea B')).getByText('Problem report')).toBeInTheDocument();
    expect(within(rowOf('ZZT idea C')).getByText('Feature request')).toBeInTheDocument();
  });

  it('is one line (truncate, no wrapping)', async () => {
    await open();
    const cell = within(rowOf('ZZT idea B')).getByText('Problem report');
    const cls = `${cell.className} ${cell.parentElement?.className ?? ''}`;
    expect(cls).toMatch(/truncate|whitespace-nowrap/);
  });

  it('the Type header sorts by the label: Feature request before Issue, then reversed', async () => {
    await open();
    const header = screen.getByRole('button', { name: 'Type' });
    fireEvent.click(header);
    expect(rowTitles().slice(-2).sort()).toEqual(['ZZT idea B', 'ZZT idea D']);
    expect(rowTitles().slice(0, 2).sort()).toEqual(['ZZT idea A', 'ZZT idea C']);
    fireEvent.click(header);
    expect(rowTitles().slice(0, 2).sort()).toEqual(['ZZT idea B', 'ZZT idea D']);
  });
});

describe('B-2 Type multi-select filter', () => {
  it('offers Feature request and Issue as a multi control', async () => {
    const user = userEvent.setup();
    await open();
    const box = await typeBox(user);
    expect(box.hasAttribute('multiple')).toBe(true);
    expect(within(box).getByText('Problem report')).toBeInTheDocument();
  });

  it('ticking Issue shows only issues', async () => {
    const user = userEvent.setup();
    await open();
    await user.selectOptions(await typeBox(user), ['issue']);
    await waitFor(() => expect(shown()).toBe('BD'));
  });

  it('ticking Feature request shows ideas, including ones with no type data', async () => {
    const user = userEvent.setup();
    await open();
    await user.selectOptions(await typeBox(user), ['idea']);
    await waitFor(() => expect(shown()).toBe('AC'));
  });

  it('ticking both shows all', async () => {
    const user = userEvent.setup();
    await open();
    await user.selectOptions(await typeBox(user), ['idea', 'issue']);
    await waitFor(() => expect(shown()).toBe('ABCD'));
  });

  it('combines with the search filter', async () => {
    const user = userEvent.setup();
    await open();
    await user.selectOptions(await typeBox(user), ['issue']);
    await waitFor(() => expect(shown()).toBe('BD'));
    await user.type(screen.getByPlaceholderText(/search/i), 'idea B');
    await waitFor(() => expect(shown()).toBe('B'));
  });
});
