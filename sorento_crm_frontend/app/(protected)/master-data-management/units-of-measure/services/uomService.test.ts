/**
 * Units of measure - feature service (AC-F12, slice S2-BE-1).
 *
 * `decimal_places` travels on every shape the unit already travels in - this
 * pins that CREATE and UPDATE payloads carry it through untouched (never
 * defaulted or dropped client-side; the backend owns the create-time default
 * and the edit-time "omitted preserves stored value" rule), that `getUOMs`
 * builds its query string with the shared `buildDataGridParams` helper (not a
 * hand-rolled `URLSearchParams`, per `docs/ARCHITECTURE-RULES.md`), and that a
 * write failure surfaces the backend's own message via `extractApiError` rather
 * than a generic string.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { createUOM, deleteUOM, getUOM, getUOMs, updateUOM } from './uomService';

const mockedFetch = vi.mocked(apiFetch);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function calledUrl(): URL {
  const calls = mockedFetch.mock.calls;
  const raw = String(calls[calls.length - 1][0]);
  return new URL(raw, 'http://x');
}

function lastInit(): RequestInit {
  const calls = mockedFetch.mock.calls;
  return (calls[calls.length - 1][1] ?? {}) as RequestInit;
}

beforeEach(() => vi.clearAllMocks());

describe('getUOMs - query string via buildDataGridParams', () => {
  const LIST_RESPONSE = { data: [], empty: true, pagination: { total: 0, page: 1 } };

  it('builds page, limit, sort, dir and query when sorted and searched', async () => {
    mockedFetch.mockResolvedValue(jsonResponse(LIST_RESPONSE));

    await getUOMs({
      pageIndex: 2,
      pageSize: 10,
      sorting: [{ id: 'uom_code', desc: true }],
      searchQuery: 'kilogram',
    });

    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/master-data/units-of-measure');
    expect(u.searchParams.get('page')).toBe('3'); // 0-based pageIndex -> 1-based page
    expect(u.searchParams.get('limit')).toBe('10');
    expect(u.searchParams.get('sort')).toBe('uom_code');
    expect(u.searchParams.get('dir')).toBe('desc');
    expect(u.searchParams.get('query')).toBe('kilogram');
    // Exactly these five params - buildDataGridParams' own contract, asserted here
    // so a hand-rolled URLSearchParams regression is caught at this call site.
    expect([...u.searchParams.keys()].sort()).toEqual(['dir', 'limit', 'page', 'query', 'sort']);
  });

  it('omits sort, dir and query when unset - no empty params on the wire', async () => {
    mockedFetch.mockResolvedValue(jsonResponse(LIST_RESPONSE));

    await getUOMs({ pageIndex: 0, pageSize: 25, sorting: [], searchQuery: '' });

    const u = calledUrl();
    expect(u.searchParams.get('page')).toBe('1');
    expect(u.searchParams.get('limit')).toBe('25');
    expect(u.searchParams.has('sort')).toBe(false);
    expect(u.searchParams.has('dir')).toBe(false);
    expect(u.searchParams.has('query')).toBe(false);
  });

  it('returns decimal_places on every listed row untouched', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({
        data: [{ id: 'u1', uom_code: 'KG', uom_name: 'Kilogram', decimal_places: 3, is_active: true }],
        empty: false,
        pagination: { total: 1, page: 1 },
      }),
    );

    const page = await getUOMs({ pageIndex: 0, pageSize: 25 });
    expect(page.data[0].decimal_places).toBe(3);
  });

  it('throws a generic failure message rather than the backend detail on a failed read', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({ detail: 'should not surface' }, 500));
    await expect(getUOMs({ pageIndex: 0, pageSize: 25 })).rejects.toThrow('Failed to fetch UOMs');
  });
});

describe('getUOM - single read', () => {
  it('requests the unit by id and returns its decimal_places', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ id: 'u1', uom_code: 'EA', uom_name: 'Each', decimal_places: 0, is_active: true }),
    );
    const uom = await getUOM('u1');
    expect(calledUrl().pathname).toBe('/api/v1/master-data/units-of-measure/u1');
    expect(uom.decimal_places).toBe(0);
  });

  it('throws a generic failure message on a failed read', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({}, 404));
    await expect(getUOM('missing')).rejects.toThrow('Failed to fetch UOM');
  });
});

describe('createUOM - decimal_places passes through on write', () => {
  it('POSTs decimal_places verbatim alongside the rest of the form', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({
        id: 'u2',
        uom_code: 'L',
        uom_name: 'Litre',
        decimal_places: 2,
        is_active: true,
      }),
    );

    const created = await createUOM({
      uom_code: 'L',
      uom_name: 'Litre',
      decimal_places: 2,
      is_active: true,
    });

    const init = lastInit();
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toMatchObject({ uom_code: 'L', decimal_places: 2 });
    expect(created.decimal_places).toBe(2);
  });

  it('omits decimal_places from the body when the caller supplies none, rather than defaulting client-side', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ id: 'u3', uom_code: 'EA', uom_name: 'Each', decimal_places: 0, is_active: true }),
    );

    await createUOM({ uom_code: 'EA', uom_name: 'Each', is_active: true });

    expect(JSON.parse(String(lastInit().body))).not.toHaveProperty('decimal_places');
  });

  it('surfaces the backend validation message via extractApiError on a 422', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ detail: 'decimal_places must be between 0 and 4' }, 422),
    );

    await expect(
      createUOM({ uom_code: 'BAD', uom_name: 'Bad unit', decimal_places: 7, is_active: true }),
    ).rejects.toThrow('decimal_places must be between 0 and 4');
  });

  it('falls back to the generic message when the 4xx body carries no detail', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({}, 400));
    await expect(
      createUOM({ uom_code: 'X', uom_name: 'X', is_active: true }),
    ).rejects.toThrow('Failed to create UOM');
  });
});

describe('updateUOM - decimal_places passes through on write', () => {
  it('PUTs decimal_places verbatim when the caller changes it', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ id: 'u1', uom_code: 'KG', uom_name: 'Kilogram', decimal_places: 3, is_active: true }),
    );

    const updated = await updateUOM('u1', { decimal_places: 3 });

    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/master-data/units-of-measure/u1');
    expect(lastInit().method).toBe('PUT');
    expect(JSON.parse(String(lastInit().body))).toEqual({ decimal_places: 3 });
    expect(updated.decimal_places).toBe(3);
  });

  it('omits decimal_places from a partial update that does not touch it, so the stored value is preserved server-side', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ id: 'u1', uom_code: 'KG', uom_name: 'Kilogram v2', decimal_places: 3, is_active: true }),
    );

    await updateUOM('u1', { uom_name: 'Kilogram v2' });

    expect(JSON.parse(String(lastInit().body))).not.toHaveProperty('decimal_places');
  });

  it('surfaces the backend validation message via extractApiError on a 422', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ detail: 'decimal_places must be between 0 and 4' }, 422),
    );

    await expect(updateUOM('u1', { decimal_places: 9 })).rejects.toThrow(
      'decimal_places must be between 0 and 4',
    );
  });

  it('falls back to the generic message when the 4xx body carries no detail', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({}, 400));
    await expect(updateUOM('u1', { uom_name: 'X' })).rejects.toThrow('Failed to update UOM');
  });
});

describe('deleteUOM - write path also uses extractApiError', () => {
  it('DELETEs by id and resolves with no body on success', async () => {
    mockedFetch.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(deleteUOM('u1')).resolves.toBeUndefined();
    expect(calledUrl().pathname).toBe('/api/v1/master-data/units-of-measure/u1');
    expect(lastInit().method).toBe('DELETE');
  });

  it('surfaces the backend message when the unit is still referenced', async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({ detail: 'Unit of measure is in use and cannot be deleted' }, 409),
    );
    await expect(deleteUOM('u1')).rejects.toThrow(
      'Unit of measure is in use and cannot be deleted',
    );
  });
});
