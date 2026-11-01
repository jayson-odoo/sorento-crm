/**
 * PRICETAG-COMBO: the service calls behind the designer's Preview combo (AC-5.1 to AC-5.3).
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). `comboOptions` does not exist and
 * `getProductTagData` takes no combo yet.
 *
 * Assumed call shapes (the route is the UAC's; the function names follow the file's
 * `productOptions` / `getProductTagData` neighbours): `comboOptions(query)` and
 * `getProductTagData(productId, promotionId, comboId)`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import * as service from './tagDataService';

const fetchMock = vi.mocked(apiFetch);

function ok(body: unknown) {
  fetchMock.mockResolvedValue({ ok: true, json: async () => body } as unknown as Response);
}

afterEach(() => fetchMock.mockReset());

describe('comboOptions', () => {
  it('searches the server by the typed term, bounded by a limit', async () => {
    ok({ data: [] });
    await (service as unknown as { comboOptions: (q: string) => Promise<unknown> }).comboOptions('3 in');

    const url = new URL(String(fetchMock.mock.calls[0][0]), 'http://x');
    expect(url.pathname).toBe('/api/v1/dealer-kit/tag-data/combos');
    expect(url.searchParams.get('query')).toBe('3 in');
    expect(Number(url.searchParams.get('limit'))).toBeGreaterThan(0);
  });

  it('maps a combo to an option: name as the label, the host code under it, never an id on screen', async () => {
    ok({
      data: [
        { combo_id: 'combo-1', name: '3 in 1', host_product_id: 'p-host', host_code: 'ZZHOST1' },
      ],
    });
    const options = await (
      service as unknown as {
        comboOptions: (q: string) => Promise<{ value: string; label: string; description?: string }[]>;
      }
    ).comboOptions('');

    expect(options).toHaveLength(1);
    expect(options[0].value).toBe('combo-1');
    expect(options[0].label).toBe('3 in 1');
    expect(options[0].description).toBe('ZZHOST1');
  });

  it('raises the server message on failure', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ message: 'No access' }),
    } as unknown as Response);
    await expect(
      (service as unknown as { comboOptions: (q: string) => Promise<unknown> }).comboOptions('x'),
    ).rejects.toThrow();
  });
});

describe('getProductTagData with a combo', () => {
  it('sends combo_id when given', async () => {
    ok({ id: 'p1', combo: null });
    await (
      service.getProductTagData as unknown as (a: string, b?: string | null, c?: string | null) => Promise<unknown>
    )('p1', null, 'combo-1');
    const url = new URL(String(fetchMock.mock.calls[0][0]), 'http://x');
    expect(url.pathname).toBe('/api/v1/dealer-kit/products/p1/tag-data');
    expect(url.searchParams.get('combo_id')).toBe('combo-1');
  });

  it('sends no combo_id when omitted, so today\'s call is unchanged', async () => {
    ok({ id: 'p1' });
    await service.getProductTagData('p1', 'promo-1');
    const url = new URL(String(fetchMock.mock.calls[0][0]), 'http://x');
    expect(url.searchParams.get('combo_id')).toBeNull();
    expect(url.searchParams.get('promotion_id')).toBe('promo-1');
  });
});
