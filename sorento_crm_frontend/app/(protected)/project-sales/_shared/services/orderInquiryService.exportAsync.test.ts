/**
 * Lane B - OI detail Export Excel goes async, tied to the OI; the OI LIST page's Export
 * Excel also goes async (`PLAN-order-sheet-oi-reports-22sep.md` Lane B,
 * `order-sheet-oi-reports-22sep-acceptance-criteria.md` AC-B1/AC-B6).
 *
 * TEST-FIRST (Phase 2): `exportOrderInquiryXlsx` / `exportOrderInquiryWorklistXlsx` do
 * not exist on `orderInquiryService` yet - every test below must fail today with an
 * import/undefined error (not calling a function that does not exist as if it did),
 * never a fixture bug.
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

function failed(status = 500, body: unknown = { message: 'boom' }) {
  return {
    ok: false,
    status,
    json: async () => body,
    headers: { get: () => 'application/json' },
  } as unknown as Response;
}

beforeEach(() => mockFetch.mockReset());

describe('exportOrderInquiryXlsx (AC-B1)', () => {
  it('POSTs to the OI detail export route and returns the download row', async () => {
    const { exportOrderInquiryXlsx } = await import('./orderInquiryService');
    const download = {
      id: 'dl-1',
      kind: 'order_inquiry_xlsx',
      status: 'pending',
      filename: 'OI-2609-0001.xlsx',
    };
    mockFetch.mockResolvedValue(ok(download));

    const result = await exportOrderInquiryXlsx('oi-1');

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/project-sales/order-inquiries/oi-1/export',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(result).toEqual(download);
  });

  it('throws the extracted error message on failure', async () => {
    const { exportOrderInquiryXlsx } = await import('./orderInquiryService');
    mockFetch.mockResolvedValue(failed(409, { detail: 'already in flight' }));

    await expect(exportOrderInquiryXlsx('oi-1')).rejects.toThrow('already in flight');
  });

  it('falls back to a readable message when the server sends nothing usable', async () => {
    const { exportOrderInquiryXlsx } = await import('./orderInquiryService');
    // 400, not 500/401: `extractApiError` has its own dedicated wording for those two
    // statuses, ahead of the caller's fallback - a status this test does not care about
    // is what actually reaches `exportOrderInquiryXlsx`'s own fallback message.
    mockFetch.mockResolvedValue(failed(400, {}));

    await expect(exportOrderInquiryXlsx('oi-1')).rejects.toThrow(
      /Failed to start the order inquiry export/i,
    );
  });
});

describe('exportOrderInquiryWorklistXlsx (AC-B6)', () => {
  it('POSTs to the list export route with the current filters as a JSON body', async () => {
    const { exportOrderInquiryWorklistXlsx } = await import('./orderInquiryService');
    const download = {
      id: 'dl-2',
      kind: 'order_inquiry_worklist_xlsx',
      status: 'pending',
      filename: 'order-inquiries-23092026.xlsx',
    };
    mockFetch.mockResolvedValue(ok(download));

    const result = await exportOrderInquiryWorklistXlsx({
      ack: 'rejected',
      delivery_month: '2026-10',
      page: 3,
      limit: 25,
      sort: 'delivery_date',
      dir: 'desc',
    });

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/project-sales/order-inquiries/export',
      expect.objectContaining({ method: 'POST' }),
    );
    const call = mockFetch.mock.calls[0][1] as { body: string; headers?: Record<string, string> };
    expect(JSON.parse(call.body)).toMatchObject({
      ack: 'rejected',
      delivery_month: '2026-10',
    });
    // Never page/limit/sort/dir - the export is the whole filtered set, unpaged.
    const parsed = JSON.parse(call.body);
    expect(parsed).not.toHaveProperty('page');
    expect(parsed).not.toHaveProperty('limit');
    expect(parsed).not.toHaveProperty('sort');
    expect(parsed).not.toHaveProperty('dir');
    expect(result).toEqual(download);
  });

  it('throws the extracted error message on failure', async () => {
    const { exportOrderInquiryWorklistXlsx } = await import('./orderInquiryService');
    mockFetch.mockResolvedValue(failed(409, { detail: 'already in flight' }));

    await expect(exportOrderInquiryWorklistXlsx({})).rejects.toThrow('already in flight');
  });
});
