import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import {
  getProducts,
  setVariantParent,
  unlinkVariant,
  resetVariantAuto,
  getProductsForVariantSelect,
} from './productService';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function ok(body: unknown = {}) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response;
}

function calledUrl(idx = 0): string {
  return String(mockApiFetch.mock.calls[idx][0]);
}

function calledInit(idx = 0): RequestInit {
  return mockApiFetch.mock.calls[idx][1] as RequestInit;
}

beforeEach(() => {
  mockApiFetch.mockReset();
  mockApiFetch.mockResolvedValue(ok());
});

const base = { pageIndex: 0, pageSize: 50, sorting: [], searchQuery: '' } as const;

describe('getProducts variant_filter param', () => {
  it('omits variant_filter by default (treated as "all")', async () => {
    await getProducts({ ...base });
    expect(calledUrl()).not.toContain('variant_filter');
  });

  it('omits variant_filter when explicitly "all"', async () => {
    await getProducts({ ...base, variant_filter: 'all' });
    expect(calledUrl()).not.toContain('variant_filter');
  });

  it('appends variant_filter=base', async () => {
    await getProducts({ ...base, variant_filter: 'base' });
    expect(calledUrl()).toContain('variant_filter=base');
  });

  it('appends variant_filter=variant', async () => {
    await getProducts({ ...base, variant_filter: 'variant' });
    expect(calledUrl()).toContain('variant_filter=variant');
  });
});

describe('setVariantParent', () => {
  it('PUTs to the variant-parent endpoint with the parent_id body', async () => {
    mockApiFetch.mockResolvedValue(ok({ id: 'p1', variant_link_manual: true }));
    const result = await setVariantParent('p1', 'SRTKT71SS');

    expect(calledUrl()).toBe('/api/v1/master-data/products/p1/variant-parent');
    expect(calledInit().method).toBe('PUT');
    expect(JSON.parse(String(calledInit().body))).toEqual({ parent_id: 'SRTKT71SS' });
    expect(result).toEqual({ id: 'p1', variant_link_manual: true });
  });

  it('throws the extracted API error message on failure', async () => {
    mockApiFetch.mockResolvedValue({
      ok: false,
      status: 400,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ detail: 'A product cannot be a variant of itself' }),
    } as Response);

    await expect(setVariantParent('p1', 'p1')).rejects.toThrow(
      'A product cannot be a variant of itself',
    );
  });
});

describe('unlinkVariant', () => {
  it('DELETEs the variant-parent endpoint', async () => {
    await unlinkVariant('p1');
    expect(calledUrl()).toBe('/api/v1/master-data/products/p1/variant-parent');
    expect(calledInit().method).toBe('DELETE');
  });
});

describe('resetVariantAuto', () => {
  it('POSTs to the variant-reset endpoint', async () => {
    await resetVariantAuto('p1');
    expect(calledUrl()).toBe('/api/v1/master-data/products/p1/variant-reset');
    expect(calledInit().method).toBe('POST');
  });
});

describe('getProductsForVariantSelect', () => {
  it('maps /select rows to human-readable refs (id + code + name)', async () => {
    mockApiFetch.mockResolvedValue(
      ok({
        data: [
          { id: 'u1', product_code: 'SRTKT71SS', product_name: 'Kitchen Tap 71' },
        ],
      }),
    );

    const rows = await getProductsForVariantSelect('SRT');
    expect(calledUrl()).toContain('/api/v1/master-data/products/select?');
    expect(calledUrl()).toContain('query=SRT');
    expect(rows).toEqual([
      { id: 'u1', product_code: 'SRTKT71SS', product_name: 'Kitchen Tap 71' },
    ]);
  });
});
