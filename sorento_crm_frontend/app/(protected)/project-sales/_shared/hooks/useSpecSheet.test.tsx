/**
 * SPEC-SHEET-V2 red test 18: the spec sheet queries never refetch on window focus, and the
 * mutations refresh the list and the one sheet.
 *
 * Written BEFORE the hooks. Contract of this file (all exports of ./useSpecSheet):
 *
 *   useSpecSheets(projectId, documentId)                          -> listSpecSheets
 *   useSpecSheetDetail(projectId, documentId, sheetId)            -> getSpecSheet
 *   useSpecSheetPreview(projectId, documentId, sheetId, keys, enabled?)
 *                                                                 -> getSpecSheetPreview(p, d, s, keys)
 *                                                                    query key uses the SORTED keys
 *   useSpecSheetPageDesign(projectId, documentId, sheetId, key)   -> getSpecSheetPageDesign
 *   useSpecSheetMutations(projectId, documentId) -> { create, update, savePageEdit, exportPdf }
 *        create.mutate(body)                  -> createSpecSheet(p, d, body)
 *        update.mutate({ sheetId, body })     -> updateSpecSheet(p, d, sheetId, body)
 *        savePageEdit.mutate({ sheetId, key, layers }) -> saveSpecSheetPageEdit(p, d, sheetId, key, layers)
 *        exportPdf.mutate(sheetId)            -> queueSpecSheetPdf(p, d, sheetId)
 *
 *   Service module `@/app/(protected)/project-sales/_shared/services/specSheetService` exports exactly:
 *     listSpecSheets, createSpecSheet, getSpecSheet, updateSpecSheet, getSpecSheetPreview,
 *     getSpecSheetPageDesign, saveSpecSheetPageEdit, queueSpecSheetPdf
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

const listSpecSheets = vi.fn();
const createSpecSheet = vi.fn();
const getSpecSheet = vi.fn();
const updateSpecSheet = vi.fn();
const getSpecSheetPreview = vi.fn();
const getSpecSheetPageDesign = vi.fn();
const saveSpecSheetPageEdit = vi.fn();
const queueSpecSheetPdf = vi.fn();
vi.mock('../services/specSheetService', () => ({
  listSpecSheets: (...a: unknown[]) => listSpecSheets(...a),
  createSpecSheet: (...a: unknown[]) => createSpecSheet(...a),
  getSpecSheet: (...a: unknown[]) => getSpecSheet(...a),
  updateSpecSheet: (...a: unknown[]) => updateSpecSheet(...a),
  getSpecSheetPreview: (...a: unknown[]) => getSpecSheetPreview(...a),
  getSpecSheetPageDesign: (...a: unknown[]) => getSpecSheetPageDesign(...a),
  saveSpecSheetPageEdit: (...a: unknown[]) => saveSpecSheetPageEdit(...a),
  queueSpecSheetPdf: (...a: unknown[]) => queueSpecSheetPdf(...a),
}));

import {
  useSpecSheetDetail,
  useSpecSheetMutations,
  useSpecSheetPageDesign,
  useSpecSheetPreview,
  useSpecSheets,
} from './useSpecSheet';

function wrapperFor(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function newClient() {
  // Library defaults on purpose: the hooks must opt out themselves, not rely on a test default.
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

beforeEach(() => {
  listSpecSheets.mockReset().mockResolvedValue({ items: [], sources: [], templates: { cover: [], page: [] }, defaults: {}, create_disabled_reason: null });
  createSpecSheet.mockReset().mockResolvedValue({ id: 'sheet-2' });
  getSpecSheet.mockReset().mockResolvedValue({ id: 'sheet-1', pages: [] });
  updateSpecSheet.mockReset().mockResolvedValue({ id: 'sheet-1', pages: [] });
  getSpecSheetPreview.mockReset().mockResolvedValue({ doc: { sheets: [] } });
  getSpecSheetPageDesign.mockReset().mockResolvedValue({ layers: [] });
  saveSpecSheetPageEdit.mockReset().mockResolvedValue({ id: 'sheet-1', pages: [] });
  queueSpecSheetPdf.mockReset().mockResolvedValue({});
});

describe('useSpecSheet queries', () => {
  it('every query opts out of refetch on window focus', async () => {
    const client = newClient();
    renderHook(
      () => ({
        list: useSpecSheets('p1', 'd1'),
        detail: useSpecSheetDetail('p1', 'd1', 'sheet-1'),
        preview: useSpecSheetPreview('p1', 'd1', 'sheet-1', ['cover', 'k1'], true),
        design: useSpecSheetPageDesign('p1', 'd1', 'sheet-1', 'k1'),
      }),
      { wrapper: wrapperFor(client) },
    );

    await waitFor(() => {
      expect(listSpecSheets).toHaveBeenCalled();
      expect(getSpecSheet).toHaveBeenCalled();
      expect(getSpecSheetPreview).toHaveBeenCalled();
      expect(getSpecSheetPageDesign).toHaveBeenCalled();
    });
    const queries = client.getQueryCache().getAll();
    expect(queries.length).toBeGreaterThanOrEqual(4);
    for (const query of queries) {
      expect(query.options.refetchOnWindowFocus).toBe(false);
    }
  });

  it('a window focus event does not refetch', async () => {
    const client = newClient();
    renderHook(() => useSpecSheetDetail('p1', 'd1', 'sheet-1'), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(getSpecSheet).toHaveBeenCalledTimes(1));

    act(() => {
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(getSpecSheet).toHaveBeenCalledTimes(1);
  });

  it('the preview query key is the sorted keys: the same window in another order is one request', async () => {
    const client = newClient();
    const { rerender } = renderHook(
      ({ keys }: { keys: string[] }) => useSpecSheetPreview('p1', 'd1', 'sheet-1', keys, true),
      { wrapper: wrapperFor(client), initialProps: { keys: ['k2', 'cover', 'k1'] } },
    );
    await waitFor(() => expect(getSpecSheetPreview).toHaveBeenCalledTimes(1));

    rerender({ keys: ['cover', 'k1', 'k2'] });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(getSpecSheetPreview).toHaveBeenCalledTimes(1);
  });

  it('a disabled preview asks for nothing', async () => {
    const client = newClient();
    renderHook(() => useSpecSheetPreview('p1', 'd1', 'sheet-1', ['cover'], false), {
      wrapper: wrapperFor(client),
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    expect(getSpecSheetPreview).not.toHaveBeenCalled();
  });
});

describe('useSpecSheetMutations', () => {
  it('create refreshes the list', async () => {
    const client = newClient();
    const { result } = renderHook(
      () => ({ list: useSpecSheets('p1', 'd1'), m: useSpecSheetMutations('p1', 'd1') }),
      { wrapper: wrapperFor(client) },
    );
    await waitFor(() => expect(listSpecSheets).toHaveBeenCalledTimes(1));

    await act(async () => {
      await result.current.m.create.mutateAsync({
        source: 'issue-1',
        cover_template_id: 'c',
        page_template_id: 'p',
        single_page_template_id: null,
      });
    });

    expect(createSpecSheet).toHaveBeenCalledWith('p1', 'd1', {
      source: 'issue-1',
      cover_template_id: 'c',
      page_template_id: 'p',
      single_page_template_id: null,
    });
    await waitFor(() => expect(listSpecSheets).toHaveBeenCalledTimes(2));
  });

  it('update refreshes the list and that sheet', async () => {
    const client = newClient();
    const { result } = renderHook(
      () => ({
        list: useSpecSheets('p1', 'd1'),
        detail: useSpecSheetDetail('p1', 'd1', 'sheet-1'),
        m: useSpecSheetMutations('p1', 'd1'),
      }),
      { wrapper: wrapperFor(client) },
    );
    await waitFor(() => {
      expect(listSpecSheets).toHaveBeenCalledTimes(1);
      expect(getSpecSheet).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      await result.current.m.update.mutateAsync({ sheetId: 'sheet-1', body: { use_latest_templates: true } });
    });

    expect(updateSpecSheet).toHaveBeenCalledWith('p1', 'd1', 'sheet-1', { use_latest_templates: true });
    await waitFor(() => {
      expect(listSpecSheets.mock.calls.length).toBeGreaterThanOrEqual(2);
      expect(getSpecSheet.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('saving a page edit refreshes that sheet', async () => {
    const client = newClient();
    const { result } = renderHook(
      () => ({ detail: useSpecSheetDetail('p1', 'd1', 'sheet-1'), m: useSpecSheetMutations('p1', 'd1') }),
      { wrapper: wrapperFor(client) },
    );
    await waitFor(() => expect(getSpecSheet).toHaveBeenCalledTimes(1));

    await act(async () => {
      await result.current.m.savePageEdit.mutateAsync({ sheetId: 'sheet-1', key: 'k1', layers: [] });
    });

    expect(saveSpecSheetPageEdit).toHaveBeenCalledWith('p1', 'd1', 'sheet-1', 'k1', []);
    await waitFor(() => expect(getSpecSheet.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it('export queues the sheet', async () => {
    const client = newClient();
    const { result } = renderHook(() => useSpecSheetMutations('p1', 'd1'), {
      wrapper: wrapperFor(client),
    });

    await act(async () => {
      await result.current.exportPdf.mutateAsync('sheet-1');
    });

    expect(queueSpecSheetPdf).toHaveBeenCalledWith('p1', 'd1', 'sheet-1');
  });
});
