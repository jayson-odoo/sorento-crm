/**
 * ============================================================================
 * Warranty configuration (S7b) - feature service
 * ============================================================================
 * Layering: UI -> hooks (`useWarrantyConfig`) -> THIS service -> lib/api-client
 * -> FastAPI. No component fetches directly.
 *
 * ── BACKEND CONTRACT ────────────────────────────────────────────────────────
 * Mounted in `app/api/v1/__init__.py` under
 * `Depends(require_module_enabled_with_api_key("warranty"))`, prefix
 * `/warranty-management`. Reads take `require_permission_with_api_key`, writes
 * take `require_permission`. Slugs: `warranty.policies.*` (policies AND terms)
 * and `warranty.kinds.*` (kinds AND kind rules) - AC-P11.
 *
 * Status codes (AC-P15): POST 201 with the row, PATCH 200 with the row, DELETE
 * 200 (NOT 204) - `complaints/complaint_root_causes.py` is the precedent. Update
 * semantics are PATCH, never PUT: every `XUpdate` schema here is all-Optional.
 * ONE exception to "POST 201": `POST /kind-rules/test` answers **200**. It is a
 * read wearing a POST (the payload is the question), and it creates nothing -
 * treating a 201 as its success code would be asserting a row that never exists.
 *
 * Envelope (AC-P14): policies are `ListResponse[T]` =
 * `{data, pagination:{total,page,limit}, empty}`, which is the FE's own
 * `DataGridApiResponse<T>`. Kinds, kinds-select, kind-rules and defect-types are
 * BARE ARRAYS.
 *
 *  GET    /api/v1/warranty-management/policies?page&limit&sort&dir&query
 *           -> ListResponse[PolicyResponse]
 *  POST   /api/v1/warranty-management/policies                PolicyCreate -> PolicyResponse (201)
 *  GET    /api/v1/warranty-management/policies/{id}           -> PolicyResponse
 *  PATCH  /api/v1/warranty-management/policies/{id}           PolicyUpdate -> PolicyResponse (200);
 *                                                             overlap-guarded (AC-P22)
 *  DELETE /api/v1/warranty-management/policies/{id}           200, hard, cascades terms (AC-P13)
 *  POST   /api/v1/warranty-management/policies/{id}/supersede PolicyCreate
 *           -> { closed: PolicyResponse, created: PolicyResponse }   (AC-P2a, P21, ONE transaction)
 *
 *  GET    /api/v1/warranty-management/policies/{pid}/terms?group_by=kind
 *           -> { groups: [{ kind: {id,code,name}, terms: TermResponse[] }], total }
 *  POST   /api/v1/warranty-management/policies/{pid}/terms          TermCreate -> TermResponse (201)
 *  PATCH  /api/v1/warranty-management/policies/{pid}/terms/{tid}    TermUpdate -> TermResponse (200)
 *  DELETE /api/v1/warranty-management/policies/{pid}/terms/{tid}    200; assessments survive (AC-P8a)
 *
 *  GET    /api/v1/warranty-management/kinds?query                   -> KindResponse[]
 *  POST   /api/v1/warranty-management/kinds                         KindCreate -> KindResponse (201)
 *  PATCH  /api/v1/warranty-management/kinds/{id}                    KindUpdate -> KindResponse (200)
 *  DELETE /api/v1/warranty-management/kinds/{id}                    200, or refused while referenced (AC-P12)
 *  GET    /api/v1/warranty-management/kinds/select                  -> {id, code, name}[]
 *
 *  GET    /api/v1/warranty-management/kind-rules?kind_id            -> RuleResponse[]
 *  POST   /api/v1/warranty-management/kind-rules                    RuleCreate -> RuleResponse (201)
 *  PATCH  /api/v1/warranty-management/kind-rules/{id}               RuleUpdate -> RuleResponse (200)
 *  DELETE /api/v1/warranty-management/kind-rules/{id}               200
 *  POST   /api/v1/warranty-management/kind-rules/test               -> TestResponse, 200 (AC-P6, P6b, P6c)
 *
 *  GET    /api/v1/warranty-management/defect-types                  -> {id, label}[] (AC-P18)
 *
 * ── RESPONSE FIELDS THE SCREENS CANNOT WORK WITHOUT ─────────────────────────
 *  · PolicyResponse.term_count          - AC-P16, on the LIST row: the delete is
 *      offered from the grid, so a detail-only count cannot reach the dialog
 *  · TermResponse.assessment_count      - AC-P16, same reason, for AC-P8a
 *  · KindResponse.has_no_rules / has_no_terms - AC-P17, computed server-side
 *  · GET /defect-types                  - AC-P18, load-bearing: the existing
 *      `GET /api/v1/lookup/{set_key}/options` returns `value` + `label` and
 *      never `lookup_options.id`, which is what the uuid[] column stores
 *  · PolicyResponse.source_attachment_name - "no UUIDs in the UI"; the id is never rendered
 *  · TermResponse.kind_code / kind_name, TermResponse.covered_defect_type_labels,
 *      RuleResponse.kind_code / kind_name - ditto
 *  · The `?group_by=kind` response envelope - the plan names the parameter but
 *      not the shape; pinned here as `{groups: [{kind, terms}], total}`
 *  · `deciding_rule.id` is NULLABLE - an unsaved candidate rule (AC-P6b) has no id.
 *
 * ── THE ERROR ENVELOPE ──────────────────────────────────────────────────────
 * `AppException` serializes to a TOP-LEVEL `{message, detail, code}` (see
 * `app/main.py`'s `app_exception_handler`, which returns `exc.detail` as the
 * whole body). So `body.detail` is the OPTIONAL second-line elaboration and is
 * `null` for every warranty refusal below - the sentence an admin reads is
 * `body.message`. `extractApiError` recovers it through its `error.message`
 * branch, after the string/array `detail` branches fall through. Never reach
 * for `body.detail` here; it is not where the message lives.
 *
 * ── ERROR MESSAGES THE SCREENS RELY ON (quoted from warranty_config_service.py) ──
 *  · Policy overlap (AC-P2, AC-P2b) - names the other version AND its range:
 *      "Effective range overlaps policy v15 (2000-01-01 onwards). A complaint is
 *       judged against the version in force on its purchase date, so two
 *       candidates make that answer arbitrary."
 *    When the conflicting policy STARTS LATER (the mis-dated-supersede shape),
 *    one more sentence is appended - and it says DELETE THE SUCCESSOR, not
 *    "supersede that version instead", because AC-P26 ruled recovery is two
 *    supported steps (delete the successor, then reopen the incumbent) and there
 *    is no undo endpoint:
 *      " Delete policy v16 first, or change the dates."
 *  · Kind delete refusal (AC-P12) - names BOTH counts, with `(s)` plurals:
 *      "Mirror Cabinet is still referenced by 3 term(s) and 1 rule(s). Remove
 *       those first - deleting this kind would take the terms with it."
 *    `KindsTab` pre-empts this refusal client-side from the row's
 *    `has_no_terms` / `has_no_rules` flags and states the same two counts
 *    (`term_count` / `rule_count`) itself, so the server sentence is the
 *    BACKSTOP for a stale grid, not the primary path.
 * ============================================================================
 */
import type { SortingState } from '@tanstack/react-table';
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  DefectTypeOption,
  KindRuleTestRequest,
  KindRuleTestResponse,
  SupersedeResult,
  WarrantyKindRef,
  WarrantyKindRow,
  WarrantyKindRuleRow,
  WarrantyKindRuleUpdate,
  WarrantyKindRuleWrite,
  WarrantyKindWrite,
  WarrantyPolicyPage,
  WarrantyPolicyRow,
  WarrantyPolicyWrite,
  WarrantyTermRow,
  WarrantyTermWrite,
  WarrantyTermsGrouped,
} from '../types/warranty-config.types';

const BASE = '/api/v1/warranty-management';

export interface PolicyListQuery {
  pageIndex: number;
  pageSize: number;
  searchQuery?: string;
  sorting?: SortingState;
}

// ── Policies ────────────────────────────────────────────────────────────────

export async function listPolicies(q: PolicyListQuery): Promise<WarrantyPolicyPage> {
  const params = buildDataGridParams({
    pageIndex: q.pageIndex,
    pageSize: q.pageSize,
    sorting: q.sorting ?? [],
    searchQuery: q.searchQuery ?? '',
  });
  const res = await apiFetch(`${BASE}/policies?${params}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load warranty policies'));
  return (await res.json()) as WarrantyPolicyPage;
}

export async function getPolicy(id: string): Promise<WarrantyPolicyRow> {
  const res = await apiFetch(`${BASE}/policies/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load warranty policy'));
  return (await res.json()) as WarrantyPolicyRow;
}

export async function createPolicy(body: WarrantyPolicyWrite): Promise<WarrantyPolicyRow> {
  const res = await apiFetch(`${BASE}/policies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to create warranty policy'));
  return (await res.json()) as WarrantyPolicyRow;
}

export async function updatePolicy(
  id: string,
  body: WarrantyPolicyWrite,
): Promise<WarrantyPolicyRow> {
  const res = await apiFetch(`${BASE}/policies/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update warranty policy'));
  return (await res.json()) as WarrantyPolicyRow;
}

export async function deletePolicy(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/policies/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete warranty policy'));
}

export async function supersedePolicy(
  id: string,
  body: WarrantyPolicyWrite,
): Promise<SupersedeResult> {
  const res = await apiFetch(`${BASE}/policies/${encodeURIComponent(id)}/supersede`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to supersede warranty policy'));
  return (await res.json()) as SupersedeResult;
}

// ── Terms ───────────────────────────────────────────────────────────────────

export async function listTermsGroupedByKind(policyId: string): Promise<WarrantyTermsGrouped> {
  const res = await apiFetch(
    `${BASE}/policies/${encodeURIComponent(policyId)}/terms?group_by=kind`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load warranty terms'));
  return (await res.json()) as WarrantyTermsGrouped;
}

export async function createTerm(
  policyId: string,
  body: WarrantyTermWrite,
): Promise<WarrantyTermRow> {
  const res = await apiFetch(`${BASE}/policies/${encodeURIComponent(policyId)}/terms`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to create warranty term'));
  return (await res.json()) as WarrantyTermRow;
}

export async function updateTerm(
  policyId: string,
  termId: string,
  body: WarrantyTermWrite,
): Promise<WarrantyTermRow> {
  const res = await apiFetch(
    `${BASE}/policies/${encodeURIComponent(policyId)}/terms/${encodeURIComponent(termId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update warranty term'));
  return (await res.json()) as WarrantyTermRow;
}

export async function deleteTerm(policyId: string, termId: string): Promise<void> {
  const res = await apiFetch(
    `${BASE}/policies/${encodeURIComponent(policyId)}/terms/${encodeURIComponent(termId)}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete warranty term'));
}

// ── Kinds ───────────────────────────────────────────────────────────────────

export async function listKinds(searchQuery = ''): Promise<WarrantyKindRow[]> {
  const qs = searchQuery ? `?query=${encodeURIComponent(searchQuery)}` : '';
  const res = await apiFetch(`${BASE}/kinds${qs}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load product kinds'));
  return (await res.json()) as WarrantyKindRow[];
}

export async function listKindOptions(): Promise<WarrantyKindRef[]> {
  const res = await apiFetch(`${BASE}/kinds/select`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load product kinds'));
  return (await res.json()) as WarrantyKindRef[];
}

export async function createKind(body: WarrantyKindWrite): Promise<WarrantyKindRow> {
  const res = await apiFetch(`${BASE}/kinds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to create product kind'));
  return (await res.json()) as WarrantyKindRow;
}

export async function updateKind(id: string, body: WarrantyKindWrite): Promise<WarrantyKindRow> {
  const res = await apiFetch(`${BASE}/kinds/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update product kind'));
  return (await res.json()) as WarrantyKindRow;
}

export async function deleteKind(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/kinds/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete product kind'));
}

// ── Kind rules ──────────────────────────────────────────────────────────────

export async function listKindRules(kindId: string | null = null): Promise<WarrantyKindRuleRow[]> {
  const qs = kindId ? `?kind_id=${encodeURIComponent(kindId)}` : '';
  const res = await apiFetch(`${BASE}/kind-rules${qs}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load kind rules'));
  return (await res.json()) as WarrantyKindRuleRow[];
}

export async function createKindRule(body: WarrantyKindRuleWrite): Promise<WarrantyKindRuleRow> {
  const res = await apiFetch(`${BASE}/kind-rules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to create kind rule'));
  return (await res.json()) as WarrantyKindRuleRow;
}

/**
 * PATCH is partial: keys the caller omits are left untouched server-side. That
 * is how an edit to a legacy rule's priority avoids rewriting a `match_type`
 * the picker never offered (AC-P24, tolerant at read / strict at write).
 */
export async function updateKindRule(
  id: string,
  body: WarrantyKindRuleUpdate,
): Promise<WarrantyKindRuleRow> {
  const res = await apiFetch(`${BASE}/kind-rules/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to update kind rule'));
  return (await res.json()) as WarrantyKindRuleRow;
}

export async function deleteKindRule(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/kind-rules/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete kind rule'));
}

export async function testKindRules(body: KindRuleTestRequest): Promise<KindRuleTestResponse> {
  const res = await apiFetch(`${BASE}/kind-rules/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to test kind rules'));
  return (await res.json()) as KindRuleTestResponse;
}

// ── Defect types ────────────────────────────────────────────────────────────

export async function listDefectTypes(): Promise<DefectTypeOption[]> {
  const res = await apiFetch(`${BASE}/defect-types`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load defect types'));
  return (await res.json()) as DefectTypeOption[];
}
