/**
 * The flyer reading hooks (S7.4, reworked for the background read).
 *
 * Two behaviours here are load-bearing and invisible from the screen:
 *
 * - The detail query is keyed on the PROMOTION. The report is recomputed per
 *   promotion, so a promotion-blind key would answer a question about promotion
 *   B with the numbers computed for promotion A.
 * - A create hook invalidates the list and NOTHING else. The read has not
 *   happened when the POST answers, so there is no report to seed a detail
 *   cache with; seeding one would put an empty report in front of somebody as
 *   though it were the answer.
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
  type FlyerReadingSummary,
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
  status: 'done',
  errorMessage: null,
  finishedAt: '2026-08-01T02:00:41',
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

/** What a create hook resolves with now: the row, in processing, no report. */
const ACCEPTED: FlyerReadingSummary = {
  id: 'r-1',
  filename: 'flyer.pdf',
  byteSize: 4200,
  pageCount: 0,
  codeCount: 0,
  uploadedAt: '2026-08-01T02:00:00',
  status: 'processing',
  errorMessage: null,
  finishedAt: null,
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
      {
        id: 'r-1',
        filename: 'flyer.pdf',
        byteSize: 1,
        pageCount: 3,
        codeCount: 61,
        uploadedAt: '',
        status: 'done',
        errorMessage: null,
        finishedAt: null,
      },
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

  it('polls every 3s while a row is processing, and stops once none is (AC-FE.3)', async () => {
    // Real timers: react-query's own refetch scheduling runs through a real
    // setTimeout, and testing-library's `waitFor` polls with real timers too -
    // faking them here means both go quiet and the test hangs on itself.
    mockList.mockResolvedValueOnce([
      {
        id: 'r-1',
        filename: 'flyer.pdf',
        byteSize: 0,
        pageCount: 0,
        codeCount: 0,
        uploadedAt: '',
        status: 'processing',
        errorMessage: null,
        finishedAt: null,
      },
    ]);
    mockList.mockResolvedValue([
      {
        id: 'r-1',
        filename: 'flyer.pdf',
        byteSize: 1000,
        pageCount: 4,
        codeCount: 61,
        uploadedAt: '',
        status: 'done',
        errorMessage: null,
        finishedAt: '2026-08-01T00:00:00',
      },
    ]);

    const { result } = renderHook(() => useFlyerReadingsQuery(), {
      wrapper: wrapperWith(freshClient()),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockList).toHaveBeenCalledTimes(1);

    // A row is still processing, so the interval resolves to 3000 and a
    // second GET fires on its own, without anybody touching the page.
    await waitFor(() => expect(result.current.data?.[0]?.status).toBe('done'), {
      timeout: 4500,
    });
    expect(mockList).toHaveBeenCalledTimes(2);

    // Nothing left processing, so refetchInterval resolves to false: no third
    // call turns up even after another full poll interval elapses.
    await new Promise((resolve) => setTimeout(resolve, 3200));
    expect(mockList).toHaveBeenCalledTimes(2);
  }, 10000);
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

  it('polls the detail every 3s while it is processing, and stops once it is done (AC-FE.4)', async () => {
    const processing: FlyerReading = {
      ...READING,
      status: 'processing',
      pageCount: 0,
      codeCount: 0,
      finishedAt: null,
    };
    mockGet.mockResolvedValueOnce(processing);
    mockGet.mockResolvedValue(READING);

    const { result } = renderHook(() => useFlyerReadingQuery('r-1', null), {
      wrapper: wrapperWith(freshClient()),
    });

    await waitFor(() => expect(result.current.data?.status).toBe('processing'));
    expect(mockGet).toHaveBeenCalledTimes(1);

    await waitFor(() => expect(result.current.data?.status).toBe('done'), { timeout: 4500 });
    expect(mockGet).toHaveBeenCalledTimes(2);

    // Done stops the poll: no third GET turns up after another interval.
    await new Promise((resolve) => setTimeout(resolve, 3200));
    expect(mockGet).toHaveBeenCalledTimes(2);
  }, 10000);
});

describe('useUploadFlyerReading', () => {
  it('refreshes the list and seeds no detail cache, because there is no report yet', async () => {
    mockUpload.mockResolvedValue(ACCEPTED);
    const client = freshClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useUploadFlyerReading(), {
      wrapper: wrapperWith(client),
    });

    result.current.mutate({ file: new File([''], 'flyer.pdf') });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: [FLYER_READINGS_QUERY_KEY] });
    // An empty report cached under the reading's key would be shown to the
    // first person who opened the row, as though the read had found nothing.
    expect(client.getQueryData([FLYER_READINGS_QUERY_KEY, 'r-1', ''])).toBeUndefined();
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('says where the flyer went, and does not claim it has been read', async () => {
    mockUpload.mockResolvedValue(ACCEPTED);

    const { result } = renderHook(() => useUploadFlyerReading(), {
      wrapper: wrapperWith(freshClient()),
    });

    result.current.mutate({ file: new File([''], 'flyer.pdf') });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith(
      'Reading the flyer in the background - it will appear in your uploads',
    );
  });

  it('says the read did not start when the 202 comes back already failed', async () => {
    // The queue was unreachable, so the backend answered 202 with a row that is
    // already `failed`. "Reading the flyer in the background" would be a promise
    // nothing is left to keep.
    mockUpload.mockResolvedValue({
      ...ACCEPTED,
      status: 'failed',
      errorMessage: 'The flyer could not be queued for reading. Try again in a moment.',
      finishedAt: '2026-08-01T02:00:01',
    });

    const { result } = renderHook(() => useUploadFlyerReading(), {
      wrapper: wrapperWith(freshClient()),
    });

    result.current.mutate({ file: new File([''], 'flyer.pdf') });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith(
      'The flyer could not be queued for reading. Try again in a moment.',
    );
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled();
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
  it('does exactly what the upload hook does, down to the toast', async () => {
    mockFromAttachment.mockResolvedValue(ACCEPTED);
    const client = freshClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useCreateFlyerReadingFromAttachment(), {
      wrapper: wrapperWith(client),
    });

    result.current.mutate({ attachmentId: 'att-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // `onFlyerReadingCreated` is shared by both, and this is the assertion that
    // would catch the two drifting: same invalidation, same words.
    expect(client.getQueryData([FLYER_READINGS_QUERY_KEY, 'r-1', ''])).toBeUndefined();
    expect(mockGet).not.toHaveBeenCalled();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: [FLYER_READINGS_QUERY_KEY] });
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith(
      'Reading the flyer in the background - it will appear in your uploads',
    );
  });

  it('says the read did not start on an already-failed 202, same as the upload hook', async () => {
    mockFromAttachment.mockResolvedValue({
      ...ACCEPTED,
      status: 'failed',
      errorMessage: 'The flyer could not be queued for reading. Try again in a moment.',
      finishedAt: '2026-08-01T02:00:01',
    });

    const { result } = renderHook(() => useCreateFlyerReadingFromAttachment(), {
      wrapper: wrapperWith(freshClient()),
    });

    result.current.mutate({ attachmentId: 'att-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith(
      'The flyer could not be queued for reading. Try again in a moment.',
    );
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled();
  });

  it('passes the attachment id and promotion through to the service call', async () => {
    mockFromAttachment.mockResolvedValue(ACCEPTED);
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
