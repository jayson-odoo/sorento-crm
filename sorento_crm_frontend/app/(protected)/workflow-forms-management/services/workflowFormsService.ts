import { apiFetch } from '@/lib/api';
import type {
  Paginated,
  WorkflowFormDefinition,
  WorkflowFormSchema,
  WorkflowSubmission,
} from '../types/workflowForms.types';

const BASE = '/api/v1/workflow-forms';

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try {
      const j = JSON.parse(text) as { detail?: unknown };
      if (typeof j.detail === 'string') detail = j.detail;
      else if (j.detail && typeof j.detail === 'object') detail = JSON.stringify(j.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export type WorkflowPublishedDefinition = Pick<WorkflowFormDefinition, 'id' | 'code' | 'name'>;

/** Published forms only; allowed with submissions.add / submissions.view (no definitions.view). */
export async function fetchPublishedWorkflowDefinitionsForSubmission(): Promise<
  Paginated<WorkflowPublishedDefinition>
> {
  const res = await apiFetch(`${BASE}/definitions/published-for-submission`);
  return parseJson(res);
}

/** Published schema for new/edit submission UI without definitions.view. */
export async function fetchPublishedWorkflowSchema(
  definitionId: string,
): Promise<{ schema: WorkflowFormSchema; source: string }> {
  const res = await apiFetch(
    `${BASE}/definitions/${encodeURIComponent(definitionId)}/published-schema`,
  );
  return parseJson(res);
}

export async function fetchWorkflowDefinitions(params: {
  page?: number;
  limit?: number;
  q?: string;
  is_active?: boolean;
}): Promise<Paginated<WorkflowFormDefinition>> {
  const sp = new URLSearchParams();
  if (params.page) sp.set('page', String(params.page));
  if (params.limit) sp.set('limit', String(params.limit));
  if (params.q) sp.set('q', params.q);
  if (params.is_active !== undefined) sp.set('is_active', String(params.is_active));
  const q = sp.toString();
  const res = await apiFetch(`${BASE}/definitions${q ? `?${q}` : ''}`);
  return parseJson(res);
}

export async function fetchWorkflowDefinition(id: string): Promise<WorkflowFormDefinition> {
  const res = await apiFetch(`${BASE}/definitions/${encodeURIComponent(id)}`);
  return parseJson(res);
}

export async function createWorkflowDefinition(body: {
  code: string;
  name: string;
  description?: string;
}): Promise<WorkflowFormDefinition> {
  const res = await apiFetch(`${BASE}/definitions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return parseJson(res);
}

export async function updateWorkflowDefinition(
  id: string,
  body: Partial<{
    name: string;
    description: string | null;
    is_active: boolean;
    draft_schema: WorkflowFormSchema;
  }>,
): Promise<WorkflowFormDefinition> {
  const res = await apiFetch(`${BASE}/definitions/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return parseJson(res);
}

export async function publishWorkflowDefinition(id: string): Promise<{
  id: string;
  version_number: number;
  definition_id: string;
}> {
  const res = await apiFetch(`${BASE}/definitions/${encodeURIComponent(id)}/publish`, {
    method: 'POST',
  });
  return parseJson(res);
}

export async function deleteWorkflowDefinition(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/definitions/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || `Delete failed (${res.status})`);
  }
}

export async function previewWorkflowDefinition(
  id: string,
  source: 'draft' | 'published' = 'draft',
): Promise<{ schema: WorkflowFormSchema; source: string }> {
  const res = await apiFetch(
    `${BASE}/definitions/${encodeURIComponent(id)}/preview?source=${source}`,
  );
  return parseJson(res);
}

export async function fetchWorkflowFlowGraph(
  id: string,
  source: 'draft' | 'published' = 'draft',
): Promise<{
  nodes: { id: string; code: string; name: string; is_initial: boolean; is_terminal: boolean }[];
  edges: {
    id: string;
    from_state_id: string;
    to_state_id: string;
    label: string;
    direction: string;
  }[];
}> {
  const res = await apiFetch(
    `${BASE}/definitions/${encodeURIComponent(id)}/flow-graph?source=${source}`,
  );
  return parseJson(res);
}

export async function fetchWorkflowSubmissions(params: {
  page?: number;
  limit?: number;
  definition_id?: string;
  state_code?: string;
}): Promise<Paginated<WorkflowSubmission>> {
  const sp = new URLSearchParams();
  if (params.page) sp.set('page', String(params.page));
  if (params.limit) sp.set('limit', String(params.limit));
  if (params.definition_id) sp.set('definition_id', params.definition_id);
  if (params.state_code) sp.set('state_code', params.state_code);
  const q = sp.toString();
  const res = await apiFetch(`${BASE}/submissions${q ? `?${q}` : ''}`);
  return parseJson(res);
}

export async function fetchWorkflowSubmission(id: string): Promise<WorkflowSubmission> {
  const res = await apiFetch(`${BASE}/submissions/${encodeURIComponent(id)}`);
  return parseJson(res);
}

export async function createWorkflowSubmission(body: {
  definition_id: string;
  header_data: Record<string, unknown>;
  lines: { line_group_id: string; sort_order?: number; row_data: Record<string, unknown> }[];
}): Promise<WorkflowSubmission> {
  const res = await apiFetch(`${BASE}/submissions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return parseJson(res);
}

export async function updateWorkflowSubmission(
  id: string,
  body: {
    header_data?: Record<string, unknown>;
    lines?: { line_group_id: string; sort_order?: number; row_data: Record<string, unknown> }[];
  },
): Promise<WorkflowSubmission> {
  const res = await apiFetch(`${BASE}/submissions/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return parseJson(res);
}

export async function deleteWorkflowSubmission(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/submissions/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || `Delete failed (${res.status})`);
  }
}

export async function fetchAllowedTransitions(submissionId: string): Promise<{
  transitions: { id: string; label: string; direction: string; to_state_code: string | null }[];
}> {
  const res = await apiFetch(
    `${BASE}/submissions/${encodeURIComponent(submissionId)}/allowed-transitions`,
  );
  return parseJson(res);
}

export async function applyWorkflowTransition(
  submissionId: string,
  body: { transition_id: string; remark?: string },
): Promise<WorkflowSubmission> {
  const res = await apiFetch(
    `${BASE}/submissions/${encodeURIComponent(submissionId)}/transition`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  return parseJson(res);
}
