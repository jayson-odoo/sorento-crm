/**
 * The flyer reading service, against a stubbed api-client (S7.4).
 *
 * The assertions here are the ones a well-meaning tidy-up breaks: sending an
 * unanswered target field alongside a chosen one (which the backend reads as
 * two targets and rejects), defaulting `skipped` away (which would make a seed
 * that dropped 38 products look like a seed that dropped none), and naming a
 * Content-Type on the upload (which produces a body FastAPI cannot parse).
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ extractApiError: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

import {
  deleteFlyerReading,
  getFlyerReading,
  listFlyerReadings,
  seedFromFlyerReading,
  uploadFlyerReading,
} from './flyerReadingService';

const mockFetch = vi.mocked(apiFetch);
const mockError = vi.mocked(extractApiError);

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

function failed(status = 400) {
  return { ok: false, status, json: async () => ({}) } as unknown as Response;
}

const READING = {
  id: 'r-1',
  filename: 'flyer.pdf',
  byteSize: 4200,
  pageCount: 3,
  codeCount: 61,
  uploadedAt: '2026-08-01T02:00:00',
  report: {
    matched: [{ code: 'SRT1', productId: 'p-1', productCode: 'SRT1', productName: 'Sink', pages: [1] }],
    unmatched: [{ code: 'SRT9', pages: [2], suggestion: null }],
    notPromoted: [],
    dimensionCandidates: [],
    duplicates: {},
    promotionId: null,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockError.mockResolvedValue('boom');
});

describe('listFlyerReadings', () => {
  it('asks for the list and drops the report the endpoint never sends', async () => {
    mockFetch.mockResolvedValue(ok([{ id: 'r-1', filename: 'flyer.pdf', pageCount: 3 }]));

    const rows = await listFlyerReadings();

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/dealer-kit/flyer-readings');
    expect(rows).toEqual([
      {
        id: 'r-1',
        filename: 'flyer.pdf',
        byteSize: 0,
        pageCount: 3,
        codeCount: 0,
        uploadedAt: '',
      },
    ]);
  });

  it('surfaces the message the backend gave rather than a generic one', async () => {
    mockFetch.mockResolvedValue(failed(403));
    mockError.mockResolvedValue('Permission required: dealer_kit.page.view');

    await expect(listFlyerReadings()).rejects.toThrow('Permission required: dealer_kit.page.view');
    expect(mockError).toHaveBeenCalled();
  });
});

describe('getFlyerReading', () => {
  it('leaves the promotion off the query when none is chosen', async () => {
    mockFetch.mockResolvedValue(ok(READING));

    await getFlyerReading('r-1', null);

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/dealer-kit/flyer-readings/r-1');
  });

  it('asks the report against a promotion when one is chosen', async () => {
    mockFetch.mockResolvedValue(ok(READING));

    await getFlyerReading('r-1', 'promo-7');

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/dealer-kit/flyer-readings/r-1?promotionId=promo-7',
    );
  });

  it('fills in every list the response left out, so no section reads as absent', async () => {
    mockFetch.mockResolvedValue(ok({ id: 'r-1', filename: 'f.pdf' }));

    const reading = await getFlyerReading('r-1', null);

    expect(reading.report).toEqual({
      matched: [],
      unmatched: [],
      notPromoted: [],
      dimensionCandidates: [],
      duplicates: {},
      promotionId: null,
    });
  });
});

describe('uploadFlyerReading', () => {
  it('sends multipart and never names the content type itself', async () => {
    mockFetch.mockResolvedValue(ok(READING));
    const file = new File(['%PDF-1.4'], 'flyer.pdf', { type: 'application/pdf' });

    const reading = await uploadFlyerReading(file);

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe('/api/v1/dealer-kit/flyer-readings');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get('file')).toBe(file);
    // The browser adds the multipart boundary. Naming it here produces a body
    // FastAPI cannot parse, and the failure reads like a broken endpoint.
    expect(init?.headers).toBeUndefined();
    // The report comes back on the SAME call: extraction runs in the request.
    expect(reading.report.unmatched).toHaveLength(1);
  });

  it('passes the promotion through so the first report is already scoped', async () => {
    mockFetch.mockResolvedValue(ok(READING));

    await uploadFlyerReading(new File([''], 'f.pdf'), 'promo-7');

    expect(mockFetch.mock.calls[0][0]).toBe(
      '/api/v1/dealer-kit/flyer-readings?promotionId=promo-7',
    );
  });
});

describe('seedFromFlyerReading', () => {
  it('sends name and slug for a new brochure, and no pageId at all', async () => {
    mockFetch.mockResolvedValue(ok({ pageId: 'pg-1', name: 'zzt', slug: 'zzt', version: 1 }));

    await seedFromFlyerReading('r-1', { name: 'zzt flyer', slug: 'zzt-flyer' });

    const body = JSON.parse(String(mockFetch.mock.calls[0][1]?.body));
    expect(body).toEqual({ name: 'zzt flyer', slug: 'zzt-flyer' });
    expect('pageId' in body).toBe(false);
  });

  it('sends only the pageId on a re-seed, because two targets is a 422', async () => {
    mockFetch.mockResolvedValue(ok({ pageId: 'pg-1', name: 'x', slug: 'x', version: 4 }));

    await seedFromFlyerReading('r-1', { pageId: 'pg-1', name: '', slug: '' });

    expect(JSON.parse(String(mockFetch.mock.calls[0][1]?.body))).toEqual({ pageId: 'pg-1' });
  });

  it('omits the promotion when there is none, which means "leave it alone"', async () => {
    mockFetch.mockResolvedValue(ok({ pageId: 'pg-1', name: 'x', slug: 'x', version: 2 }));

    await seedFromFlyerReading('r-1', { pageId: 'pg-1', promotionId: null });

    const body = JSON.parse(String(mockFetch.mock.calls[0][1]?.body));
    expect('promotionId' in body).toBe(false);
  });

  it('never defaults the skipped list away', async () => {
    mockFetch.mockResolvedValue(
      ok({
        pageId: 'pg-1',
        name: 'x',
        slug: 'x',
        version: 1,
        skipped: [{ code: 'SRT9', pages: [2], suggestion: null }],
      }),
    );

    const result = await seedFromFlyerReading('r-1', { pageId: 'pg-1' });

    expect(result.skipped).toEqual([{ code: 'SRT9', pages: [2], suggestion: null }]);
  });
});

describe('deleteFlyerReading', () => {
  it('is a hard DELETE on the reading', async () => {
    mockFetch.mockResolvedValue(ok(null));

    await deleteFlyerReading('r-1');

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/dealer-kit/flyer-readings/r-1', {
      method: 'DELETE',
    });
  });

  it('reports a failure instead of resolving quietly', async () => {
    mockFetch.mockResolvedValue(failed(404));
    mockError.mockResolvedValue('Flyer reading not found');

    await expect(deleteFlyerReading('r-1')).rejects.toThrow('Flyer reading not found');
  });
});
