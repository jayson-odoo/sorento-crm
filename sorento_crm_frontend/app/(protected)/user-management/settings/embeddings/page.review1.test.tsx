/** LOOKUP-EMBED-CENTRAL review fix round 1: Settings > Embeddings prefill (F-13) and the coverage rows on a 403 (F-9). */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { GEM, overview } from '../../../system-management/embeddings/__tests__/embeddingsStubs';

vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/settings/embeddings',
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));
const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import EmbeddingsSettingsPage from './page';

const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) });
// a settings row that never set the embedder: the resolved one (label fallback) is only on the overview
const unsetSettings = {
  settings: { id: 's1', name: 'Sorento', embedding_provider: null, embedding_model: null, embedding_records_search_model: null, embedding_backfill_rpm: null },
  roles: [],
};

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EmbeddingsSettingsPage />
    </QueryClientProvider>,
  );
}

afterEach(() => cleanup());

describe('prefill', () => {
  beforeEach(() => {
    apiFetch.mockReset();
    apiFetch.mockImplementation(async (url: string) =>
      String(url).includes('/system/embeddings/overview') ? json(overview) : json(unsetSettings),
    );
  });

  it('shows the resolved embedder when the setting itself is empty, not an OpenAI default', async () => {
    renderPage();
    expect((await screen.findAllByText(new RegExp(GEM))).length).toBeGreaterThan(0);
    expect(screen.queryByText(/text-embedding-3-small/)).toBeNull();
  });
});

describe('a caller who cannot read the overview', () => {
  beforeEach(() => {
    apiFetch.mockReset();
    apiFetch.mockImplementation(async (url: string) =>
      String(url).includes('/system/embeddings/overview')
        ? { ok: false, status: 403, json: async () => ({ detail: 'Forbidden' }), text: async () => 'Forbidden' }
        : json({ settings: { id: 's1', name: 'Sorento', embedding_provider: 'gemini', embedding_model: GEM, embedding_backfill_rpm: 20 }, roles: [] }),
    );
  });

  it('still gets the form and sees no coverage rows', async () => {
    renderPage();
    expect(await screen.findByRole('spinbutton', { name: /rpm|backfill/i })).toBeInTheDocument();
    expect(screen.queryByText(/422\s*\/\s*502/)).toBeNull();
    expect(screen.queryByText(/forbidden/i)).toBeNull();
  });
});
