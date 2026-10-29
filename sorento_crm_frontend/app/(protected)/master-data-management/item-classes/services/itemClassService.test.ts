import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import {
  createItemClass,
  getItemClasses,
  getItemClassSelect,
  updateItemClass,
} from './itemClassService';

const mockedFetch = vi.mocked(apiFetch);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function calledUrl(): URL {
  const calls = mockedFetch.mock.calls;
  return new URL(String(calls[calls.length - 1][0]), 'http://x');
}

beforeEach(() => vi.clearAllMocks());

describe('itemClassService', () => {
  it('lists through buildDataGridParams on the item-classes base', async () => {
    mockedFetch.mockImplementation(async () => jsonResponse({ data: [], pagination: { total: 0 } }));
    await getItemClasses({
      pageIndex: 1,
      pageSize: 25,
      sorting: [{ id: 'item_class_name', desc: true }],
      searchQuery: 'cab',
    });
    const url = calledUrl();
    expect(url.pathname).toBe('/api/v1/master-data/item-classes/');
    expect(url.searchParams.get('page')).toBe('2');
    expect(url.searchParams.get('limit')).toBe('25');
    expect(url.searchParams.get('sort')).toBe('item_class_name');
    expect(url.searchParams.get('dir')).toBe('desc');
    expect(url.searchParams.get('query')).toBe('cab');
  });

  it('select sends brand_id only when a brand is given', async () => {
    mockedFetch.mockImplementation(async () => jsonResponse([]));
    await getItemClassSelect();
    expect(calledUrl().pathname).toBe('/api/v1/master-data/item-classes/select');
    expect(calledUrl().search).toBe('');
    await getItemClassSelect('b-1');
    expect(calledUrl().searchParams.get('brand_id')).toBe('b-1');
  });

  it('create and update send JSON bodies', async () => {
    mockedFetch.mockImplementation(async () => jsonResponse({ id: 'c1' }));
    await createItemClass({ item_class_code: 'A', item_class_name: 'Alpha', is_active: true });
    const init = mockedFetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toMatchObject({ item_class_code: 'A' });
    await updateItemClass('c1', { is_active: false });
    expect(calledUrl().pathname).toBe('/api/v1/master-data/item-classes/c1');
    expect((mockedFetch.mock.calls[1][1] as RequestInit).method).toBe('PUT');
  });

  it('surfaces the backend message on failure', async () => {
    mockedFetch.mockImplementation(async () => jsonResponse({ detail: 'Code already exists' }, 409));
    await expect(
      createItemClass({ item_class_code: 'A', item_class_name: 'Alpha', is_active: true }),
    ).rejects.toThrow('Code already exists');
  });
});
