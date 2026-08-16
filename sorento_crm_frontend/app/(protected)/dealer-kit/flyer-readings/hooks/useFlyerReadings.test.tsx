/**
 * The flyer reading hooks (S7.4).
 *
 * Two behaviours here are load-bearing and invisible from the screen:
 *
 * - The detail query is keyed on the PROMOTION. The report is recomputed per
 *   promotion, so a promotion-blind key would answer a question about promotion
 *   B with the numbers computed for promotion A.
 * - The upload seeds the detail cache from its own response. Extraction plus
 *   matching already ran inside that request; refetching on arrival pays for a
 *   second match run and blanks the screen it just filled.
 */
import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../services/flyerReadingService', () => ({
  listFlyerReadings: vi.fn(),
  getFlyerReading: vi.fn(),
  uploadFlyerReading: vi.fn(),
  createFlyerReadingFromAttachment: vi.fn(),
  seedFromFlyerReading: vi.fn(),
  deleteFlyerReading: vi.fn(),
  applyDimensions: vi.fn(),
}));

import { toast } from 'sonner';
import {
  createFlyerReadingFromAttachment,
  getFlyerReading,
  listFlyerReadings,
  seedFromFlyerReading,
  uploadFlyerReading,
  type FlyerReading,
} from '../../services/flyerReadingService';
import {
  FLYER_READINGS_QUERY_KEY,
  useCreateFlyerReadingFromAttachment,
  useFlyerReadingQuery,
  useFlyerReadingsQuery,
  useSeedFromFlyerReading,
  useUploadFlyerReading,
} from './useFlyerReadings';

const mockList = vi.mocked(listFlyerReadings);
const mockGet = vi.mocked(getFlyerReading);
const mockUpload = vi.mocked(uploadFlyerReading);
const mockFromAttachment = vi.mocked(createFlyerReadingFromAttachment);
const mockSeed = vi.mocked(seedFromFlyerReading);

const READING: FlyerReading = {
  id: 'r-1',
  filename: 'flyer.pdf',
  byteSize: 4200,
  pageCount: 3,
  codeCount: 61,
  uploadedAt: '2026-08-01T02:00:00',
  headings: [{ page: 1, text: 'WATER CLOSET' }],
  report: {
    matched: [],
    unmatched: [],
    notPromoted: [],
    dimensionCandidates: [],
    duplicates: {},
    promotionId: null,
  },
};

function wrapperWith(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function freshClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useFlyerReadingsQuery', () => {
  it('lists the readings', async () => {
    mockList.mockResolvedValue([
      { id: 'r-1', filename: 'flyer.pdf', byteSize: 1, pageCount: 3, codeCount: 61, uploadedAt: '' },
    ]);

    const { result } = renderHook(() => useFlyerReadingsQuery(), {
      wrapper: wrapperWith(freshClient()),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });

  it('reports a failure rather than an empty list', async () => {
    mockList.mockRejectedValue(new Error('Could not load the flyers read so far'));

    const { result } = renderHook(() => useFlyerReadingsQuery(), {
      wrapper: wrapperWith(freshClient()),
    });

    // The query retries once before giving up, so the error state is a moment
    // away rather than immediate.
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 4000 });
    expect(result.current.error?.message).toMatch(/could not load the flyers/i);
  });
});

describe('useFlyerReadingQuery', () => {
  it('passes the promotion through and re-asks when it changes', async () => {
    mockGet.mockResolvedValue(READING);
    const client = freshClient();

    const { result, rerender } = renderHook(
      ({ promotionId }: { promotionId: string | null }) =>
        useFlyerReadingQuery('r-1', promotionId),
      { wrapper: wrapperWith(client), initialProps: { promotionId: null as string | null } },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('r-1', null);

    rerender({ promotionId: 'promo-7' });

    // A new key, so a new request. Reusing the cached answer would report the
    // gaps of a promotion nobody picked.
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('r-1', 'promo-7'));
    expect(client.getQueryData([FLYER_READINGS_QUERY_KEY, 'r-1', 'promo-7'])).toBeDefined();
  });

  it('asks for nothing until there is a reading to ask about', () => {
    renderHook(() => useFlyerReadingQuery('', null), { wrapper: wrapperWith(freshClient()) });

    expect(mockGet).not.toHaveBeenCalled();
  });
});

describe('useUploadFlyerReading', () => {
  it('seeds the detail cache from its own response instead of refetching', async () => {
    mockUpload.mockResolvedValue(READING);
    const client = freshClient();

    const { result } = renderHook(() => useUploadFlyerReading(), {
      wrapper: wrapperWith(client),
    });

    result.current.mutate({ file: new File([''], 'flyer.pdf') });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryData([FLYER_READINGS_QUERY_KEY, 'r-1', ''])).toEqual(READING);
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('passes the backend message through, because it says what is wrong with the file', async () => {
    mockUpload.mockRejectedValue(
      new Error('That flyer is larger than the 50 MB limit. Export it at a lower image quality and upload it again.'),
    );

    const { result } = renderHook(() => useUploadFlyerReading(), {
      wrapper: wrapperWith(freshClient()),
    });

    result.current.mutate({ file: new File([''], 'flyer.pdf') });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith(expect.stringContaining('50 MB limit'));
  });
});

describe('useCreateFlyerReadingFromAttachment', () => {
  it('seeds the detail cache from its own response, exactly like the upload hook', async () => {
    mockFromAttachment.mockResolvedValue(READING);
    const client = freshClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useCreateFlyerReadingFromAttachment(), {
      wrapper: wrapperWith(client),
    });

    result.current.mutate({ attachmentId: 'att-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // Same key shape the upload hook seeds - `onFlyerReadingCreated` is shared
    // by both, and this is the assertion that would catch the two drifting.
    expect(client.getQueryData([FLYER_READINGS_QUERY_KEY, 'r-1', ''])).toEqual(READING);
    expect(mockGet).not.toHaveBeenCalled();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: [FLYER_READINGS_QUERY_KEY] });
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith('Read 3 pages');
  });

  it('passes the attachment id and promotion through to the service call', async () => {
    mockFromAttachment.mockResolvedValue(READING);
    const { result } = renderHook(() => useCreateFlyerReadingFromAttachment(), {
      wrapper: wrapperWith(freshClient()),
    });

    result.current.mutate({ attachmentId: 'att-1', promotionId: 'promo-7' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockFromAttachment).toHaveBeenCalledWith('att-1', 'promo-7');
  });

  it('passes the backend message through on failure, same as the upload hook', async () => {
    mockFromAttachment.mockRejectedValue(new Error('That PDF is password protected.'));

    const { result } = renderHook(() => useCreateFlyerReadingFromAttachment(), {
      wrapper: wrapperWith(freshClient()),
    });

    result.current.mutate({ attachmentId: 'att-1' });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith('That PDF is password protected.');
  });
});

describe('useSeedFromFlyerReading', () => {
  it('refreshes the brochure list and says which draft version was made', async () => {
    mockSeed.mockResolvedValue({
      pageId: 'pg-1',
      name: 'zzt flyer',
      slug: 'zzt-flyer',
      publicPath: '/c/zzt-flyer',
      versionId: 'v-1',
      version: 3,
      sectionCount: 3,
      collectionCount: 9,
      seededProductCount: 55,
      skipped: [],
    });
    const client = freshClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useSeedFromFlyerReading('r-1'), {
      wrapper: wrapperWith(client),
    });

    result.current.mutate({ pageId: 'pg-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['dealer-kit', 'pages'] });
    // "Draft", never "published": the seed moves no label.
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith('Draft v3 created');
  });

  it('does not throw away the report the reviewer is still reading', async () => {
    mockSeed.mockResolvedValue({
      pageId: 'pg-1',
      name: 'x',
      slug: 'x',
      publicPath: null,
      versionId: 'v-1',
      version: 1,
      sectionCount: 1,
      collectionCount: 1,
      seededProductCount: 1,
      skipped: [],
    });
    const client = freshClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useSeedFromFlyerReading('r-1'), {
      wrapper: wrapperWith(client),
    });

    result.current.mutate({ pageId: 'pg-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).not.toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: [FLYER_READINGS_QUERY_KEY] }),
    );
  });
});
