/**
 * L9 (NEVER-STUCK-UI S3 "Defaults are not data", audit row 12). The settings
 * layout used to fall back to `createDefaultSettings()` when the read failed, so
 * all eleven tabs drew blank defaults and their Save could write them over the
 * real configuration. A failed read now renders an error with Retry and no tab.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/settings',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import Layout from './layout';
import { useSettings } from './components/settings-context';

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

/** Stands in for a tab: it would save whatever the context hands it. */
function FakeTab() {
  const { settings } = useSettings();
  return <button type="button">Save {settings?.name || '(blank)'}</button>;
}

function renderLayout() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Layout>
        <FakeTab />
      </Layout>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiFetch.mockReset();
});
afterEach(() => cleanup());

describe('settings when the read fails', () => {
  it('shows the error with Retry and renders no tab, so nothing can save blank defaults', async () => {
    apiFetch.mockResolvedValue(json(500, { detail: 'Database unavailable' }));
    renderLayout();

    expect(await screen.findByText('Could not load settings', {}, { timeout: 4000 })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^Save/ })).toBeNull();
    expect(screen.queryByRole('tab')).toBeNull();
  });

  it('Retry refetches and renders the real settings', async () => {
    apiFetch.mockResolvedValueOnce(json(500, { detail: 'Database unavailable' }));
    apiFetch.mockResolvedValueOnce(json(500, { detail: 'Database unavailable' }));
    apiFetch.mockResolvedValue(json(200, { settings: { id: 's1', name: 'Sorento' }, roles: [] }));
    renderLayout();

    fireEvent.click(await screen.findByRole('button', { name: 'Retry' }, { timeout: 4000 }));
    expect(await screen.findByRole('button', { name: 'Save Sorento' })).toBeTruthy();
  });

  it('a 403 shows AccessDenied, not the form', async () => {
    apiFetch.mockResolvedValue(json(403, { detail: 'Permission required: system.settings.view' }));
    renderLayout();

    expect(await screen.findByText("You don't have access to this page")).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^Save/ })).toBeNull();
  });
});
