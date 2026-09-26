/**
 * PLAN-excel-preview-26sep S1 (AC-14; owner ruling 26 Sep, Q4): Download posts the export
 * with the page's split and filters, reads "Preparing..." while the worker builds the file,
 * then saves it with no second click and says it is also in My Downloads. A refusal toasts
 * the extracted message and hands the button back.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

const exportLowStockReport = vi.fn();
vi.mock('../services/lowStockReportService', () => ({
  exportLowStockReport: (...a: unknown[]) => exportLowStockReport(...a),
}));

const fetchDownloadsForEntity = vi.fn();
const fetchDownloadFile = vi.fn();
vi.mock('@/services/myDownloadsService', () => ({
  MY_DOWNLOADS_QUERY_KEY: ['my-downloads'],
  ENTITY_DOWNLOADS_QUERY_KEY: ['entity-downloads'],
  fetchDownloadsForEntity: (...a: unknown[]) => fetchDownloadsForEntity(...a),
  fetchDownloadFile: (...a: unknown[]) => fetchDownloadFile(...a),
}));

const saveBlobAs = vi.fn();
vi.mock('@/lib/save-blob', () => ({ saveBlobAs: (...a: unknown[]) => saveBlobAs(...a) }));

import { useLowStockDownload } from './useLowStockDownload';

const REQUEST = {
  runId: 'run-1',
  split: 'supplier' as const,
  suppliers: ['Acme'],
  categories: [],
};

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  toastSuccess.mockClear();
  toastError.mockClear();
  exportLowStockReport.mockReset();
  fetchDownloadsForEntity.mockReset();
  fetchDownloadFile.mockReset();
  saveBlobAs.mockReset();
});

describe('useLowStockDownload', () => {
  it('posts the export, reads preparing until ready, then saves the file on its own', async () => {
    exportLowStockReport.mockResolvedValue({
      id: 'dl-1', status: 'pending', filename: 'low-stock-26092026.xlsx',
    });
    fetchDownloadsForEntity
      .mockResolvedValueOnce({ downloads: [{ id: 'dl-1', status: 'processing' }] })
      .mockResolvedValue({
        downloads: [
          { id: 'dl-0', status: 'ready', filename: 'older.xlsx' },
          { id: 'dl-1', status: 'ready', filename: 'low-stock-26092026.xlsx' },
        ],
      });
    const blob = new Blob(['xlsx']);
    fetchDownloadFile.mockResolvedValue(blob);

    const { result } = renderHook(() => useLowStockDownload({ pollMs: 10 }), {
      wrapper: wrapper(),
    });
    expect(result.current.preparing).toBe(false);

    act(() => result.current.start(REQUEST));
    await waitFor(() => expect(result.current.preparing).toBe(true));
    expect(exportLowStockReport).toHaveBeenCalledWith(REQUEST);

    await waitFor(() => expect(saveBlobAs).toHaveBeenCalledWith(blob, 'low-stock-26092026.xlsx'));
    expect(fetchDownloadFile).toHaveBeenCalledWith('dl-1');
    expect(fetchDownloadsForEntity).toHaveBeenCalledWith('reorder_run', 'run-1');
    expect(toastSuccess).toHaveBeenCalledWith(expect.stringMatching(/My Downloads/));
    await waitFor(() => expect(result.current.preparing).toBe(false));
  });

  it('a refused export toasts the message and hands the button back', async () => {
    exportLowStockReport.mockRejectedValue(new Error('A low stock report is already being prepared'));
    const { result } = renderHook(() => useLowStockDownload({ pollMs: 10 }), {
      wrapper: wrapper(),
    });

    act(() => result.current.start(REQUEST));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('A low stock report is already being prepared'),
    );
    expect(result.current.preparing).toBe(false);
    expect(fetchDownloadsForEntity).not.toHaveBeenCalled();
  });

  it('a failed build toasts its error and saves nothing', async () => {
    exportLowStockReport.mockResolvedValue({ id: 'dl-2', status: 'pending' });
    fetchDownloadsForEntity.mockResolvedValue({
      downloads: [{ id: 'dl-2', status: 'failed', error: 'Narrow the plan first' }],
    });
    const { result } = renderHook(() => useLowStockDownload({ pollMs: 10 }), {
      wrapper: wrapper(),
    });

    act(() => result.current.start(REQUEST));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Narrow the plan first'));
    expect(saveBlobAs).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.preparing).toBe(false));
  });
});
