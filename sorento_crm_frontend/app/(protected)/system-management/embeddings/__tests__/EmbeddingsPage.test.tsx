/**
 * LOOKUP-EMBED-CENTRAL slice 5, AC-LEC-23: the Embeddings page (header strip + one CTA, Lookup words / Records switch,
 * list tabs, words grouped by home with a vector dot, Try a phrase table, Records grid). Red before the page exists.
 * Repo pattern (settings/chatbot/page.test.tsx): the hooks module is mocked; hooks are
 * `useEmbeddingsOverview()`, `useLookupWords(list)`, `useTryPhrase()`, `useEmbedMissing()`, `useRecordsBackfill()`.
 * Test hooks the code must expose: each word's vector dot is `data-testid="vector-dot"` with `data-filled="true|false"`.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { GEM, M3S, UUID_RE, lookupWords, overview, tryResult } from './embeddingsStubs';

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
const tryMutation = vi.fn();
const embedMissing = vi.fn();
const backfill = vi.fn();

vi.mock('../hooks/useEmbeddings', () => ({
  useEmbeddingsOverview: () => overviewQuery(),
  useLookupWords: (list: string) => wordsQuery(list),
  useTryPhrase: () => tryMutation(),
  useEmbedMissing: () => embedMissing(),
  useRecordsBackfill: () => backfill(),
}));

import EmbeddingsPage from '../page';

const mutate = vi.fn();
const state = (data: unknown) => ({ data, isLoading: false, isError: false, error: null });

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EmbeddingsPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mutate.mockReset();
  overviewQuery.mockReturnValue(state(overview));
  wordsQuery.mockReturnValue(state(lookupWords));
  tryMutation.mockReturnValue({ mutate, mutateAsync: mutate, data: undefined, isPending: false, reset: vi.fn() });
  embedMissing.mockReturnValue({ mutate, mutateAsync: mutate, isPending: false });
  backfill.mockReturnValue({ mutate, mutateAsync: mutate, isPending: false });
});
afterEach(() => cleanup());

describe('header strip', () => {
  it('shows the embedder model, lookup coverage, record coverage and the search model', () => {
    renderPage();
    expect(screen.getAllByText(new RegExp(GEM)).length).toBeGreaterThan(0);
    expect(screen.getByText(/422\s*\/\s*502/)).toBeInTheDocument();
    expect(screen.getAllByText(new RegExp(M3S)).length).toBeGreaterThan(0);
    expect(screen.getByText(/1,?250/)).toBeInTheDocument(); // record chunks on the new model
  });

  it('has exactly one call to action per mode: Embed missing for lookup words, Start backfill for records', () => {
    renderPage();
    expect(screen.getAllByRole('button', { name: /embed missing/i })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /start backfill/i })).toBeNull();
    fireEvent.click(screen.getByText('Records'));
    expect(screen.getAllByRole('button', { name: /start backfill/i })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /embed missing/i })).toBeNull();
  });

  it('Embed missing fires the embed-missing mutation', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /embed missing/i }));
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('Start backfill sends action start', () => {
    renderPage();
    fireEvent.click(screen.getByText('Records'));
    fireEvent.click(screen.getByRole('button', { name: /start backfill/i }));
    expect(mutate.mock.calls[0][0]).toEqual({ action: 'start' });
  });

  it('shows nothing but a skeleton-safe state while the overview loads', () => {
    overviewQuery.mockReturnValue({ data: undefined, isLoading: true, isError: false, error: null });
    renderPage();
    expect(screen.queryByText(/422\s*\/\s*502/)).toBeNull();
  });
});

describe('lookup words', () => {
  it('lists the list tabs and asks for the clicked list', () => {
    renderPage();
    for (const name of ['Category', 'File type', 'Sales channel', 'Spec', 'Brand', 'Location', 'Salesperson', 'Customer']) {
      expect(screen.getAllByText(name).length).toBeGreaterThan(0);
    }
    fireEvent.click(screen.getAllByText('File type')[0]);
    expect(wordsQuery).toHaveBeenLastCalledWith('file_type');
  });

  it('groups each row\'s words by home', () => {
    renderPage();
    const row = screen.getByText('Water Closet', { selector: '*' }).closest('tr, [role="row"], [data-row]') as HTMLElement;
    expect(row).not.toBeNull();
    const scope = within(row);
    expect(scope.getByText(/^label$/i)).toBeInTheDocument();
    expect(scope.getByText(/alias column/i)).toBeInTheDocument();
    expect(scope.getByText('toilet bowl')).toBeInTheDocument();
    expect(scope.getByText('tandas')).toBeInTheDocument();
    expect(scope.getByText(/^code$/i)).toBeInTheDocument();
  });

  it('shows one vector dot per word, filled when a vector is stored', () => {
    renderPage();
    const dots = screen.getAllByTestId('vector-dot');
    expect(dots).toHaveLength(5);
    expect(dots.filter((d) => d.getAttribute('data-filled') === 'true')).toHaveLength(3);
  });

  it('renders no UUID text', () => {
    renderPage();
    expect(document.body.textContent ?? '').not.toMatch(UUID_RE);
  });
});

describe('try a phrase', () => {
  it('submits the phrase', () => {
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /phrase/i }), { target: { value: 'toilet bowl' } });
    fireEvent.click(screen.getByRole('button', { name: /^try/i }));
    expect(mutate.mock.calls[0][0]).toBe('toilet bowl');
  });

  it('renders the verdict and per row spelling, vector, floors and pass / fail', () => {
    tryMutation.mockReturnValue({ mutate, mutateAsync: mutate, data: tryResult, isPending: false, reset: vi.fn() });
    renderPage();
    expect(screen.getByText(/resolved/i)).toBeInTheDocument();
    const closet = screen.getAllByText('Water Closet').map((n) => n.closest('tr, [role="row"], [data-row]')).find(Boolean) as HTMLElement;
    const row = within(closet);
    expect(row.getByText('0.31')).toBeInTheDocument();
    expect(row.getAllByText(/toilet/).length).toBeGreaterThan(0);
    expect(row.getByText('0.83')).toBeInTheDocument();
    expect(row.getByText('0.6')).toBeInTheDocument(); // the meaning floor
    expect(row.getByText(/pass/i)).toBeInTheDocument();
    expect(screen.getAllByText(/fail/i).length).toBeGreaterThan(0);
  });
});

describe('records', () => {
  it('lists the keep-set sources with their per-model counts', () => {
    renderPage();
    fireEvent.click(screen.getByText('Records'));
    expect(screen.getAllByText(/promotion/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/4,?321/)).toBeInTheDocument();
    expect(screen.getByText(/4,?300/)).toBeInTheDocument();
    expect(screen.getByText(/1,?250/)).toBeInTheDocument();
    expect(screen.getAllByText(/attachment/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/product.?spec/i).length).toBeGreaterThan(0);
    expect(document.body.textContent ?? '').not.toMatch(UUID_RE);
  });
});
