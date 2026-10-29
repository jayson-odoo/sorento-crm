/**
 * LOOKUP-EMBED-CENTRAL review fix round 1, screen side (F-9, F-13). Red before the fixes.
 * Assumed contract: the overview carries `guard.running` (a backfill job is running now) for the Stop button.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { lookupWords, overview } from './embeddingsStubs';

vi.mock('next/navigation', () => ({
  usePathname: () => '/system-management/embeddings',
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

const overviewQuery = vi.fn();
const wordsQuery = vi.fn();
const mutate = vi.fn();
vi.mock('../hooks/useEmbeddings', () => ({
  useEmbeddingsOverview: () => overviewQuery(),
  useLookupWords: (list: string) => wordsQuery(list),
  useTryPhrase: () => ({ mutate, mutateAsync: mutate, data: undefined, isPending: false, reset: vi.fn() }),
  useEmbedMissing: () => ({ mutate, mutateAsync: mutate, isPending: false }),
  useRecordsBackfill: () => ({ mutate, mutateAsync: mutate, isPending: false }),
}));

import EmbeddingsPage from '../page';

const ok = (data: unknown) => ({ data, isLoading: false, isError: false, error: null });
const withRunning = (running: boolean) => ({ ...overview, guard: { ...overview.guard, running } });

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EmbeddingsPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mutate.mockReset();
  overviewQuery.mockReturnValue(ok(withRunning(false)));
  wordsQuery.mockReturnValue(ok(lookupWords));
});
afterEach(() => cleanup());

describe('Stop', () => {
  it('shows only while a backfill is running', () => {
    renderPage();
    fireEvent.click(screen.getByText('Records'));
    expect(screen.queryByRole('button', { name: /^stop$/i })).toBeNull();
    cleanup();
    overviewQuery.mockReturnValue(ok(withRunning(true)));
    renderPage();
    fireEvent.click(screen.getByText('Records'));
    expect(screen.getByRole('button', { name: /^stop$/i })).toBeInTheDocument();
  });
});

describe('overview failure', () => {
  it('shows the error instead of an endless skeleton', () => {
    overviewQuery.mockReturnValue({ data: undefined, isLoading: false, isError: true, error: new Error('Overview boom') });
    renderPage();
    expect(screen.getByText(/overview boom/i)).toBeInTheDocument();
  });
});

describe('lookup words grid', () => {
  it('shows the row label in the Row cell even when the label is also one of its words', () => {
    renderPage();
    // the word chip has no title; the Row cell carries the label as its title
    expect(screen.getAllByTitle('Water Closet').length).toBeGreaterThan(0);
  });
});

describe('tabs', () => {
  it('switch with the keyboard, not only by click', () => {
    renderPage();
    const lookup = screen.getByRole('tab', { name: 'Lookup words' });
    lookup.focus();
    fireEvent.keyDown(lookup, { key: 'ArrowRight' });
    expect(screen.getByRole('button', { name: /start backfill/i })).toBeInTheDocument();
  });
});
