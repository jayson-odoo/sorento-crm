/**
 * `PLAN-oi-no-double-count-25sep.md` S2 (AC-ND-20, issue #1248): the OI detail's Lines tab
 * reads its whole line history in ONE fetch - the worklist's `inquiry_id` read with
 * `include_history=true`, cancelled rows included - so the History dialog needs no second
 * read. `buildDataGridParams` is kept real: the point is the exact query string sent.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

const { apiFetch } = await import('@/lib/api');
const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

import * as service from './orderInquiryService';

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

function urlOf(call: number): URL {
  return new URL(mockFetch.mock.calls[call][0] as string, 'http://test.local');
}

beforeEach(() => mockFetch.mockReset());

describe('getOrderInquiryHeaderLines (AC-ND-20)', () => {
  it('asks for the header rows with include_history, and no state filter', async () => {
    mockFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 1000 } }));

    await service.getOrderInquiryHeaderLines('oi-1');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const search = urlOf(0).searchParams;
    expect(search.get('inquiry_id')).toBe('oi-1');
    expect(search.get('include_history')).toBe('true');
    expect(search.get('state')).toBeNull();
  });

  it('the separate cancelled-rows read is gone', () => {
    expect('getOrderInquiryHeaderCancelledRows' in service).toBe(false);
  });
});
