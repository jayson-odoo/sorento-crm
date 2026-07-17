/**
 * SCM Policy service — Phase-2 contract tests (USE_POLICY_MOCKS = false).
 *
 * Pins the request shaping every AC in group I (AC-STD-1/2) and the endpoint
 * contract documented at the top of scmPolicyService.ts:
 *   - list uses buildDataGridParams (page/limit/sort/dir/query)         AC-LIST-3
 *   - create/update/delete/classification/supplier-scoring/resolve hit
 *     the right method + path + body (AC-EDIT / AC-CFG-2 / AC-SUP-2 / AC-PREV-1)
 *   - extractApiError is used on a non-ok response (error branch)       AC-STD-2
 *   - scope-option mappers hold the resolver key as the hidden value:
 *       product → products.id, class → category_code, warehouse → code  AC-NAV-4 / Risk #2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  USE_POLICY_MOCKS,
  listReorderPolicies,
  createReorderPolicy,
  updateReorderPolicy,
  deleteReorderPolicy,
  getClassification,
  saveClassification,
  getSupplierScoring,
  saveSupplierScoring,
  resolvePolicy,
  getProductScopeOptions,
  getClassScopeOptions,
  getWarehouseScopeOptions,
} from './scmPolicyService';
import type { ReorderPolicyWrite } from '../types/policy.types';

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}
function fail(detail: string, status = 422) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}

/** Parse the URL passed to apiFetch on its last call (base is irrelevant). */
function lastUrl(): URL {
  const calls = apiFetch.mock.calls;
  return new URL(String(calls[calls.length - 1][0]), 'http://x');
}
function lastInit(): RequestInit {
  const calls = apiFetch.mock.calls;
  return (calls[calls.length - 1][1] ?? {}) as RequestInit;
}

const WRITE: ReorderPolicyWrite = {
  scope_type: 'product_class',
  scope_ref: 'BRK',
  policy_type: 'reorder_point',
  service_level: null,
  safety_stock_method: 'fixed_days',
  safety_days: 7,
  review_period_days: null,
  forecast_window_days: 90,
  baseline_source: null,
  spike_handling: null,
  buy_scope: null,
  dead_stock_days: 180,
  overstock_days: 120,
  min_override: null,
  max_override: null,
  priority: 10,
  is_active: true,
  supplier_selection: 'best_score',
  lead_time_default_days: 14,
};

beforeEach(() => apiFetch.mockReset());

describe('scmPolicyService — Phase-2 (live backend) is active', () => {
  it('USE_POLICY_MOCKS is false so real apiFetch branches run', () => {
    expect(USE_POLICY_MOCKS).toBe(false);
  });
});

describe('listReorderPolicies — buildDataGridParams shaping (AC-LIST-3)', () => {
  it('sends page (1-based), limit, sort, dir and query', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], total: 0 }));
    await listReorderPolicies({
      pageIndex: 2,
      pageSize: 25,
      searchQuery: 'brake',
      sorting: [{ id: 'priority', desc: true }],
    });
    const u = lastUrl();
    expect(u.pathname).toBe('/api/v1/scm/policies');
    expect(u.searchParams.get('page')).toBe('3'); // 0-based → 1-based
    expect(u.searchParams.get('limit')).toBe('25');
    expect(u.searchParams.get('sort')).toBe('priority');
    expect(u.searchParams.get('dir')).toBe('desc');
    expect(u.searchParams.get('query')).toBe('brake');
  });

  it('omits sort/dir/query when unsorted and unsearched', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], total: 0 }));
    await listReorderPolicies({ pageIndex: 0, pageSize: 50 });
    const u = lastUrl();
    expect(u.searchParams.get('page')).toBe('1');
    expect(u.searchParams.get('sort')).toBeNull();
    expect(u.searchParams.get('dir')).toBeNull();
    expect(u.searchParams.get('query')).toBeNull();
  });

  it('throws the extracted message on a non-ok response (extractApiError)', async () => {
    apiFetch.mockResolvedValue(fail('Nope', 403));
    await expect(listReorderPolicies({ pageIndex: 0, pageSize: 50 })).rejects.toThrow('Nope');
  });
});

describe('createReorderPolicy (AC-EDIT-5)', () => {
  it('POSTs the write body as JSON to the collection path', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'pol-1', scope_label: 'Braking', ...WRITE }));
    const row = await createReorderPolicy(WRITE);
    const u = lastUrl();
    const init = lastInit();
    expect(u.pathname).toBe('/api/v1/scm/policies');
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body as string)).toEqual(WRITE);
    expect(row.id).toBe('pol-1');
  });

  it('surfaces the extracted 422 message on failure', async () => {
    apiFetch.mockResolvedValue(fail('A policy already exists for this scope'));
    await expect(createReorderPolicy(WRITE)).rejects.toThrow('A policy already exists for this scope');
  });
});

describe('updateReorderPolicy', () => {
  it('PUTs to /policies/{id} with the write body', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'pol-9', scope_label: 'Braking', ...WRITE }));
    await updateReorderPolicy('pol-9', WRITE);
    const u = lastUrl();
    const init = lastInit();
    expect(u.pathname).toBe('/api/v1/scm/policies/pol-9');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual(WRITE);
  });

  it('throws the extracted message on failure', async () => {
    apiFetch.mockResolvedValue(fail('bad', 422));
    await expect(updateReorderPolicy('pol-9', WRITE)).rejects.toThrow('bad');
  });
});

describe('deleteReorderPolicy (AC-DEL-1/2)', () => {
  it('DELETEs /policies/{id}', async () => {
    apiFetch.mockResolvedValue({ ok: true } as unknown as Response);
    await deleteReorderPolicy('pol-3');
    const u = lastUrl();
    expect(u.pathname).toBe('/api/v1/scm/policies/pol-3');
    expect(lastInit().method).toBe('DELETE');
  });

  it('surfaces the global-not-deletable 422 message', async () => {
    apiFetch.mockResolvedValue(fail('The global default policy cannot be deleted'));
    await expect(deleteReorderPolicy('pol-global')).rejects.toThrow(
      'The global default policy cannot be deleted',
    );
  });
});

describe('classification thresholds (AC-CFG-2)', () => {
  it('GETs /policies/classification', async () => {
    apiFetch.mockResolvedValue(ok({ abc_a_pct: 0.8, abc_b_pct: 0.15, xyz_x_max: 0.5, xyz_y_max: 1, exists: true }));
    const p = await getClassification();
    expect(lastUrl().pathname).toBe('/api/v1/scm/policies/classification');
    expect(p.abc_a_pct).toBe(0.8);
  });

  it('PUTs /policies/classification with the write body (upsert)', async () => {
    apiFetch.mockResolvedValue(ok({ abc_a_pct: 0.7, abc_b_pct: 0.2, xyz_x_max: 0.4, xyz_y_max: 0.9, exists: true }));
    const body = { abc_a_pct: 0.7, abc_b_pct: 0.2, xyz_x_max: 0.4, xyz_y_max: 0.9 };
    await saveClassification(body);
    const u = lastUrl();
    const init = lastInit();
    expect(u.pathname).toBe('/api/v1/scm/policies/classification');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual(body);
  });

  it('throws the extracted message on failure', async () => {
    apiFetch.mockResolvedValue(fail('A + B must be below 100%'));
    await expect(saveClassification({ abc_a_pct: 0.9, abc_b_pct: 0.9, xyz_x_max: 1, xyz_y_max: 1 })).rejects.toThrow(
      'A + B must be below 100%',
    );
  });
});

describe('supplier scoring (AC-SUP-2)', () => {
  it('GETs /policies/supplier-scoring', async () => {
    apiFetch.mockResolvedValue(ok({ delivery_weight: 0.6, quality_weight: 0.4, grace_days: 2, min_sample_size: 5, exists: true }));
    const p = await getSupplierScoring();
    expect(lastUrl().pathname).toBe('/api/v1/scm/policies/supplier-scoring');
    expect(p.delivery_weight).toBe(0.6);
  });

  it('PUTs /policies/supplier-scoring with the write body (upsert)', async () => {
    apiFetch.mockResolvedValue(ok({ delivery_weight: 0.5, quality_weight: 0.5, grace_days: 1, min_sample_size: 3, exists: true }));
    const body = { delivery_weight: 0.5, quality_weight: 0.5, grace_days: 1, min_sample_size: 3 };
    await saveSupplierScoring(body);
    const u = lastUrl();
    const init = lastInit();
    expect(u.pathname).toBe('/api/v1/scm/policies/supplier-scoring');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual(body);
  });

  it('throws the extracted message on failure', async () => {
    apiFetch.mockResolvedValue(fail('weights must add up to 1.0'));
    await expect(
      saveSupplierScoring({ delivery_weight: 0.6, quality_weight: 0.6, grace_days: 0, min_sample_size: 1 }),
    ).rejects.toThrow('weights must add up to 1.0');
  });
});

describe('resolvePolicy (AC-PREV-1/4)', () => {
  it('GETs /policies/resolve with product_id and warehouse_id', async () => {
    apiFetch.mockResolvedValue(ok({ product: { product_code: 'BRK-450', product_name: 'x' }, warehouse: null, abc_xyz_cell: null, product_class: null, winner: null, chain: [] }));
    await resolvePolicy('prd-uuid-1', 'WH-KL');
    const u = lastUrl();
    expect(u.pathname).toBe('/api/v1/scm/policies/resolve');
    expect(u.searchParams.get('product_id')).toBe('prd-uuid-1');
    expect(u.searchParams.get('warehouse_id')).toBe('WH-KL');
  });

  it('omits warehouse_id when no warehouse is chosen', async () => {
    apiFetch.mockResolvedValue(ok({ product: { product_code: 'x', product_name: 'y' }, warehouse: null, abc_xyz_cell: null, product_class: null, winner: null, chain: [] }));
    await resolvePolicy('prd-uuid-2', null);
    const u = lastUrl();
    expect(u.searchParams.get('product_id')).toBe('prd-uuid-2');
    expect(u.searchParams.get('warehouse_id')).toBeNull();
  });

  it('throws the extracted message on failure', async () => {
    apiFetch.mockResolvedValue(fail('Product not found', 404));
    await expect(resolvePolicy('nope', null)).rejects.toThrow('Product not found');
  });
});

describe('scope-option mappers hold the resolver key as the hidden value (AC-NAV-4 / Risk #2)', () => {
  it('product options: value = products.id, label = code · name', async () => {
    apiFetch.mockResolvedValue(
      ok({ data: [{ id: 'prd-uuid-1', product_code: 'BRK-450', product_name: 'Brake Disc' }] }),
    );
    const opts = await getProductScopeOptions();
    expect(lastUrl().pathname).toBe('/api/v1/master-data/products/select');
    expect(opts[0].value).toBe('prd-uuid-1'); // UUID hidden as the value, never displayed
    expect(opts[0].label).toBe('BRK-450 · Brake Disc');
  });

  it('class options: value = category_code', async () => {
    apiFetch.mockResolvedValue(ok([{ category_code: 'BRK', category_name: 'Braking' }]));
    const opts = await getClassScopeOptions();
    expect(lastUrl().pathname).toBe('/api/v1/master-data/product-categories/select');
    expect(opts[0].value).toBe('BRK');
    expect(opts[0].label).toBe('Braking');
  });

  it('warehouse options: value = warehouse_code', async () => {
    apiFetch.mockResolvedValue(ok({ data: [{ warehouse_code: 'WH-KL', warehouse_name: 'Kuala Lumpur DC' }] }));
    const opts = await getWarehouseScopeOptions();
    expect(lastUrl().pathname).toBe('/api/v1/scm/dashboard/warehouses');
    expect(opts[0].value).toBe('WH-KL');
    expect(opts[0].label).toBe('Kuala Lumpur DC');
  });

  it('option sources throw the extracted message on failure', async () => {
    apiFetch.mockResolvedValue(fail('boom', 500));
    await expect(getProductScopeOptions()).rejects.toThrow();
  });
});
