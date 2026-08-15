/**
 * `warrantyConfigService` - S7b Phase 2c gate, Group 3 (the service contract).
 *
 * Pins the exact URL, HTTP method and error-throwing behaviour of every
 * function against the real `apiFetch` call it makes (the full contract is in
 * the header comment atop the source file). Every function now goes straight
 * to the backend, so a swapped verb (PATCH becoming PUT), a drifted path or a
 * dropped query parameter fails here rather than at runtime.
 *
 * `extractApiError` is mocked (not the real implementation) so the exact
 * fallback-message string each function passes is pinned independent of
 * `extractApiError`'s own parsing logic, which has its own test coverage.
 *
 * The promises are awaited directly, never swallowed: a function that starts
 * rejecting on an OK response must fail its test, not pass it quietly.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return {
    ...actual,
    extractApiError: vi.fn(async (_res: Response, fallback: string) => `EXTRACTED:${fallback}`),
  };
});

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import * as svc from './warrantyConfigService';
import type {
  WarrantyKindRuleWrite,
  WarrantyKindWrite,
  WarrantyPolicyWrite,
  WarrantyTermWrite,
} from '../types/warranty-config.types';

const mockedFetch = vi.mocked(apiFetch);
const mockedExtract = vi.mocked(extractApiError);

const BASE = '/api/v1/warranty-management';

function okJson(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

function badJson(): Response {
  return { ok: false, status: 422, json: async () => ({ detail: 'nope' }) } as Response;
}

beforeEach(() => {
  mockedFetch.mockReset();
  mockedExtract.mockClear();
});

const policyWrite: WarrantyPolicyWrite = {
  version: 'v99',
  effective_from: '2026-01-01',
  effective_to: null,
  policy_text: null,
};
const termWrite: WarrantyTermWrite = {
  kind_id: 'kind-1',
  part_name: 'Ceramic body',
  duration_months: 60,
  is_lifetime: false,
  covered_defect_type_ids: null,
  installation_included: true,
  registration_bonus_months: null,
  qualifications: null,
  exclusions: null,
};
const kindWrite: WarrantyKindWrite = {
  code: 'water_closet',
  name: 'Water Closet',
  consumer_label: null,
  consumer_icon: null,
  sort_order: 1,
  is_active: true,
};
const ruleWrite: WarrantyKindRuleWrite = {
  kind_id: 'kind-1',
  match_type: 'model_prefix',
  match_value: 'SRTMCB',
  priority: 0,
};

describe('warrantyConfigService - URL + method + error contract', () => {
  // ── Policies ──────────────────────────────────────────────────────────────

  it('listPolicies sends buildDataGridParams (page/limit/sort/dir/query) as a GET', async () => {
    mockedFetch.mockResolvedValue(okJson({ data: [], pagination: { total: 0, page: 1, limit: 20 }, empty: true }));
    await svc.listPolicies({
      pageIndex: 2,
      pageSize: 20,
      searchQuery: 'v15',
      sorting: [{ id: 'version', desc: true }],
    });
    expect(mockedFetch).toHaveBeenCalledWith(
      `${BASE}/policies?page=3&limit=20&sort=version&dir=desc&query=v15`,
    );
  });

  it('listPolicies throws the extractApiError message on a non-ok response', async () => {
    mockedFetch.mockResolvedValue(badJson());
    await expect(svc.listPolicies({ pageIndex: 0, pageSize: 20 })).rejects.toThrow(
      'EXTRACTED:Failed to load warranty policies',
    );
  });

  it('getPolicy GETs /policies/{id}', async () => {
    mockedFetch.mockResolvedValue(okJson({ id: 'pol-1' }));
    await svc.getPolicy('pol-1');
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/policies/pol-1`);
  });

  it('createPolicy POSTs to /policies with the write body (never PUT)', async () => {
    mockedFetch.mockResolvedValue(okJson({ id: 'pol-2' }));
    await svc.createPolicy(policyWrite);
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/policies`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(policyWrite),
    });
  });

  it('updatePolicy PATCHes /policies/{id}: update semantics are PATCH, never PUT', async () => {
    mockedFetch.mockResolvedValue(okJson({ id: 'pol-1' }));
    await svc.updatePolicy('pol-1', policyWrite);
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/policies/pol-1`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(policyWrite),
    });
  });

  it('deletePolicy DELETEs /policies/{id} (AC-P13: cascades terms server-side)', async () => {
    mockedFetch.mockResolvedValue(okJson({ message: 'deleted' }));
    await svc.deletePolicy('pol-1');
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/policies/pol-1`, { method: 'DELETE' });
  });

  it('supersedePolicy POSTs /policies/{id}/supersede (AC-P2a: one transaction, two rows)', async () => {
    mockedFetch.mockResolvedValue(okJson({ closed: {}, created: {} }));
    await svc.supersedePolicy('pol-1', policyWrite);
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/policies/pol-1/supersede`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(policyWrite),
    });
  });

  // ── Terms ─────────────────────────────────────────────────────────────────

  it('listTermsGroupedByKind GETs /policies/{pid}/terms?group_by=kind', async () => {
    mockedFetch.mockResolvedValue(okJson({ groups: [], total: 0 }));
    await svc.listTermsGroupedByKind('pol-1');
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/policies/pol-1/terms?group_by=kind`);
  });

  it('createTerm POSTs /policies/{pid}/terms', async () => {
    mockedFetch.mockResolvedValue(okJson({ id: 'term-1' }));
    await svc.createTerm('pol-1', termWrite);
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/policies/pol-1/terms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(termWrite),
    });
  });

  it('updateTerm PATCHes /policies/{pid}/terms/{tid}, never PUT', async () => {
    mockedFetch.mockResolvedValue(okJson({ id: 'term-1' }));
    await svc.updateTerm('pol-1', 'term-1', termWrite);
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/policies/pol-1/terms/term-1`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(termWrite),
    });
  });

  it('deleteTerm DELETEs /policies/{pid}/terms/{tid} (AC-P8a: assessments survive server-side)', async () => {
    mockedFetch.mockResolvedValue(okJson({ message: 'deleted' }));
    await svc.deleteTerm('pol-1', 'term-1');
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/policies/pol-1/terms/term-1`, {
      method: 'DELETE',
    });
  });

  it('deleteTerm throws the extractApiError message on a non-ok response', async () => {
    mockedFetch.mockResolvedValue(badJson());
    await expect(svc.deleteTerm('pol-1', 'term-1')).rejects.toThrow(
      'EXTRACTED:Failed to delete warranty term',
    );
  });

  // ── Kinds ─────────────────────────────────────────────────────────────────

  it('listKinds GETs /kinds with no query string when the search is empty', async () => {
    mockedFetch.mockResolvedValue(okJson([]));
    await svc.listKinds();
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kinds`);
  });

  it('listKinds GETs /kinds?query=... when a search string is given', async () => {
    mockedFetch.mockResolvedValue(okJson([]));
    await svc.listKinds('mirror');
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kinds?query=mirror`);
  });

  it('listKindOptions GETs /kinds/select', async () => {
    mockedFetch.mockResolvedValue(okJson([]));
    await svc.listKindOptions();
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kinds/select`);
  });

  it('createKind POSTs /kinds', async () => {
    mockedFetch.mockResolvedValue(okJson({ id: 'kind-2' }));
    await svc.createKind(kindWrite);
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kinds`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(kindWrite),
    });
  });

  it('updateKind PATCHes /kinds/{id}, never PUT', async () => {
    mockedFetch.mockResolvedValue(okJson({ id: 'kind-1' }));
    await svc.updateKind('kind-1', kindWrite);
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kinds/kind-1`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(kindWrite),
    });
  });

  it('deleteKind DELETEs /kinds/{id} (AC-P12: refused server-side while referenced)', async () => {
    mockedFetch.mockResolvedValue(okJson({ message: 'deleted' }));
    await svc.deleteKind('kind-1');
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kinds/kind-1`, { method: 'DELETE' });
  });

  it('deleteKind throws the extractApiError message on a non-ok (refused) response', async () => {
    mockedFetch.mockResolvedValue(badJson());
    await expect(svc.deleteKind('kind-1')).rejects.toThrow('EXTRACTED:Failed to delete product kind');
  });

  // ── Kind rules ────────────────────────────────────────────────────────────

  it('listKindRules GETs /kind-rules with no query when kindId is null', async () => {
    mockedFetch.mockResolvedValue(okJson([]));
    await svc.listKindRules(null);
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kind-rules`);
  });

  it('listKindRules GETs /kind-rules?kind_id=... when a kindId is given', async () => {
    mockedFetch.mockResolvedValue(okJson([]));
    await svc.listKindRules('kind-1');
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kind-rules?kind_id=kind-1`);
  });

  it('createKindRule POSTs /kind-rules', async () => {
    mockedFetch.mockResolvedValue(okJson({ id: 'rule-1' }));
    await svc.createKindRule(ruleWrite);
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kind-rules`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ruleWrite),
    });
  });

  it('updateKindRule PATCHes /kind-rules/{id}, never PUT', async () => {
    mockedFetch.mockResolvedValue(okJson({ id: 'rule-1' }));
    await svc.updateKindRule('rule-1', ruleWrite);
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kind-rules/rule-1`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ruleWrite),
    });
  });

  it('deleteKindRule DELETEs /kind-rules/{id}', async () => {
    mockedFetch.mockResolvedValue(okJson({ message: 'deleted' }));
    await svc.deleteKindRule('rule-1');
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kind-rules/rule-1`, { method: 'DELETE' });
  });

  it('testKindRules POSTs /kind-rules/test and treats a 200 response as success (a read, not a write, despite POST)', async () => {
    const response = { resolved_kind: null, deciding_rule: null, matches: [] };
    mockedFetch.mockResolvedValue(okJson(response));
    const out = await svc.testKindRules({
      product_code: 'SRTMCB6071',
      category_code: null,
      product_name: null,
      candidate_rule: null,
    });
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/kind-rules/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product_code: 'SRTMCB6071',
        category_code: null,
        product_name: null,
        candidate_rule: null,
      }),
    });
    // No thrown error on a 200 body even though the verb is POST: this is a read.
    expect(out).toEqual(response);
  });

  // ── Defect types ──────────────────────────────────────────────────────────

  it('listDefectTypes GETs /defect-types', async () => {
    mockedFetch.mockResolvedValue(okJson([]));
    await svc.listDefectTypes();
    expect(mockedFetch).toHaveBeenCalledWith(`${BASE}/defect-types`);
  });

  it('listDefectTypes throws the extractApiError message on a non-ok response', async () => {
    mockedFetch.mockResolvedValue(badJson());
    await expect(svc.listDefectTypes()).rejects.toThrow('EXTRACTED:Failed to load defect types');
  });
});
