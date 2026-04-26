import { apiFetch } from '@/lib/api';

const BASE = '/api/v1/commercial-activity';

export interface CommercialTaskCategory {
  code: string;
  label: string;
  sort_order: number;
  is_active: boolean;
}

export interface ActivityTaskStatusRow {
  id: string;
  code: string;
  label: string;
  sort_order: number;
  is_default: boolean;
  is_terminal: boolean;
  is_active: boolean;
}

export type ActivityTemplateScope = 'project' | 'quotation';

export interface RuntimeTemplateSummary {
  id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  version_number: number;
  template_scope?: ActivityTemplateScope;
  created_by_user_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TemplateNodeTree {
  id: string;
  template_id: string;
  parent_id: string | null;
  sort_order: number;
  title: string;
  category_code?: string | null;
  is_service_task?: boolean;
  description?: string | null;
  default_status_id?: string | null;
  default_offset_days?: number | null;
  lead_time_days?: number | null;
  dependency_node_ids?: string[];
  children: TemplateNodeTree[];
}

export interface RuntimeTemplateDetail extends RuntimeTemplateSummary {
  nodes: TemplateNodeTree[];
}

export async function listRuntimeActivityTemplates(
  activeOnly = true,
  templateScope?: ActivityTemplateScope,
): Promise<RuntimeTemplateSummary[]> {
  const params = new URLSearchParams();
  if (activeOnly) params.set('active_only', 'true');
  if (templateScope) params.set('template_scope', templateScope);
  const q = params.toString() ? `?${params.toString()}` : '';
  const res = await apiFetch(`${BASE}/templates${q}`);
  if (!res.ok) throw new Error('Failed to list templates');
  return res.json();
}

export async function getRuntimeActivityTemplate(templateId: string): Promise<RuntimeTemplateDetail> {
  const res = await apiFetch(`${BASE}/templates/${encodeURIComponent(templateId)}`);
  if (!res.ok) throw new Error('Failed to load template');
  return res.json();
}

export async function createRuntimeActivityTemplate(body: {
  name: string;
  description?: string | null;
  is_active?: boolean;
  template_scope?: ActivityTemplateScope;
}): Promise<RuntimeTemplateSummary> {
  const res = await apiFetch(`${BASE}/templates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Create failed');
  }
  return res.json();
}

export async function updateRuntimeActivityTemplate(
  templateId: string,
  body: {
    name?: string;
    description?: string | null;
    is_active?: boolean;
    template_scope?: ActivityTemplateScope;
  },
): Promise<RuntimeTemplateSummary> {
  const res = await apiFetch(`${BASE}/templates/${encodeURIComponent(templateId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Update failed');
  }
  return res.json();
}

export async function deleteRuntimeActivityTemplate(templateId: string): Promise<void> {
  const res = await apiFetch(`${BASE}/templates/${encodeURIComponent(templateId)}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Delete failed');
  }
}

export async function listTaskCategories(activeOnly = true): Promise<CommercialTaskCategory[]> {
  const q = `?active_only=${activeOnly ? 'true' : 'false'}`;
  const res = await apiFetch(`${BASE}/task-categories${q}`);
  if (!res.ok) throw new Error('Failed to load categories');
  return res.json();
}

export async function createTaskCategory(body: {
  code: string;
  label: string;
  sort_order?: number;
}): Promise<CommercialTaskCategory> {
  const res = await apiFetch(`${BASE}/task-categories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to create category');
  }
  return res.json();
}

export async function updateTaskCategory(
  code: string,
  body: { label?: string; sort_order?: number; is_active?: boolean },
): Promise<CommercialTaskCategory> {
  const res = await apiFetch(`${BASE}/task-categories/${encodeURIComponent(code)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to update category');
  }
  return res.json();
}

export async function deleteTaskCategory(code: string): Promise<void> {
  const res = await apiFetch(`${BASE}/task-categories/${encodeURIComponent(code)}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to delete category');
  }
}

export async function listActivityTaskStatuses(activeOnly = true): Promise<ActivityTaskStatusRow[]> {
  const q = activeOnly ? '?active_only=true' : '?active_only=false';
  const res = await apiFetch(`${BASE}/statuses${q}`);
  if (!res.ok) throw new Error('Failed to load statuses');
  return res.json();
}

export async function createTemplateNode(
  templateId: string,
  body: {
    parent_id?: string | null;
    sort_order?: number;
    title: string;
    description?: string | null;
    category_code?: string | null;
    is_service_task?: boolean;
    default_status_id?: string | null;
    default_offset_days?: number | null;
    lead_time_days?: number | null;
    dependency_node_ids?: string[];
  },
): Promise<TemplateNodeTree> {
  const res = await apiFetch(`${BASE}/templates/${encodeURIComponent(templateId)}/nodes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to add task');
  }
  return res.json() as Promise<TemplateNodeTree>;
}

export async function updateTemplateNode(
  templateId: string,
  nodeId: string,
  body: Partial<{
    parent_id: string | null;
    sort_order: number;
    title: string;
    description: string | null;
    category_code: string | null;
    is_service_task: boolean;
    default_status_id: string | null;
    default_offset_days: number | null;
    lead_time_days: number | null;
    dependency_node_ids: string[];
  }>,
): Promise<TemplateNodeTree> {
  const res = await apiFetch(
    `${BASE}/templates/${encodeURIComponent(templateId)}/nodes/${encodeURIComponent(nodeId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to update task');
  }
  return res.json();
}

export async function deleteTemplateNode(templateId: string, nodeId: string): Promise<void> {
  const res = await apiFetch(
    `${BASE}/templates/${encodeURIComponent(templateId)}/nodes/${encodeURIComponent(nodeId)}`,
    { method: 'DELETE' },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to delete task');
  }
}
