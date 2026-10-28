/**
 * QUOTE-STOCK-AGENT-LOC (AC-QSA-21, AC-QSA-22): `getQuotationLineStock` asks the quotation-only
 * stock read for one product and passes a JSON null (the user may see no stock) through as null.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
});

describe('getQuotationLineStock', () => {
  const apiFetch = vi.fn();

  async function load() {
    vi.doMock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));
    vi.doMock('@/lib/api-client', async (importOriginal) => {
      const actual = await importOriginal<typeof import('@/lib/api-client')>();
      return { ...actual, extractApiError: vi.fn(async () => 'Backend said no') };
    });
    return import('./fulfilmentPlanningService');
  }

  it('GETs the quotation-line-stock url with the product id and returns the body', async () => {
    const detail = { available_qty: '25', locations: [], incoming: [] };
    apiFetch.mockResolvedValue({ ok: true, json: async () => detail } as Response);
    const service = await load();
    const result = await (service as unknown as {
      getQuotationLineStock: (id: string) => Promise<unknown>;
    }).getQuotationLineStock('prod-1');
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(String(apiFetch.mock.calls[0][0])).toMatch(
      /\/project-sales\/quotation-line-stock\?product_id=prod-1$/,
    );
    expect(result).toEqual(detail);
  });

  it('resolves null when the body is JSON null', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => null } as Response);
    const service = await load();
    const result = await (service as unknown as {
      getQuotationLineStock: (id: string) => Promise<unknown>;
    }).getQuotationLineStock('prod-1');
    expect(result).toBeNull();
  });
});
