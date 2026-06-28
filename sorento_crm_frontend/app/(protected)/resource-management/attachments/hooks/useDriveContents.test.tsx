/**
 * useDriveContents — the Unified Drive query hook (UAC B1/B2, C6).
 *
 * Asserts the hook forwards browse vs recursive params + pagination to the
 * service and surfaces the response. The service is mocked (network is covered
 * by driveService.test + backend pytest).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useDriveContents } from './useAttachments';
import { getDriveContents } from '../services/driveService';

vi.mock('../services/driveService', async () => {
  const actual = await vi.importActual<typeof import('../services/driveService')>(
    '../services/driveService'
  );
  return { ...actual, getDriveContents: vi.fn() };
});
const mockedGet = vi.mocked(getDriveContents);

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  mockedGet.mockReset();
  mockedGet.mockResolvedValue({
    data: [],
    pagination: { total: 0, page: 1 },
    empty: true,
    recursive: false,
  });
});

describe('useDriveContents', () => {
  it('B1: browse forwards directory_id and no recursive flag', async () => {
    const { result } = renderHook(
      () => useDriveContents({ pageIndex: 0, pageSize: 50, directory_id: 'dir-1' }),
      { wrapper }
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedGet).toHaveBeenCalledWith(
      expect.objectContaining({ directory_id: 'dir-1', pageIndex: 0, pageSize: 50 })
    );
    expect(mockedGet.mock.calls[0][0].recursive).toBeUndefined();
  });

  it('B2: recursive search forwards recursive + query', async () => {
    const { result } = renderHook(
      () =>
        useDriveContents({
          pageIndex: 0,
          pageSize: 50,
          searchQuery: 'invoice',
          recursive: true,
        }),
      { wrapper }
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedGet).toHaveBeenCalledWith(
      expect.objectContaining({ searchQuery: 'invoice', recursive: true })
    );
  });

  it('C6: pagination params reach the service', async () => {
    const { result } = renderHook(
      () => useDriveContents({ pageIndex: 3, pageSize: 25 }),
      { wrapper }
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedGet).toHaveBeenCalledWith(
      expect.objectContaining({ pageIndex: 3, pageSize: 25 })
    );
  });
});
