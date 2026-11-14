/**
 * OCN-ORDER-CHANGE-NOTICE red tests: the feature service (UI -> hooks -> service -> lib/api).
 * Component: ./orderChangeNoticeService.ts
 *
 * Wire shapes follow the backend suites (sorento_crm_backend/tests/test_ocn_routes.py,
 * _ocn_support.py): routes under /api/v1/procurement/order-change-notices, one POST per move,
 * the revision number travels as X-Revision-No (UAC B9), bodies {reason} / {action, comments} /
 * {cs_comment}. A list sends sort + dir to the server (owner rule: every column sorts there).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiFetch: vi.fn(
      async () =>
        new Response(JSON.stringify({ id: 'ocn-1', data: [], pagination: { total: 0 } }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    ),
  };
});

import { apiFetch } from '@/lib/api';
import {
  createOrderChangeNotice,
  decideOrderChangeNotice,
  getOrderChangeNotice,
  listChangeTypes,
  listOrderChangeNotices,
  markDone,
  reviseOrderChangeNotice,
  sendBack,
  sendForApproval,
  submitOrderChangeNotice,
  updateOrderChangeNotice,
  voidOrderChangeNotice,
} from './orderChangeNoticeService';

const BASE = '/api/v1/procurement/order-change-notices';
const asMock = apiFetch as unknown as ReturnType<typeof vi.fn>;

const lastCall = () => asMock.mock.calls[asMock.mock.calls.length - 1] as [string, RequestInit | undefined];
const lastUrl = () => new URL(lastCall()[0], 'http://localhost');
const lastMethod = () => (lastCall()[1]?.method ?? 'GET').toUpperCase();
const lastBody = () => JSON.parse(String(lastCall()[1]?.body));
const lastHeader = (name: string) => new Headers((lastCall()[1]?.headers ?? {}) as HeadersInit).get(name);
const setOf = (values: string[]) =>
  values.flatMap((v) => v.split(',')).map((s) => s.trim()).filter(Boolean).sort();

beforeEach(() => asMock.mockClear());

describe('listOrderChangeNotices', () => {
  it('asks the server to sort: sort and dir travel with page and limit', async () => {
    await listOrderChangeNotices({
      pageIndex: 1,
      pageSize: 25,
      sorting: [{ id: 'ocn_date', desc: true }],
    });
    const url = lastUrl();
    expect(url.pathname).toBe(BASE);
    expect(lastMethod()).toBe('GET');
    expect(url.searchParams.get('sort')).toBe('ocn_date');
    expect(url.searchParams.get('dir')).toBe('desc');
    expect(url.searchParams.get('page')).toBe('2');
    expect(url.searchParams.get('limit')).toBe('25');
  });

  it('sends the search text as the standard DataGrid query', async () => {
    await listOrderChangeNotices({ pageIndex: 0, pageSize: 25, sorting: [], searchQuery: 'XT04/3871' });
    expect(lastUrl().searchParams.get('query')).toBe('XT04/3871');
  });

  it('sends status, change type and risk as sets (comma list in, every value out)', async () => {
    await listOrderChangeNotices({
      pageIndex: 0,
      pageSize: 25,
      sorting: [],
      status: 'draft,approved',
      changeTypeId: 'ct-delay,ct-cancel',
      riskLevel: 'High,Highest',
    });
    const sp = lastUrl().searchParams;
    expect(setOf(sp.getAll('status'))).toEqual(['approved', 'draft']);
    expect(setOf(sp.getAll('change_type_id'))).toEqual(['ct-cancel', 'ct-delay']);
    expect(setOf(sp.getAll('risk_level'))).toEqual(['High', 'Highest']);
  });

  it('sends no filter keys when nothing is chosen', async () => {
    await listOrderChangeNotices({ pageIndex: 0, pageSize: 25, sorting: [] });
    const sp = lastUrl().searchParams;
    for (const key of ['status', 'change_type_id', 'risk_level', 'sort', 'dir']) {
      expect(sp.has(key), key).toBe(false);
    }
  });

  it('throws the server sentence when the list cannot load', async () => {
    asMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'You cannot view order change notices' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    await expect(
      listOrderChangeNotices({ pageIndex: 0, pageSize: 25, sorting: [] }),
    ).rejects.toThrow('You cannot view order change notices');
  });
});

describe('record reads and writes', () => {
  it('getOrderChangeNotice reads GET /{id}', async () => {
    await getOrderChangeNotice('ocn-1');
    expect(lastUrl().pathname).toBe(`${BASE}/ocn-1`);
    expect(lastMethod()).toBe('GET');
  });

  it('createOrderChangeNotice POSTs the body as given', async () => {
    const body = {
      change_type_id: 'ct-delay',
      customer_name: 'Customer A',
      customer_po_no: 'XT04/3871 (R1)',
      lines: [{ product_id: 'p-1', qty_before: '100', qty_after: '100' }],
    };
    await createOrderChangeNotice(body as never);
    expect(lastUrl().pathname).toBe(BASE);
    expect(lastMethod()).toBe('POST');
    expect(lastBody()).toMatchObject(body);
  });

  it('updateOrderChangeNotice PUTs /{id}', async () => {
    await updateOrderChangeNotice('ocn-1', { description: 'New dates' } as never);
    expect(lastUrl().pathname).toBe(`${BASE}/ocn-1`);
    expect(lastMethod()).toBe('PUT');
    expect(lastBody()).toMatchObject({ description: 'New dates' });
  });

  it('listChangeTypes reads the change type lookup', async () => {
    asMock.mockResolvedValueOnce(
      new Response(JSON.stringify([{ id: 'ct-delay', name: 'Delay', risk_level: 'Low' }]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const types = await listChangeTypes();
    expect(lastMethod()).toBe('GET');
    expect(lastUrl().pathname).toMatch(/change-types/);
    expect(Array.isArray(types)).toBe(true);
  });
});

describe('the moves carry the revision number and the body the backend reads', () => {
  const moves: Array<[string, string, (rev: number) => Promise<unknown>, unknown]> = [
    ['submit', 'submit', (rev) => submitOrderChangeNotice('ocn-1', rev), undefined],
    ['send for approval', 'send-for-approval', (rev) => sendForApproval('ocn-1', rev), undefined],
    ['send back', 'reject-submitted', (rev) => sendBack('ocn-1', rev, 'Add the PO copy'), { reason: 'Add the PO copy' }],
    [
      'approve',
      'approval-decision',
      (rev) => decideOrderChangeNotice('ocn-1', rev, 'approved', null),
      { action: 'approved', comments: null },
    ],
    [
      'reject',
      'approval-decision',
      (rev) => decideOrderChangeNotice('ocn-1', rev, 'rejected', 'Wrong quantity'),
      { action: 'rejected', comments: 'Wrong quantity' },
    ],
    ['mark done', 'done', (rev) => markDone('ocn-1', rev, 'Keyed into the SO'), { cs_comment: 'Keyed into the SO' }],
    ['void', 'void', (rev) => voidOrderChangeNotice('ocn-1', rev, 'Customer withdrew it'), { reason: 'Customer withdrew it' }],
    ['revise', 'revise', (rev) => reviseOrderChangeNotice('ocn-1', rev, 'Customer changed the dates'), { reason: 'Customer changed the dates' }],
  ];

  it.each(moves)('%s POSTs /{id}/%s with X-Revision-No', async (_name, path, run, body) => {
    await run(3);
    expect(lastUrl().pathname).toBe(`${BASE}/ocn-1/${path}`);
    expect(lastMethod()).toBe('POST');
    expect(lastHeader('X-Revision-No')).toBe('3');
    if (body !== undefined) expect(lastBody()).toEqual(body);
  });

  it('a revision of 0 is still sent (a first-revision record is fenced too)', async () => {
    await submitOrderChangeNotice('ocn-1', 0);
    expect(lastHeader('X-Revision-No')).toBe('0');
  });

  it('a stale revision (409) reaches the caller as the server sentence', async () => {
    asMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: 'This order change notice was revised while you were working on it.' }),
        { status: 409, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    await expect(submitOrderChangeNotice('ocn-1', 0)).rejects.toThrow(/revised while you were working/);
  });
});
