import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  KindRuleTestResult,
  SupersedeResult,
  SupersedeValues,
  WarrantyKind,
  WarrantyKindValues,
  WarrantyPolicy,
  WarrantyPolicyValues,
  WarrantyRule,
  WarrantyRuleValues,
  WarrantyTerm,
  WarrantyTermValues,
} from '../types/warranty.types';

const BASE = '/api/v1/after-sales/warranty';

type KindsParams = DataGridApiFetchParams & { is_active?: string[]; has_no_rule?: boolean };
type RulesParams = DataGridApiFetchParams & { kind_id?: string[] };

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw new Error(await extractApiError(response, fallback));
  return response.json();
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
});

// ---- policies

export async function getPolicies(params: DataGridApiFetchParams): Promise<DataGridApiResponse<WarrantyPolicy>> {
  const qs = buildDataGridParams(params);
  return readJson(await apiFetch(`${BASE}/policies?${qs.toString()}`), 'Failed to load policies');
}

export async function getPolicy(id: string): Promise<WarrantyPolicy> {
  return readJson(await apiFetch(`${BASE}/policies/${id}`), 'Failed to load the policy');
}

export async function createPolicy(values: WarrantyPolicyValues): Promise<WarrantyPolicy> {
  return readJson(await apiFetch(`${BASE}/policies`, send('POST', values)), 'Failed to create the policy');
}

export async function updatePolicy(id: string, values: Partial<WarrantyPolicyValues>): Promise<WarrantyPolicy> {
  return readJson(await apiFetch(`${BASE}/policies/${id}`, send('PATCH', values)), 'Failed to update the policy');
}

export async function deletePolicy(id: string): Promise<void> {
  await readJson(await apiFetch(`${BASE}/policies/${id}`, send('DELETE')), 'Failed to delete the policy');
}

export async function supersedePolicy(id: string, values: SupersedeValues): Promise<SupersedeResult> {
  return readJson(
    await apiFetch(`${BASE}/policies/${id}/supersede`, send('POST', values)),
    'Failed to supersede the policy',
  );
}

// ---- terms

export async function getTerms(policyId: string): Promise<WarrantyTerm[]> {
  const qs = new URLSearchParams({ policy_id: policyId });
  return readJson(await apiFetch(`${BASE}/terms?${qs.toString()}`), 'Failed to load the terms');
}

export async function createTerm(values: WarrantyTermValues): Promise<WarrantyTerm> {
  return readJson(await apiFetch(`${BASE}/terms`, send('POST', values)), 'Failed to add the term');
}

export async function updateTerm(id: string, values: Partial<WarrantyTermValues>): Promise<WarrantyTerm> {
  return readJson(await apiFetch(`${BASE}/terms/${id}`, send('PATCH', values)), 'Failed to update the term');
}

export async function deleteTerm(id: string): Promise<void> {
  await readJson(await apiFetch(`${BASE}/terms/${id}`, send('DELETE')), 'Failed to delete the term');
}

// ---- kinds

export async function getKinds(params: KindsParams): Promise<DataGridApiResponse<WarrantyKind>> {
  const qs = buildDataGridParams(params, {
    is_active: params.is_active?.length ? params.is_active : undefined,
    has_no_rule: params.has_no_rule ? true : undefined,
  });
  return readJson(await apiFetch(`${BASE}/kinds?${qs.toString()}`), 'Failed to load kinds');
}

export async function createKind(values: WarrantyKindValues): Promise<WarrantyKind> {
  return readJson(await apiFetch(`${BASE}/kinds`, send('POST', values)), 'Failed to create the kind');
}

export async function updateKind(id: string, values: Partial<WarrantyKindValues>): Promise<WarrantyKind> {
  return readJson(await apiFetch(`${BASE}/kinds/${id}`, send('PATCH', values)), 'Failed to update the kind');
}

export async function deleteKind(id: string): Promise<void> {
  await readJson(await apiFetch(`${BASE}/kinds/${id}`, send('DELETE')), 'Failed to delete the kind');
}

// ---- kind rules

export async function getRules(params: RulesParams): Promise<DataGridApiResponse<WarrantyRule>> {
  const qs = buildDataGridParams(params, { kind_id: params.kind_id?.length ? params.kind_id : undefined });
  return readJson(await apiFetch(`${BASE}/kind-rules?${qs.toString()}`), 'Failed to load rules');
}

export async function createRule(values: WarrantyRuleValues): Promise<WarrantyRule> {
  return readJson(await apiFetch(`${BASE}/kind-rules`, send('POST', values)), 'Failed to create the rule');
}

export async function updateRule(id: string, values: Partial<WarrantyRuleValues>): Promise<WarrantyRule> {
  return readJson(await apiFetch(`${BASE}/kind-rules/${id}`, send('PATCH', values)), 'Failed to update the rule');
}

export async function deleteRule(id: string): Promise<void> {
  await readJson(await apiFetch(`${BASE}/kind-rules/${id}`, send('DELETE')), 'Failed to delete the rule');
}

export async function testKindRules(productId: string): Promise<KindRuleTestResult> {
  return readJson(
    await apiFetch(`${BASE}/kind-rules/test`, send('POST', { product_id: productId })),
    'Failed to test the product',
  );
}

export async function getDefectTypes(): Promise<{ id: string; label: string }[]> {
  return readJson(await apiFetch(`${BASE}/defect-types`), 'Failed to load defect types');
}
