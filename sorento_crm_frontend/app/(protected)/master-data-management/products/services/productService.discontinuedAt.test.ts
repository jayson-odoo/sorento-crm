/**
 * `getProducts` - `discontinued_from` / `discontinued_to` query params (issue #1287,
 * AC-FLT-5). Copied from `productService.discontinuedBatch.test.ts`'s harness.
 *
 * RED for Phase 2: `GetProductsParams` has no `discontinued_from` / `discontinued_to`
 * fields and `getProducts` never puts them on the query string, so both assertions below
 * fail against TODAY's code - the query string never contains either param, whether it was
 * passed or not.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { getProducts } from './productService';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function ok() {
  return {
    ok: true,
    status: 200,
    json: async () => ({ data: [], pagination: {} }),
  } as Response;
}

function calledUrl(): string {
  return String(mockApiFetch.mock.calls[0][0]);
}

beforeEach(() => {
  mockApiFetch.mockReset();
  mockApiFetch.mockResolvedValue(ok());
});

const base = { pageIndex: 0, pageSize: 50, sorting: [], searchQuery: '' };

describe('getProducts discontinued_from / discontinued_to params', () => {
  it('sends discontinued_from and discontinued_to', async () => {
    await getProducts({
      ...base,
      discontinued_from: '2026-09-01',
      discontinued_to: '2026-09-26',
      // `GetProductsParams` does not declare these fields yet (this lane adds them) -
      // cast rather than `@ts-expect-error`, so the directive does not go stale (and
      // start failing the build for an unrelated reason) the moment the coder does.
    } as unknown as Parameters<typeof getProducts>[0]);
    const url = calledUrl();
    expect(url).toContain('discontinued_from=2026-09-01');
    expect(url).toContain('discontinued_to=2026-09-26');
  });

  it('omits them when unset', async () => {
    await getProducts({ ...base });
    const url = calledUrl();
    expect(url).not.toContain('discontinued_from');
    expect(url).not.toContain('discontinued_to');
  });
});
