/**
 * `useCurrencyFormat` used to read the full system-settings blob, which is now
 * gated on `user_management.settings.view` (Q2 of
 * documentation/plans/security/PLAN-user-management-read-gates.md). It reads the
 * narrow `/settings/app-config` projection instead.
 *
 * Two things are pinned here because getting either wrong is silent:
 *  - the URL, since the old one now 403s for the roles that render currency;
 *  - the FLAT read (`currency_format`, not `settings.currency_format`), since the
 *    old nested shape would just fall through to the default and every price on
 *    the screen would quietly render in the shipped format instead of the
 *    configured one.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useCurrencyFormat } from './useCurrencyFormat';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

const ENDPOINT = '/api/user-management/settings/app-config';
const DEFAULT_CURRENCY_FORMAT = 'RM {value}';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client }, children);
}

function okResponse(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('useCurrencyFormat', () => {
  it('reads currency_format off the flat app-config projection', async () => {
    apiFetch.mockResolvedValue(okResponse({ currency_format: 'MYR {value}' }));

    const { result } = renderHook(() => useCurrencyFormat(), { wrapper });

    await waitFor(() => expect(result.current).toBe('MYR {value}'));
    expect(apiFetch).toHaveBeenCalledWith(ENDPOINT);
  });

  it('does not read the old nested settings shape', async () => {
    // The gated full blob nests under `settings`. If the hook still read that
    // shape it would find nothing here and fall back, so asserting the default
    // is what proves the flat read.
    apiFetch.mockResolvedValue(
      okResponse({ settings: { currency_format: 'NESTED {value}' } }),
    );

    const { result } = renderHook(() => useCurrencyFormat(), { wrapper });

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(result.current).toBe(DEFAULT_CURRENCY_FORMAT);
  });

  it('falls back to the shipped default when the endpoint fails', async () => {
    apiFetch.mockResolvedValue({ ok: false } as unknown as Response);

    const { result } = renderHook(() => useCurrencyFormat(), { wrapper });

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(result.current).toBe(DEFAULT_CURRENCY_FORMAT);
  });

  it('falls back to the shipped default while loading', () => {
    apiFetch.mockResolvedValue(okResponse({ currency_format: 'MYR {value}' }));

    const { result } = renderHook(() => useCurrencyFormat(), { wrapper });

    expect(result.current).toBe(DEFAULT_CURRENCY_FORMAT);
  });
});
