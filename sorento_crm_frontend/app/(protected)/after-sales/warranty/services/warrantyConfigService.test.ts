/**
 * AFTER-SALES-P2 red tests (UAC C, P1): the wire contract of the warranty configuration API.
 * Paths, methods and bodies are asserted: a key typo is a silently dropped field.
 *
 * Module the coder builds: `./warrantyConfigService` (this folder), every call through apiFetch and
 * extractApiError, base `/api/v1/after-sales/warranty`:
 *   getPolicies(params) / getPolicy(id) / createPolicy(v) / updatePolicy(id, v) PATCH / deletePolicy(id)
 *   supersedePolicy(id, { version, effective_from, policy_text? })   POST .../policies/{id}/supersede
 *   getTerms(policyId)                                               GET  .../terms?policy_id=
 *   getKinds(params & { is_active?: string[]; has_no_rule?: boolean })
 *   createKind / updateKind(id, v) PATCH / deleteKind(id)
 *   getRules(params & { kind_id?: string[] }) / createRule / updateRule(id, v) PATCH / deleteRule(id)
 *   testKindRules(productId)                                         POST .../kind-rules/test { product_id }
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import {
  deletePolicy,
  getKinds,
  getPolicies,
  getRules,
  getTerms,
  supersedePolicy,
  testKindRules,
  updateKind,
} from './warrantyConfigService';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;
const BASE = '/api/v1/after-sales/warranty';
const grid = { pageIndex: 1, pageSize: 25, sorting: [{ id: 'version', desc: true }], searchQuery: 'v1' };

beforeEach(() => apiFetch.mockReset());

describe('warrantyConfigService', () => {
  it('lists policies with the data grid params', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 2, limit: 25 } }));
    await getPolicies(grid);
    const url = String(apiFetch.mock.calls.at(-1)![0]);
    expect(url.startsWith(`${BASE}/policies?`)).toBe(true);
    expect(url).toContain('page=2');
    expect(url).toContain('limit=25');
    expect(url).toContain('sort=version');
    expect(url).toContain('dir=desc');
    expect(url).toContain('query=v1');
  });

  it('supersede posts the new version and start date', async () => {
    apiFetch.mockResolvedValue(ok({ closed: {}, created: {} }));
    await supersedePolicy('pol-1', { version: 'v16', effective_from: '2027-01-01' });
    const [url, init] = apiFetch.mock.calls.at(-1)!;
    expect(url).toBe(`${BASE}/policies/pol-1/supersede`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toMatchObject({ version: 'v16', effective_from: '2027-01-01' });
  });

  it('delete policy uses DELETE', async () => {
    apiFetch.mockResolvedValue(ok({ message: 'ok' }));
    await deletePolicy('pol-1');
    expect(apiFetch.mock.calls.at(-1)![0]).toBe(`${BASE}/policies/pol-1`);
    expect(apiFetch.mock.calls.at(-1)![1].method).toBe('DELETE');
  });

  it('terms are read by policy_id', async () => {
    apiFetch.mockResolvedValue(ok([]));
    await getTerms('pol-1');
    expect(apiFetch.mock.calls.at(-1)![0]).toBe(`${BASE}/terms?policy_id=pol-1`);
  });

  it('kinds send the no-rule filter and repeated is_active', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 25 } }));
    await getKinds({ ...grid, has_no_rule: true, is_active: ['active'] } as never);
    const url = String(apiFetch.mock.calls.at(-1)![0]);
    expect(url.startsWith(`${BASE}/kinds?`)).toBe(true);
    expect(url).toContain('has_no_rule=true');
    expect(url).toContain('is_active=active');
  });

  it('a kind is edited with PATCH', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'k-1' }));
    await updateKind('k-1', { is_active: false });
    const [url, init] = apiFetch.mock.calls.at(-1)!;
    expect(url).toBe(`${BASE}/kinds/k-1`);
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body)).toEqual({ is_active: false });
  });

  it('rules send the Kind filter repeated', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 25 } }));
    await getRules({ ...grid, kind_id: ['k-1', 'k-2'] } as never);
    expect(String(apiFetch.mock.calls.at(-1)![0])).toContain('kind_id=k-1&kind_id=k-2');
  });

  it('test a product posts product_id', async () => {
    apiFetch.mockResolvedValue(ok({ resolved_kind: null, deciding_rule: null }));
    await testKindRules('p-1');
    const [url, init] = apiFetch.mock.calls.at(-1)!;
    expect(url).toBe(`${BASE}/kind-rules/test`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ product_id: 'p-1' });
  });

  it('a 403 surfaces the server message', async () => {
    apiFetch.mockResolvedValue({
      ok: false, status: 403, json: async () => ({ detail: 'Admin access is required to change warranty configuration.' }),
    } as Response);
    await expect(deletePolicy('pol-1')).rejects.toThrow(/Admin access is required/);
  });
});
