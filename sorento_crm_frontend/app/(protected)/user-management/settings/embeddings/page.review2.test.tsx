/**
 * LOOKUP-EMBED-CENTRAL review fix round 2 (G-6): the Settings tab prefills only from known values and sends provider /
 * model only when the user changed them. A settings row with NULL embedding columns and an overview the caller may not
 * read (403) must not show OpenAI / text-embedding-3-small as if they were saved.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockImplementation(async (url: string) => {
    if (String(url).includes('/system/embeddings/overview')) {
      return { ok: false, status: 403, json: async () => ({ detail: 'Forbidden' }), text: async () => 'Forbidden' };
    }
    if (String(url).includes('/user-management/settings/general')) return json({ message: 'ok' });
    return json({
      settings: { id: 's1', name: 'Sorento', embedding_provider: null, embedding_model: null, embedding_records_search_model: null, embedding_backfill_rpm: null },
      roles: [],
    });
  });
});
afterEach(() => cleanup());

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EmbeddingsSettingsPage />
    </QueryClientProvider>,
  );
}

describe('Settings > Embeddings with nothing saved and no overview', () => {
  it('does not show OpenAI or text-embedding-3-small as a saved value', async () => {
    renderPage();
    await screen.findByRole('spinbutton', { name: /rpm|backfill/i });
    expect(screen.queryByText(/text-embedding-3-small/)).toBeNull();
    expect(screen.queryByText(/^OpenAI$/)).toBeNull();
  });

  it('saving the rpm alone sends no provider and no model', async () => {
    renderPage();
    const rpm = await screen.findByRole('spinbutton', { name: /rpm|backfill/i });
    fireEvent.change(rpm, { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      const save = apiFetch.mock.calls.find(([url]) => String(url).includes('/user-management/settings/general'));
      expect(save).toBeTruthy();
      const body = JSON.parse(save![1].body);
      expect(body).toMatchObject({ embedding_backfill_rpm: 30 });
      expect(body).not.toHaveProperty('embedding_provider');
      expect(body).not.toHaveProperty('embedding_model');
    });
  });
});
