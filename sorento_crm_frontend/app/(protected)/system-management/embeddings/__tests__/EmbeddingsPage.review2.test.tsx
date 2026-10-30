/** LOOKUP-EMBED-CENTRAL review fix round 2 (G-6): the Row label is real text, not CSS generated content. */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
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
const ok = (data: unknown) => ({ data, isLoading: false, isError: false, error: null });
const mutate = vi.fn();
vi.mock('../hooks/useEmbeddings', () => ({
  useEmbeddingsOverview: () => ok({ ...overview, guard: { ...overview.guard, running: false } }),
  useLookupWords: () => ok(lookupWords),
  useTryPhrase: () => ({ mutate, mutateAsync: mutate, data: undefined, isPending: false, reset: vi.fn() }),
  useEmbedMissing: () => ({ mutate, mutateAsync: mutate, isPending: false }),
  useRecordsBackfill: () => ({ mutate, mutateAsync: mutate, isPending: false }),
}));

import EmbeddingsPage from '../page';

beforeEach(() => mutate.mockReset());
afterEach(() => cleanup());

describe('lookup words grid', () => {
  it('draws the Row label as text, so it is found once in the Row cell and once as the label word', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <EmbeddingsPage />
      </QueryClientProvider>,
    );
    // "Water Closet" is both the row label and one of its words (a chip): two real text nodes
    expect(screen.getAllByText('Water Closet').length).toBeGreaterThanOrEqual(2);
  });
});
