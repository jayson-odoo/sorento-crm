/**
 * FILTER-MULTISELECT PR2: the Ideas list's Status, Submitter and Channel filters take several values
 * and filter in the browser: two values show the ideas matching either and hide the rest (OR within a
 * filter), the filters AND across each other, and clearing restores every idea. Harness mirrors
 * IdeasListView.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
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

function idea(id: string, title: string, statusLabel: string, submitterName: string, source: string) {
  return {
    id, productName: 'Sorento CRM', status: 'new', statusId: `st-${statusLabel}`, statusLabel, statusColor: 'info',
    statusIsArchived: false, transitions: [], advanceTransitionId: null, title, problem: 'p',
    proposedSolution: null, impact: null, department: null, rawText: '', source, submitterName, upvotes: 0,
    myVote: null, priority: 1, rank: 1, attachments: [], createdAt: '2026-07-21T09:05:00Z',
    ideaNumber: `IDEA-${id}`, mergedIntoId: null, mergedInto: null, mergedCount: 0,
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
    idea('a', 'ZZT idea A', 'ZZT New', 'Jane Lim', 'manual'),
    idea('b', 'ZZT idea B', 'ZZT Review', 'Ben Tan', 'email'),
    idea('c', 'ZZT idea C', 'ZZT Done', 'Cy Ong', 'web'),
    idea('d', 'ZZT idea D', 'ZZT New', 'Ben Tan', 'whatsapp'),
  ]);
});
afterEach(() => cleanup());

async function open(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <IdeasListView />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT idea A');
  await user.click(screen.getByRole('button', { name: /^filters/i }));
}
/** The multi control that carries this option text. */
const boxWith = async (option: string) => {
  const boxes = await screen.findAllByRole('listbox');
  const found = boxes.find((b) => within(b).queryByText(option));
  if (!found) throw new Error(`no multi control offers ${option}`);
  return found as HTMLSelectElement;
};
/** Status sits in the toolbar; picking there dismisses the non-modal Filters menu, so reopen it. */
async function inFilters(user: ReturnType<typeof userEvent.setup>, option: string) {
  if (!screen.queryAllByRole('listbox').some((b) => within(b).queryByText(option))) {
    await user.click(screen.getByRole('button', { name: /^filters/i }));
  }
  return boxWith(option);
}
const shown = () => ['A', 'B', 'C', 'D'].filter((k) => screen.queryByText(`ZZT idea ${k}`) !== null).join('');

describe('Ideas - multi Status, Submitter and Channel filters', () => {
  it('are three multi controls', async () => {
    const user = userEvent.setup();
    await open(user);
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(3);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two statuses show the ideas of either status', async () => {
    const user = userEvent.setup();
    await open(user);
    await user.selectOptions(await boxWith('ZZT Review'), ['ZZT New', 'ZZT Review']);
    await waitFor(() => expect(shown()).toBe('ABD'));
  });

  it('two submitters show the ideas of either person', async () => {
    const user = userEvent.setup();
    await open(user);
    await user.selectOptions(await boxWith('Cy Ong'), ['Jane Lim', 'Cy Ong']);
    await waitFor(() => expect(shown()).toBe('AC'));
  });

  it('two channels show the ideas of either channel', async () => {
    const user = userEvent.setup();
    await open(user);
    await user.selectOptions(await boxWith('Email'), ['manual', 'email']);
    await waitFor(() => expect(shown()).toBe('AB'));
  });

  it('the filters AND across each other', async () => {
    const user = userEvent.setup();
    await open(user);
    await user.selectOptions(await boxWith('ZZT Review'), ['ZZT New', 'ZZT Review']);
    await user.selectOptions(await inFilters(user, 'Email'), ['manual', 'email']);
    await waitFor(() => expect(shown()).toBe('AB'));
    await user.selectOptions(await inFilters(user, 'Cy Ong'), ['Ben Tan']);
    await waitFor(() => expect(shown()).toBe('B'));
  });

  it('clearing the filters restores every idea', async () => {
    const user = userEvent.setup();
    await open(user);
    await user.selectOptions(await boxWith('Email'), ['manual', 'email']);
    await waitFor(() => expect(shown()).toBe('AB'));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(shown()).toBe('ABCD'));
  });
});
