/**
 * `useExcelAccept` returns the shipped accept list and issues no request.
 *
 * The behaviour it must preserve is unusual and worth stating plainly:
 * `excel_upload_accept_extensions` is NOT a column on the backend SystemSetting
 * model and never has been, so this hook has ALWAYS returned DEFAULT_ACCEPT. The
 * `/settings/app-config` projection (Q2 of
 * documentation/plans/security/PLAN-user-management-read-gates.md) pins six fields
 * by response_model, so the key cannot reach the client at all - which is why the
 * fetch was removed rather than repointed.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useExcelAccept } from './use-excel-accept';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

const DEFAULT_ACCEPT = '.xlsx,.xls,.xlsm';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('useExcelAccept', () => {
  it('yields the shipped accept list on the first render, with no loading pass', () => {
    const { result } = renderHook(() => useExcelAccept(), { wrapper });

    expect(result.current).toBe(DEFAULT_ACCEPT);
  });

  it('issues no request', async () => {
    renderHook(() => useExcelAccept(), { wrapper });

    await Promise.resolve();
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
