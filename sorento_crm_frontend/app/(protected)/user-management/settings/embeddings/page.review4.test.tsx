/**
 * LOOKUP-EMBED-CENTRAL review fix round 4, J-3: the save toast mentions the records backfill exactly when the save
 * changed provider or model, also on a second save in the same visit and on a first save of a never-saved setting.
 * Red before the fixes.
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

function settingsBlob(provider: string | null, model: string | null) {
  return {
    settings: { id: 's1', name: 'Sorento', embedding_provider: provider, embedding_model: model, embedding_records_search_model: null, embedding_backfill_rpm: 20 },
    roles: [],
  };
}

function mockApi(blob: ReturnType<typeof settingsBlob>) {
  apiFetch.mockReset();
  apiFetch.mockImplementation(async (url: string) => {
    if (String(url).includes('/system/embeddings/overview')) return json({ ...overview, setting: { ...overview.setting, provider: 'openai', model: M3S } });
    if (String(url).includes('/user-management/settings/general')) return json({ message: 'ok' });
    return json(blob);
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EmbeddingsSettingsPage />
    </QueryClientProvider>,
  );
}

const lastToast = () => String(vi.mocked(toast.success).mock.calls.at(-1)?.[0]);

afterEach(() => cleanup());
beforeEach(() => vi.mocked(toast.success).mockClear());

describe('backfill mention on the save toast', () => {
  it('names the backfill after a model change, then not after a second save that changes only the rpm', async () => {
    mockApi(settingsBlob('gemini', GEM));
    renderPage();
    fireEvent.click((await screen.findAllByRole('combobox'))[0]);
    fireEvent.click(await screen.findByRole('option', { name: /openai/i }));
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(vi.mocked(toast.success)).toHaveBeenCalledTimes(1));
    expect(lastToast()).toMatch(/backfill/i);

    fireEvent.change(screen.getByLabelText(/requests per minute/i), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(vi.mocked(toast.success)).toHaveBeenCalledTimes(2));
    expect(lastToast()).not.toMatch(/backfill/i);
  });

  it('names the backfill on the first save of a never-saved setting that sends provider and model', async () => {
    mockApi(settingsBlob(null, null));
    renderPage();
    await screen.findAllByRole('combobox');
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(vi.mocked(toast.success)).toHaveBeenCalledTimes(1));
    const body = JSON.parse(String((apiFetch.mock.calls.find((c) => String(c[0]).includes('/settings/general'))?.[1] as { body?: string })?.body));
    expect(body.embedding_model).toBeTruthy();
    expect(lastToast()).toMatch(/backfill/i);
  });
});
