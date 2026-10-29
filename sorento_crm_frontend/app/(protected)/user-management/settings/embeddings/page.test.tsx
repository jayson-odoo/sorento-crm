/**
 * LOOKUP-EMBED-CENTRAL slice 5, AC-LEC-23: System Settings > Embeddings tab (provider, model, backfill rpm, read-only
 * coverage rows). Red before the page and the tab exist. Mocked at `@/lib/api` (apiFetch) so the hooks / service
 * names stay the coder's: the page must read the settings blob, read /system/embeddings/overview for the coverage
 * rows, and save through /user-management/settings/general.
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

import EmbeddingsSettingsPage from './page';

const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) });

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockImplementation(async (url: string) => {
    if (String(url).includes('/system/embeddings/overview')) return json(overview);
    if (String(url).includes('/user-management/settings/general')) return json({ message: 'ok' });
    return json({
      settings: { id: 's1', name: 'Sorento', embedding_provider: 'gemini', embedding_model: GEM, embedding_records_search_model: M3S, embedding_backfill_rpm: 20 },
      roles: [],
    });
  });
});
afterEach(() => cleanup());

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EmbeddingsSettingsPage />
    </QueryClientProvider>,
  );
}

describe('Settings > Embeddings', () => {
  it('shows the stored model and the read-only coverage rows', async () => {
    renderPage();
    expect((await screen.findAllByText(new RegExp(GEM))).length).toBeGreaterThan(0);
    expect(await screen.findByText(/422\s*\/\s*502/)).toBeInTheDocument();
    expect(screen.getAllByText(new RegExp(M3S)).length).toBeGreaterThan(0);
  });

  it('saves provider, model and backfill rpm through the settings general route', async () => {
    renderPage();
    const rpm = await screen.findByRole('spinbutton', { name: /rpm|backfill/i });
    fireEvent.change(rpm, { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      const save = apiFetch.mock.calls.find(([url]) => String(url).includes('/user-management/settings/general'));
      expect(save).toBeTruthy();
      expect(['PUT', 'POST']).toContain(save![1].method);
      expect(JSON.parse(save![1].body)).toMatchObject({
        embedding_provider: 'gemini',
        embedding_model: GEM,
        embedding_backfill_rpm: 30,
      });
    });
  });

  it('never sends the records search model back', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /save/i }));
    await waitFor(() => expect(apiFetch.mock.calls.some(([url]) => String(url).includes('/settings/general'))).toBe(true));
    const save = apiFetch.mock.calls.find(([url]) => String(url).includes('/settings/general'))!;
    expect(JSON.parse(save[1].body)).not.toHaveProperty('embedding_records_search_model');
  });
});
