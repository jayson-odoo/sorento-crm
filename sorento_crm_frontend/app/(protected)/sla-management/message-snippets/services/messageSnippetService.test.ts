/**
 * messageSnippetService - the wire calls (UAC AC-L4, slice S4.4).
 *
 * Pins the URLs and shapes the backend contract promises, so a rename on either
 * side breaks here rather than in a customer's composer.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import {
  createMessageSnippet,
  deleteMessageSnippet,
  getMessageSnippetOptions,
  listMessageSnippets,
  updateMessageSnippet,
} from './messageSnippetService';

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  };
}

function fail(status: number, body: unknown) {
  return {
    ok: false,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

const BASE = '/api/v1/sla-management/message-snippets';

beforeEach(() => {
  apiFetch.mockReset();
});

describe('listMessageSnippets', () => {
  it('uses the shared DataGrid params', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 10 } }));

    await listMessageSnippets({
      pageIndex: 1,
      pageSize: 10,
      searchQuery: 'stock',
      sorting: [{ id: 'name', desc: true }],
    });

    const url = apiFetch.mock.calls[0][0] as string;
    expect(url.startsWith(`${BASE}?`)).toBe(true);
    expect(url).toContain('page=2');
    expect(url).toContain('limit=10');
    expect(url).toContain('sort=name');
    expect(url).toContain('dir=desc');
    expect(url).toContain('query=stock');
  });

  it('surfaces the backend message on failure', async () => {
    apiFetch.mockResolvedValue(fail(500, { message: 'Boom' }));

    await expect(listMessageSnippets({ pageIndex: 0, pageSize: 10 })).rejects.toThrow('Boom');
  });
});

describe('write calls', () => {
  it('POSTs a create', async () => {
    apiFetch.mockResolvedValue(ok({ id: 's1' }));

    await createMessageSnippet({ name: 'Stock', shortcut: 'stock', body: 'x', is_active: true });

    expect(apiFetch).toHaveBeenCalledWith(
      BASE,
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('surfaces a duplicate shortcut as its own message', async () => {
    apiFetch.mockResolvedValue(
      fail(409, { message: "A snippet with the shortcut 'stock' already exists." }),
    );

    await expect(
      createMessageSnippet({ name: 'Other', shortcut: 'stock', body: 'x', is_active: true }),
    ).rejects.toThrow("A snippet with the shortcut 'stock' already exists.");
  });

  it('PUTs an update against the id', async () => {
    apiFetch.mockResolvedValue(ok({ id: 's1' }));

    await updateMessageSnippet('s1', { name: 'New' });

    expect(apiFetch).toHaveBeenCalledWith(
      `${BASE}/s1`,
      expect.objectContaining({ method: 'PUT' }),
    );
  });

  it('DELETEs against the id', async () => {
    apiFetch.mockResolvedValue(ok({ message: 'deleted' }));

    await deleteMessageSnippet('s1');

    expect(apiFetch).toHaveBeenCalledWith(`${BASE}/s1`, { method: 'DELETE' });
  });
});

describe('getMessageSnippetOptions', () => {
  it('passes the ticket so the bodies come back resolved', async () => {
    apiFetch.mockResolvedValue(ok([]));

    await getMessageSnippetOptions({ trackingId: 't1' });

    expect(apiFetch).toHaveBeenCalledWith(`${BASE}/select?tracking_id=t1`);
  });

  it('works with no ticket at all', async () => {
    apiFetch.mockResolvedValue(ok([]));

    await getMessageSnippetOptions({});

    expect(apiFetch).toHaveBeenCalledWith(`${BASE}/select`);
  });

  it('returns both the stored and the resolved body', async () => {
    apiFetch.mockResolvedValue(
      ok([
        {
          id: 's1',
          name: 'Stock check',
          shortcut: 'stock',
          body: 'Hi $contact_name',
          resolved_body: 'Hi Aisyah Rahman',
        },
      ]),
    );

    const items = await getMessageSnippetOptions({ trackingId: 't1' });

    expect(items[0].body).toBe('Hi $contact_name');
    expect(items[0].resolved_body).toBe('Hi Aisyah Rahman');
  });
});
