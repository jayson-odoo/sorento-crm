/**
 * OI-RESERVE-ROUND (AC-10): `reserve_request` rides the Lines screen's list and summary
 * query strings and its Excel / PDF export body, beside `inquiry_no`. The screen test mocks
 * this service, so the wire is pinned here.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

const { apiFetch } = await import('@/lib/api');
const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function ok(body: unknown) {
  return {
    ok: true,
    json: async () => body,
    headers: { get: () => 'application/json' },
  } as unknown as Response;
}

const IDS = 'req-x,req-y';

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockResolvedValue(ok({ data: [], total: 0, page: 1, limit: 25, id: 'dl-1' }));
});

describe('reserve_request on the worklist calls', () => {
  it('the list query string carries it with inquiry_no', async () => {
    const { listOrderInquiryWorklist } = await import('./orderInquiryService');
    await listOrderInquiryWorklist({ inquiry_no: 'OI-1,OI-2', reserve_request: IDS });
    const url = new URL(String(mockFetch.mock.calls[0][0]), 'http://x');
    expect(url.searchParams.get('reserve_request')).toBe(IDS);
    expect(url.searchParams.get('inquiry_no')).toBe('OI-1,OI-2');
  });

  it('the summary query string carries it', async () => {
    const { getOrderInquiryWorklistSummary } = await import('./orderInquiryService');
    await getOrderInquiryWorklistSummary({ reserve_request: IDS });
    const url = new URL(String(mockFetch.mock.calls[0][0]), 'http://x');
    expect(url.searchParams.get('reserve_request')).toBe(IDS);
  });

  it('an empty value is not sent', async () => {
    const { listOrderInquiryWorklist } = await import('./orderInquiryService');
    await listOrderInquiryWorklist({ reserve_request: undefined });
    expect(String(mockFetch.mock.calls[0][0])).not.toContain('reserve_request');
  });

  it('the Excel and PDF export bodies carry it', async () => {
    const { exportOrderInquiryWorklistXlsx, exportOrderInquiryWorklistPdf } = await import(
      './orderInquiryService'
    );
    await exportOrderInquiryWorklistXlsx({ reserve_request: IDS });
    await exportOrderInquiryWorklistPdf({ reserve_request: IDS });
    for (const [, init] of mockFetch.mock.calls) {
      expect(JSON.parse((init as { body: string }).body).reserve_request).toBe(IDS);
    }
  });

  it('Select all then Confirm sends it inside the filter body', async () => {
    const { acknowledgeOrderInquiryRowsByFilter } = await import('./orderInquiryService');
    await acknowledgeOrderInquiryRowsByFilter({ inquiry_no: 'OI-1', reserve_request: IDS });
    const body = JSON.parse((mockFetch.mock.calls[0][1] as { body: string }).body);
    expect(body.filter.reserve_request).toBe(IDS);
  });
});
