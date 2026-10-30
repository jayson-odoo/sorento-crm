/** LOOKUP-EMBED-CENTRAL slice 5: the Settings tab strip gains an "Embeddings" tab (red before layout.tsx lists it). */
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/settings/embeddings',
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import Layout from './layout';

afterEach(() => cleanup());

describe('Settings tab strip', () => {
  it('lists an Embeddings tab', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({ settings: { id: 's1', name: 'Sorento' }, roles: [] }) });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Layout>
          <div>child</div>
        </Layout>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('tab', { name: 'Embeddings' })).toBeInTheDocument();
  });
});
