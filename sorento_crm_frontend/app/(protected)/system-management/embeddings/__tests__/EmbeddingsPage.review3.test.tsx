/** LOOKUP-EMBED-CENTRAL review fix round 3, H-5: the header's record-coverage label is short, the full model is in the title. */
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { GEM, lookupWords, overview } from './embeddingsStubs';

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

afterEach(() => cleanup());

describe('header strip', () => {
  it('labels record coverage with a short text and puts the full model name in the title', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <EmbeddingsPage />
      </QueryClientProvider>,
    );
    const label = screen.getByText(/^Record chunks/i);
    expect(label.textContent ?? '').not.toContain(GEM);
    expect((label.textContent ?? '').length).toBeLessThanOrEqual(24);
    const title = label.getAttribute('title') ?? label.closest('[title]')?.getAttribute('title') ?? '';
    expect(title).toContain(GEM);
  });
});
