/**
 * An open v2 tab hears about the kill switch or a revoked preview (review fix S2): the /me profile is
 * re-read on window focus and every 5 minutes while the effective version is v2, and never in v1.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Owner' } }, status: 'authenticated' }),
}));
const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { UiVersionProvider } from './UiVersionProvider';
import { useUiVersion } from './useUiVersion';

let server: Record<string, unknown>;

function Probe() {
  const v = useUiVersion();
  return <div data-testid="probe">{v.isLoading ? 'loading' : v.uiVersion}</div>;
}

async function mountAndSettle() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(
    <QueryClientProvider client={client}>
      <UiVersionProvider>
        <Probe />
      </UiVersionProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByTestId('probe').textContent).not.toBe('loading'));
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  apiFetch.mockReset();
  apiFetch.mockImplementation(async () => ({ ok: true, status: 200, json: async () => server }));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('v2 tab refresh of /me', () => {
  it('re-reads the profile on window focus while v2', async () => {
    server = { name: 'Owner', ui_version: 'v2', ui_v2_available: true };
    await mountAndSettle();
    const before = apiFetch.mock.calls.length;
    await act(async () => {
      fireEvent.focus(window);
    });
    await waitFor(() => expect(apiFetch.mock.calls.length).toBeGreaterThan(before));
  });

  it('re-reads the profile every 5 minutes while v2, and a kill switch then drops to v1', async () => {
    server = { name: 'Owner', ui_version: 'v2', ui_v2_available: true };
    await mountAndSettle();
    expect(screen.getByTestId('probe').textContent).toBe('v2');
    const before = apiFetch.mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4 * 60 * 1000);
    });
    expect(apiFetch.mock.calls.length).toBe(before);

    server = { name: 'Owner', ui_version: 'v1', ui_v2_available: false }; // the admin turned v2 off
    await act(async () => {
      await vi.advanceTimersByTimeAsync(61 * 1000);
    });
    await waitFor(() => expect(apiFetch.mock.calls.length).toBeGreaterThan(before));
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('v1'));
  });

  it('does not poll or refetch on focus in v1', async () => {
    server = { name: 'Owner', ui_version: 'v1', ui_v2_available: true };
    await mountAndSettle();
    const before = apiFetch.mock.calls.length;
    await act(async () => {
      fireEvent.focus(window);
      await vi.advanceTimersByTimeAsync(11 * 60 * 1000);
    });
    expect(apiFetch.mock.calls.length).toBe(before);
  });
});
