/**
 * `useExcelAccept` moved off the full system-settings blob (now gated on
 * `user_management.settings.view`, Q2 of
 * documentation/plans/security/PLAN-user-management-read-gates.md) onto the narrow
 * `/settings/app-config` projection.
 *
 * The behaviour it must preserve is unusual and worth stating plainly:
 * `excel_upload_accept_extensions` is NOT a column on the backend SystemSetting
 * model and never has been, so this hook has ALWAYS returned DEFAULT_ACCEPT. The
 * default is the shipped behaviour, not a regression introduced by the endpoint
 * move - which is exactly why the "realistic payload" test below asserts the
 * default rather than a configured value.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useExcelAccept } from './use-excel-accept';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

const ENDPOINT = '/api/user-management/settings/app-config';
const DEFAULT_ACCEPT = '.xlsx,.xls,.xlsm';

// The six fields the projection actually returns - no accept-extensions among them.
const APP_CONFIG_PAYLOAD = {
  currency: 'MYR',
  currency_format: 'RM {value}',
  purchase_request_default_approver_user_id: null,
  purchase_request_default_approver_email: null,
  sponsorship_form_default_approver_user_id: null,
  sponsorship_form_default_approver_email: null,
};

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

describe('useExcelAccept', () => {
  it('calls the app-config projection, not the gated settings blob', async () => {
    apiFetch.mockResolvedValue(okResponse(APP_CONFIG_PAYLOAD));

    renderHook(() => useExcelAccept(), { wrapper });

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(apiFetch).toHaveBeenCalledWith(ENDPOINT);
  });

  it('yields the default against the real projection payload (no such column)', async () => {
    apiFetch.mockResolvedValue(okResponse(APP_CONFIG_PAYLOAD));

    const { result } = renderHook(() => useExcelAccept(), { wrapper });

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(result.current).toBe(DEFAULT_ACCEPT);
  });

  it('yields the default when the endpoint fails', async () => {
    apiFetch.mockResolvedValue({ ok: false } as unknown as Response);

    const { result } = renderHook(() => useExcelAccept(), { wrapper });

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(result.current).toBe(DEFAULT_ACCEPT);
  });

  it('would honour the value if the projection ever returned one', async () => {
    // Documents the read path itself (flat, not nested) without claiming the
    // field exists server-side.
    apiFetch.mockResolvedValue(
      okResponse({ ...APP_CONFIG_PAYLOAD, excel_upload_accept_extensions: '.xlsx' }),
    );

    const { result } = renderHook(() => useExcelAccept(), { wrapper });

    await waitFor(() => expect(result.current).toBe('.xlsx'));
  });
});
