/**
 * ============================================================================
 * SCM Policy Configuration — feature service
 * ============================================================================
 * Layering: hooks (usePolicies*) → THIS service → lib/api-client → backend.
 * No component fetches directly (AC-STD-1).
 *
 * ── PHASE-1 / PHASE-2 SWAP ──────────────────────────────────────────────────
 * `USE_POLICY_MOCKS` is the single flag that toggles this whole feature between
 * the deterministic prototype store (`lib/scmPolicyMock.ts`) and the live
 * backend. Phase 1 = true (no backend). Phase 2 flips it to false; every mock
 * branch below already has its real `apiFetch` counterpart wired to the
 * contract, so the swap is one line + deleting the mock import.
 *
 * ── PHASE-2 BACKEND CONTRACT (mounted under require_module_enabled("scm"),
 *    read + write both gated `scm.policy.manage`; AC-CFG-3) ───────────────────
 *
 *  GET    /api/v1/scm/policies?page&limit&sort&dir&query
 *    → { data: ReorderPolicyRow[], total: number }
 *      ReorderPolicyRow.scope_label is human-readable (no UUID). scope_ref keys:
 *        sku → products.id · product_class → category_code · abc_xyz_cell → "A-X"
 *        · global → null.
 *  POST   /api/v1/scm/policies              body ReorderPolicyWrite  → ReorderPolicyRow (201)
 *  PUT    /api/v1/scm/policies/{id}         body ReorderPolicyWrite  → ReorderPolicyRow
 *  DELETE /api/v1/scm/policies/{id}         → 204   (422 if scope_type='global', AC-DEL-2)
 *    ReorderPolicyWrite = ReorderPolicyRow minus id + scope_label; scope_ref
 *    required unless global; for sku scope_ref = products.id (picker hidden value).
 *
 *  GET    /api/v1/scm/policies/classification    → AbcXyzPolicy   ({exists:false}+defaults if none)
 *  PUT    /api/v1/scm/policies/classification     body AbcXyzWrite → AbcXyzPolicy   (upsert 1 row)
 *
 *  GET    /api/v1/scm/policies/supplier-scoring  → SupplierScoringPolicy  (defaults if none)
 *  PUT    /api/v1/scm/policies/supplier-scoring   body SupplierScoringWrite → SupplierScoringPolicy
 *
 *  GET    /api/v1/scm/policies/resolve?product_id=&warehouse_id=  → ResolutionResult
 *    Produced by calling the SAME `reorder_engine.resolve_policy_for_sku` the
 *    reorder run uses — never a reimplementation (AC-PREV-2). `chain` teaches the
 *    precedence: which scopes matched, which won, and why.
 *
 * Server-authoritative validation (mirrored client-side for UX) — AC-VAL-*,
 * AC-CFG-2, AC-SUP-2 — returns 422 via the global AppException handler.
 * ============================================================================
 */
import type { SortingState } from '@tanstack/react-table';
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  AbcXyzPolicy,
  AbcXyzWrite,
  ReorderPolicyRow,
  ReorderPolicyWrite,
  ResolutionResult,
  SupplierScoringPolicy,
  SupplierScoringWrite,
} from '../types/policy.types';
import type { Option } from '../../services/scmOptionsService';
import {
  mockCategoryOptions,
  mockCreateReorderPolicy,
  mockDeleteReorderPolicy,
  mockGetClassification,
  mockGetSupplierScoring,
  mockListReorderPolicies,
  mockProductOptions,
  mockResolve,
  mockSaveClassification,
  mockSaveSupplierScoring,
  mockUpdateReorderPolicy,
  mockWarehouseOptions,
} from '../lib/scmPolicyMock';

/** Phase-1 flag — true = deterministic mock store, false = live backend. */
export const USE_POLICY_MOCKS = false;

export interface PolicyListQuery {
  pageIndex: number;
  pageSize: number;
  searchQuery?: string;
  sorting?: SortingState;
}

export interface ReorderPolicyPage {
  data: ReorderPolicyRow[];
  total: number;
}

const BASE = '/api/v1/scm/policies';

// ── Reorder policies ────────────────────────────────────────────────────────

export async function listReorderPolicies(q: PolicyListQuery): Promise<ReorderPolicyPage> {
  if (USE_POLICY_MOCKS) {
    return { data: mockListReorderPolicies(), total: mockListReorderPolicies().length };
  }
  const params = buildDataGridParams({
    pageIndex: q.pageIndex,
    pageSize: q.pageSize,
    sorting: q.sorting ?? [],
    searchQuery: q.searchQuery ?? '',
  });
  const res = await apiFetch(`${BASE}?${params}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load reorder policies'));
  return (await res.json()) as ReorderPolicyPage;
}

export async function createReorderPolicy(body: ReorderPolicyWrite): Promise<ReorderPolicyRow> {
  if (USE_POLICY_MOCKS) return mockCreateReorderPolicy(body);
  const res = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to create policy'));
  return (await res.json()) as ReorderPolicyRow;
}

export async function updateReorderPolicy(
  id: string,
  body: ReorderPolicyWrite,
): Promise<ReorderPolicyRow> {
  if (USE_POLICY_MOCKS) return mockUpdateReorderPolicy(id, body);
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update policy'));
  return (await res.json()) as ReorderPolicyRow;
}

export async function deleteReorderPolicy(id: string): Promise<void> {
  if (USE_POLICY_MOCKS) {
    mockDeleteReorderPolicy(id);
    return;
  }
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete policy'));
}

// ── Classification thresholds (single global row) ───────────────────────────

export async function getClassification(): Promise<AbcXyzPolicy> {
  if (USE_POLICY_MOCKS) return mockGetClassification();
  const res = await apiFetch(`${BASE}/classification`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load classification thresholds'));
  return (await res.json()) as AbcXyzPolicy;
}

export async function saveClassification(body: AbcXyzWrite): Promise<AbcXyzPolicy> {
  if (USE_POLICY_MOCKS) return mockSaveClassification(body);
  const res = await apiFetch(`${BASE}/classification`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save classification thresholds'));
  return (await res.json()) as AbcXyzPolicy;
}

// ── Supplier scoring (single global row) ────────────────────────────────────

export async function getSupplierScoring(): Promise<SupplierScoringPolicy> {
  if (USE_POLICY_MOCKS) return mockGetSupplierScoring();
  const res = await apiFetch(`${BASE}/supplier-scoring`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load supplier scoring'));
  return (await res.json()) as SupplierScoringPolicy;
}

export async function saveSupplierScoring(
  body: SupplierScoringWrite,
): Promise<SupplierScoringPolicy> {
  if (USE_POLICY_MOCKS) return mockSaveSupplierScoring(body);
  const res = await apiFetch(`${BASE}/supplier-scoring`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save supplier scoring'));
  return (await res.json()) as SupplierScoringPolicy;
}

// ── Resolution preview ──────────────────────────────────────────────────────

export async function resolvePolicy(
  productId: string,
  warehouseCode: string | null,
): Promise<ResolutionResult> {
  if (USE_POLICY_MOCKS) return mockResolve(productId, warehouseCode);
  const params = new URLSearchParams({ product_id: productId });
  if (warehouseCode) params.set('warehouse_id', warehouseCode);
  const res = await apiFetch(`${BASE}/resolve?${params.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to resolve policy'));
  return (await res.json()) as ResolutionResult;
}

// ── Scope-target option sources (pickers) ───────────────────────────────────
// In Phase 2 these swap to `scmOptionsService` variants keyed by resolver id:
//   products → value = products.id (add getProductOptionsById); label unchanged.
//   classes  → value = category_code (needs a category_code option source).

export async function getProductScopeOptions(): Promise<Option[]> {
  if (USE_POLICY_MOCKS) return mockProductOptions();
  const res = await apiFetch('/api/v1/master-data/products/select');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load products'));
  const body = (await res.json()) as {
    data: { id: string; product_code: string; product_name: string }[];
  };
  return body.data.map((p) => ({ value: p.id, label: `${p.product_code} · ${p.product_name}` }));
}

export async function getClassScopeOptions(): Promise<Option[]> {
  if (USE_POLICY_MOCKS) return mockCategoryOptions();
  const res = await apiFetch('/api/v1/master-data/product-categories/select');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load product classes'));
  const rows = (await res.json()) as { category_code: string; category_name: string }[];
  return rows.map((c) => ({ value: c.category_code, label: c.category_name, description: c.category_code }));
}

export async function getWarehouseScopeOptions(): Promise<Option[]> {
  if (USE_POLICY_MOCKS) return mockWarehouseOptions();
  const res = await apiFetch('/api/v1/scm/dashboard/warehouses');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load warehouses'));
  const body = (await res.json()) as {
    data: { warehouse_code: string; warehouse_name: string }[];
  };
  return body.data.map((w) => ({ value: w.warehouse_code, label: w.warehouse_name }));
}
