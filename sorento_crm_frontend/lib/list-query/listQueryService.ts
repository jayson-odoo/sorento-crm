import { apiFetch } from '@/lib/api';

export type ListQueryResourceKey =
  | 'orders'
  | 'products'
  | 'suppliers'
  | 'promotions'
  | 'workflow_form_definitions'
  | 'workflow_form_submissions'
  | 'commercial_activities'
  | 'commercial_activity_tasks'
  | 'commercial_project_tasks'
  | 'finance_billing_documents';

export type ListQueryFilterCondition = {
  field_key: string;
  op: string;
  value?: unknown;
};

export type ListQueryFilterGroup = {
  op: 'and' | 'or';
  children: (ListQueryFilterGroup | ListQueryFilterCondition)[];
};

export type ListQueryFieldMeta = {
  field_key: string;
  label: string;
  data_type: string;
  compile_key: string;
  allowed_operators: string[];
  filterable: boolean;
  exportable: boolean;
  export_column_name?: string | null;
  is_line_field: boolean;
  sort_order: number;
  /** Delivery orders export UI: top-level section */
  export_section?: 'order' | 'line' | null;
  /** Delivery orders export UI: nested under line */
  export_subgroup?: 'product' | 'warehouse' | null;
  /** Set (`{ kind: 'distinct' }`) when the field offers a pick list from the options endpoint. */
  option_source?: { kind: string } | null;
};

export type FetchListQueryFieldsOptions = {
  /** Workflow submissions: published schema fields for this definition (header / line JSON). */
  definitionId?: string | null;
};

export async function fetchListQueryFields(
  resourceKey: ListQueryResourceKey,
  options?: FetchListQueryFieldsOptions,
): Promise<ListQueryFieldMeta[]> {
  const sp = new URLSearchParams();
  if (options?.definitionId) sp.set('definition_id', options.definitionId);
  const q = sp.toString();
  const r = await apiFetch(`/api/v1/list-query/resources/${resourceKey}/fields${q ? `?${q}` : ''}`);
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(typeof err.detail === 'string' ? err.detail : 'Failed to load list fields');
  }
  return r.json();
}

export type ListQueryFieldOption = { value: string; label: string };

/** One page of a field's pick list: the distinct values over the resource's own scoped rows. */
export async function fetchListQueryFieldOptions(
  resourceKey: ListQueryResourceKey,
  fieldKey: string,
  params: { query?: string; page?: number; limit?: number } = {},
): Promise<{ data: ListQueryFieldOption[]; pagination: { total: number; page: number; limit: number } }> {
  const sp = new URLSearchParams();
  if (params.query) sp.set('query', params.query);
  if (params.page) sp.set('page', String(params.page));
  if (params.limit) sp.set('limit', String(params.limit));
  const q = sp.toString();
  const r = await apiFetch(
    `/api/v1/list-query/${resourceKey}/fields/${encodeURIComponent(fieldKey)}/options${q ? `?${q}` : ''}`,
  );
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(typeof err.detail === 'string' ? err.detail : 'Failed to load the options');
  }
  return r.json();
}

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((x) => (typeof x === 'object' && x && 'msg' in x ? String((x as { msg: string }).msg) : String(x))).join('; ');
  return 'Request failed';
}

export async function postListQuerySearch<T = unknown>(
  body: Record<string, unknown>,
): Promise<{
  data: T[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}> {
  const r = await apiFetch('/api/v1/list-query/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(detailMessage(err.detail));
  }
  return r.json();
}

export async function postListQueryExport(
  body: Record<string, unknown>,
): Promise<{ data: Record<string, unknown>[]; total: number }> {
  const r = await apiFetch('/api/v1/list-query/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(detailMessage(err.detail));
  }
  return r.json();
}
