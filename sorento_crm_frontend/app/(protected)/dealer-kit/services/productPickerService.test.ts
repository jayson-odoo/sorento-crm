/**
 * The picker must search on the SERVER.
 *
 * This is a regression guard, not paperwork. The first version of this service
 * fetched one page and let the caller filter it in the browser, so a search for
 * a code shared by 998 products answered "no products match" - the term never
 * left the client, and most of a 22,000-product catalogue was unreachable from
 * every dealer-kit picker at once.
 *
 * So the assertions are about the REQUEST: the search term travels, and the
 * page index becomes a real offset.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PICKER_PAGE_SIZE, listPickerProducts } from './productPickerService';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';

const fetchMock = vi.mocked(apiFetch);

function respondWith(rows: unknown[]) {
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({ data: rows }),
  } as unknown as Response);
}

/** The query string of the single call made. */
function requestedParams(): URLSearchParams {
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const url = String(fetchMock.mock.calls[0][0]);
  return new URLSearchParams(url.split('?')[1] ?? '');
}

afterEach(() => {
  fetchMock.mockReset();
});

describe('listPickerProducts', () => {
  it('sends the search term to the server', async () => {
    respondWith([]);
    await listPickerProducts('SRTWC');
    expect(requestedParams().get('query')).toBe('SRTWC');
  });

  it('trims the search term, and omits it when it is only whitespace', async () => {
    respondWith([]);
    await listPickerProducts('  SRTWC  ');
    expect(requestedParams().get('query')).toBe('SRTWC');

    fetchMock.mockReset();
    respondWith([]);
    await listPickerProducts('   ');
    // An empty `query=` would be a filter matching nothing on some backends;
    // absent means "no filter".
    expect(requestedParams().has('query')).toBe(false);
  });

  it('turns a page index into an offset, not a repeat of page one', async () => {
    respondWith([]);
    await listPickerProducts('', 3);
    const params = requestedParams();
    expect(params.get('limit')).toBe(String(PICKER_PAGE_SIZE));
    expect(params.get('offset')).toBe(String(3 * PICKER_PAGE_SIZE));
  });

  it('asks for the first page with offset 0', async () => {
    respondWith([]);
    await listPickerProducts();
    expect(requestedParams().get('offset')).toBe('0');
  });

  it('honours a caller-supplied page size in BOTH limit and offset', async () => {
    respondWith([]);
    await listPickerProducts('', 2, 10);
    const params = requestedParams();
    expect(params.get('limit')).toBe('10');
    // Using the default page size here would skip rows 20-99 silently.
    expect(params.get('offset')).toBe('20');
  });

  it('maps a row to what a picker shows, and never leaks an id as a label', async () => {
    respondWith([
      {
        id: 'aaaaaaaa-0000-0000-0000-000000000001',
        product_code: 'SRTWC-100',
        product_name: 'Wall tile 100',
        category_name: 'Tiles',
        brand_name: 'Sorento',
        list_price: '12.5',
        is_discontinued: true,
      },
    ]);

    const [product] = await listPickerProducts();
    expect(product.code).toBe('SRTWC-100');
    expect(product.name).toBe('Wall tile 100');
    expect(product.category).toBe('Tiles');
    expect(product.brand).toBe('Sorento');
    expect(product.price).toBe('MYR 12.50');
    expect(product.isDiscontinued).toBe(true);
  });

  it('leaves the price blank rather than printing MYR NaN', async () => {
    respondWith([
      {
        id: 'aaaaaaaa-0000-0000-0000-000000000002',
        product_code: 'SRTWC-200',
        product_name: 'Wall tile 200',
        list_price: null,
      },
    ]);

    const [product] = await listPickerProducts();
    expect(product.price).toBe('');
    expect(product.isDiscontinued).toBe(false);
  });

  it('accepts a bare array body as well as { data }', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [
        { id: 'x', product_code: 'A', product_name: 'B' },
      ],
    } as unknown as Response);

    const rows = await listPickerProducts();
    expect(rows).toHaveLength(1);
  });
});
