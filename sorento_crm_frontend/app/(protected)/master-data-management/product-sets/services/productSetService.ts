/**
 * Product set master - feature service.
 *
 * Layering: components -> hooks (useProductSets) -> THIS service -> lib/api-client.
 *
 * PHASE 1: every function below answers from `MOCK_SETS`. No backend exists yet.
 * S1 phase 2 swaps each body for the `apiFetch` call already written beside it
 * and deletes the mock. The contract the backend must meet is stated here first,
 * so the two halves cannot drift while they are built apart.
 *
 * Backend contract (mounted under the `product` module guard):
 *   GET    /api/v1/master-data/product-sets?page&limit&sort&dir&query
 *            -> { data: ProductSet[], pagination: { total, page, limit }, empty }
 *            gated `master_data.product_sets.view`; `query` matches set_code and name.
 *   GET    /api/v1/master-data/product-sets/{id}
 *            -> ProductSetDetail, members ordered by sort_order, each carrying
 *            its own `available` and the set carrying `complete_sets` +
 *            `limiting_member_code`.        gated `master_data.product_sets.view`
 *   POST   /api/v1/master-data/product-sets          body ProductSetPayload -> ProductSetDetail
 *            409 when (company, set_code) already exists. Uniqueness is per
 *            company: Sorento and Mocha both legitimately carry the same codes.
 *            gated `master_data.product_sets.edit`
 *   PUT    /api/v1/master-data/product-sets/{id}     body ProductSetPayload -> ProductSetDetail
 *            `members` omitted leaves membership alone; `members: []` empties it.
 *            gated `master_data.product_sets.edit`
 *   DELETE /api/v1/master-data/product-sets/{id}     -> 204
 *            Hard delete. Members go with it; no product is touched.
 *            gated `master_data.product_sets.delete`
 *
 * A set is NOT orderable and is never a `products` row, so there is deliberately
 * no stock write, no costing and no order endpoint here.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  ProductSet,
  ProductSetDetail,
  ProductSetPayload,
} from '../types/productSet.types';

const BASE = '/api/v1/master-data/product-sets';

/** PHASE 1 ONLY. Deleted when the routes land. */
const USE_MOCK = true;

/**
 * The 8608 family, as it actually reads in the catalogue: the whole set's list
 * price is parked on the pedestal and the cistern is 0.00, which is why the
 * price basis is a per-member tick rather than a sum over everything.
 */
const MOCK_SETS: ProductSetDetail[] = [
  {
    id: 'mock-8608-rl',
    set_code: 'SRTWC8608-RL',
    name: 'Washdown with rimless flushing, S-trap',
    is_active: true,
    company_name: 'Sorento',
    member_count: 3,
    complete_sets: 0,
    limiting_member_code: 'SRTWC8608-SC',
    price: {
      computed: 1180,
      override: null,
      resolved: 1180,
      is_overridden: false,
      reason: null,
    },
    created_at: '2026-08-23T02:10:00',
    updated_at: '2026-08-23T02:10:00',
    members: [
      {
        id: 'm1',
        product_code: 'SRTWCX8608-RL',
        product_name: 'SRTWCX8608-RL',
        description: 'SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM)',
        list_price: 1180,
        is_discontinued: false,
        quantity: 1,
        contributes_to_price: true,
        sort_order: 0,
        available: 40,
      },
      {
        id: 'm2',
        product_code: 'SRTWCY8608',
        product_name: 'SRTWCY8608',
        description: 'SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP)',
        list_price: 0,
        is_discontinued: false,
        quantity: 1,
        contributes_to_price: false,
        sort_order: 1,
        available: 12,
      },
      {
        id: 'm3',
        product_code: 'SRTWC8608-SC',
        product_name: 'SRTWC8608-SC',
        description: 'SORENTO SRTWC8608-SC SEAT COVER ONLY',
        list_price: 85,
        is_discontinued: false,
        quantity: 1,
        contributes_to_price: false,
        sort_order: 2,
        available: 0,
      },
    ],
  },
  {
    id: 'mock-8608-p-rl',
    set_code: 'SRTWC8608-P-RL',
    name: 'Washdown with rimless flushing, P-trap',
    is_active: true,
    company_name: 'Sorento',
    member_count: 3,
    complete_sets: 9,
    limiting_member_code: 'SRTWCY8608',
    price: {
      computed: 1180,
      override: 1150,
      resolved: 1150,
      is_overridden: true,
      reason: null,
      override_set_by_name: 'Jayson Teh',
      override_set_at: '2026-08-23T03:40:00',
    },
    created_at: '2026-08-23T02:12:00',
    updated_at: '2026-08-23T03:40:00',
    members: [
      {
        id: 'm4',
        product_code: 'SRTWCX8608-P-RL',
        product_name: 'SRTWCX8608-P-RL',
        description: 'SORENTO CLOSE COUPLED PEDESTAL (P-TRAP 180MM)',
        list_price: 1180,
        is_discontinued: false,
        quantity: 1,
        contributes_to_price: true,
        sort_order: 0,
        available: 22,
      },
      {
        id: 'm5',
        product_code: 'SRTWCY8608',
        product_name: 'SRTWCY8608',
        description: 'SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP)',
        list_price: 0,
        is_discontinued: false,
        quantity: 1,
        contributes_to_price: false,
        sort_order: 1,
        available: 9,
      },
      {
        id: 'm6',
        product_code: 'SRTWC8608-SC-UF',
        product_name: 'SRTWC8608-SC-UF',
        description: 'SORENTO SRTWC8608-SC-UF SEAT COVER ONLY',
        list_price: 0,
        is_discontinued: true,
        quantity: 1,
        contributes_to_price: false,
        sort_order: 2,
        available: 15,
      },
    ],
  },
  {
    id: 'mock-7605-eco',
    set_code: 'CWC7605-ECO',
    name: 'Cabana close-coupled, eco',
    is_active: true,
    company_name: 'Sorento',
    member_count: 0,
    complete_sets: null,
    limiting_member_code: null,
    // A set mid-authoring. The price is ABSENT, not 0.00.
    price: {
      computed: null,
      override: null,
      resolved: null,
      is_overridden: false,
      reason: 'no_members',
    },
    created_at: '2026-08-23T04:02:00',
    updated_at: '2026-08-23T04:02:00',
    members: [],
  },
];

function mockDelay<T>(value: T, ms = 320): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

function toListRow(set: ProductSetDetail): ProductSet {
  const { members: _members, ...row } = set;
  return row;
}

export async function getProductSets(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<ProductSet>> {
  if (USE_MOCK) {
    const query = (params.searchQuery ?? '').trim().toLowerCase();
    const matched = MOCK_SETS.filter(
      (s) =>
        !query ||
        s.set_code.toLowerCase().includes(query) ||
        s.name.toLowerCase().includes(query),
    ).map(toListRow);
    return mockDelay({
      data: matched,
      pagination: { total: matched.length, page: 1, limit: params.pageSize },
      empty: MOCK_SETS.length === 0,
    } as DataGridApiResponse<ProductSet>);
  }
  const search = buildDataGridParams(params);
  const response = await apiFetch(`${BASE}?${search.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load product sets'));
  }
  return response.json();
}

export async function getProductSet(id: string): Promise<ProductSetDetail> {
  if (USE_MOCK) {
    const found = MOCK_SETS.find((s) => s.id === id);
    if (!found) throw new Error('Product set not found');
    return mockDelay(structuredClone(found));
  }
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load product set'));
  }
  return response.json();
}

export async function createProductSet(data: ProductSetPayload): Promise<ProductSetDetail> {
  if (USE_MOCK) {
    if (MOCK_SETS.some((s) => s.set_code.toLowerCase() === data.set_code.trim().toLowerCase())) {
      throw new Error(`A set with the code ${data.set_code} already exists for this company`);
    }
    const created: ProductSetDetail = {
      ...structuredClone(MOCK_SETS[2]),
      id: `mock-${Date.now()}`,
      set_code: data.set_code,
      name: data.name,
    };
    MOCK_SETS.push(created);
    return mockDelay(created);
  }
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create product set'));
  }
  return response.json();
}

export async function updateProductSet(
  id: string,
  data: ProductSetPayload,
): Promise<ProductSetDetail> {
  if (USE_MOCK) {
    const index = MOCK_SETS.findIndex((s) => s.id === id);
    if (index < 0) throw new Error('Product set not found');
    const next = { ...MOCK_SETS[index], set_code: data.set_code, name: data.name };
    if (data.list_price_override !== undefined) {
      next.price = {
        ...next.price,
        override: data.list_price_override,
        resolved: data.list_price_override ?? next.price.computed,
        is_overridden: data.list_price_override !== null,
      };
    }
    MOCK_SETS[index] = next;
    return mockDelay(structuredClone(next));
  }
  const response = await apiFetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save product set'));
  }
  return response.json();
}

export async function deleteProductSet(id: string): Promise<void> {
  if (USE_MOCK) {
    const index = MOCK_SETS.findIndex((s) => s.id === id);
    if (index >= 0) MOCK_SETS.splice(index, 1);
    await mockDelay(null);
    return;
  }
  const response = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete product set'));
  }
}
