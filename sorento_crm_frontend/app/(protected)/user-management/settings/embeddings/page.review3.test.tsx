/**
 * LOOKUP-EMBED-CENTRAL review fix round 3, H-4: the Settings tab's Record search row reads the overview's
 * records_search_model (also when the settings blob's column is NULL), and the save toast says when a records backfill
 * was started. Red before the fixes.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { GEM, M3S, overview } from '../../../system-management/embeddings/__tests__/embeddingsStubs';

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

import { toast } from '@/lib/toast';
import EmbeddingsSettingsPage from './page';

const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) });

function settingsBlob(provider: string, model: string) {
  return {
    settings: { id: 's1', name: 'Sorento', embedding_provider: provider, embedding_model: model, embedding_records_search_model: null, embedding_backfill_rpm: 20 },
    roles: [],
  };
}

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EmbeddingsSettingsPage />
    </QueryClientProvider>,
  );
}

afterEach(() => cleanup());

describe('Record search row', () => {
  beforeEach(() => {
    apiFetch.mockReset();
    apiFetch.mockImplementation(async (url: string) =>
      String(url).includes('/system/embeddings/overview') ? json(overview) : json(settingsBlob('gemini', GEM)),
    );
  });

  it('shows the search model from the overview while it differs from the embedder, though the settings column is NULL', async () => {
    renderPage();
    const row = await screen.findByText(/record search/i);
    expect(row).toBeInTheDocument();
    expect(screen.getAllByText(new RegExp(M3S)).length).toBeGreaterThan(0);
  });
});

describe('save toast', () => {
  beforeEach(() => {
    vi.mocked(toast.success).mockClear();
    apiFetch.mockReset();
    apiFetch.mockImplementation(async (url: string) => {
      if (String(url).includes('/system/embeddings/overview')) return json({ ...overview, setting: { ...overview.setting, provider: 'openai', model: M3S } });
      if (String(url).includes('/user-management/settings/general')) return json({ message: 'ok' });
      return json(settingsBlob('openai', M3S));
    });
  });

  it('mentions the records backfill when the model changed', async () => {
    renderPage();
    const provider = (await screen.findAllByRole('combobox'))[0];
    fireEvent.click(provider);
    fireEvent.click(await screen.findByRole('option', { name: /gemini/i }));
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(vi.mocked(toast.success)).toHaveBeenCalled());
    const messages = vi.mocked(toast.success).mock.calls.map((c) => String(c[0]));
    expect(messages.some((m) => /backfill/i.test(m))).toBe(true);
  });
});
