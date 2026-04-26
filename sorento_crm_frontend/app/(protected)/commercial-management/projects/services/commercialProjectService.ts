import { apiFetch } from '@/lib/api';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  CommercialLeadOption,
  CommercialProjectDetail,
  CommercialProjectListRow,
  CommercialProjectMasterQuotationRow,
  CommercialProjectTaskTemplateRow,
} from '../types/commercialProject.types';

/** Matches FastAPI `list_projects`: `limit` query le=300 */
export const COMMERCIAL_PROJECTS_MAX_PAGE_SIZE = 300;

export type CommercialProjectsListParams = DataGridApiFetchParams & {
  owner_user_id?: string;
  status?: string;
  project_stage_id?: string;
  lead_id?: string;
  customer_id?: string;
};

export async function getCommercialProjects(
  params: CommercialProjectsListParams,
): Promise<DataGridApiResponse<CommercialProjectListRow>> {
  const { pageIndex, pageSize, searchQuery, owner_user_id, status, project_stage_id, lead_id, customer_id } = params;
  const safeLimit = Math.min(Math.max(pageSize, 1), COMMERCIAL_PROJECTS_MAX_PAGE_SIZE);
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(safeLimit),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(owner_user_id ? { owner_user_id } : {}),
    ...(status && status !== '__all__' ? { status } : {}),
    ...(project_stage_id && project_stage_id !== '__all__' ? { project_stage_id } : {}),
    ...(lead_id ? { lead_id } : {}),
    ...(customer_id ? { customer_id } : {}),
  });
  const response = await apiFetch(`/api/v1/commercial/projects?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch projects');
  return response.json();
}

/** Kanban / boards need every row; backend caps each request at {@link COMMERCIAL_PROJECTS_MAX_PAGE_SIZE}. */
export async function getCommercialProjectsAllPages(
  params: Omit<CommercialProjectsListParams, 'pageIndex' | 'pageSize'>,
): Promise<DataGridApiResponse<CommercialProjectListRow>> {
  const merged: CommercialProjectListRow[] = [];
  let pageIndex = 0;
  let total = 0;
  for (;;) {
    const resp = await getCommercialProjects({
      ...params,
      pageIndex,
      pageSize: COMMERCIAL_PROJECTS_MAX_PAGE_SIZE,
    });
    const rows = resp.data ?? [];
    total = resp.pagination?.total ?? merged.length + rows.length;
    merged.push(...rows);
    if (merged.length >= total || rows.length < COMMERCIAL_PROJECTS_MAX_PAGE_SIZE) break;
    pageIndex += 1;
  }
  return {
    data: merged,
    empty: merged.length === 0,
    pagination: { total, page: 1 },
  };
}

export async function getCommercialProject(id: string): Promise<CommercialProjectDetail> {
  const response = await apiFetch(`/api/v1/commercial/projects/${id}`);
  if (!response.ok) throw new Error('Failed to fetch project');
  return response.json();
}

export async function listProjectMasterQuotations(projectId: string): Promise<CommercialProjectMasterQuotationRow[]> {
  const response = await apiFetch(`/api/v1/commercial/projects/${projectId}/master-quotations`);
  if (!response.ok) throw new Error('Failed to fetch quotations');
  const json = (await response.json()) as { data: CommercialProjectMasterQuotationRow[] };
  return json.data ?? [];
}

export async function createProjectMasterQuotation(
  projectId: string,
  body: {
    title: string;
    valid_until?: string | null;
    description?: string | null;
    remark?: string | null;
    owner_user_id?: string | null;
    customer_id?: string | null;
    lead_id?: string | null;
    task_template_id?: string | null;
    quotation_package_template_id?: string | null;
  },
): Promise<{ id: string; tender_code: string; quotation_code: string }> {
  const response = await apiFetch(`/api/v1/commercial/projects/${projectId}/master-quotations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: body.title,
      ...(body.valid_until ? { valid_until: body.valid_until } : {}),
      ...(body.description != null && body.description !== '' ? { description: body.description } : {}),
      ...(body.remark != null && body.remark !== '' ? { remark: body.remark } : {}),
      ...(body.owner_user_id ? { owner_user_id: body.owner_user_id } : {}),
      ...(body.customer_id ? { customer_id: body.customer_id } : {}),
      ...(body.lead_id ? { lead_id: body.lead_id } : {}),
      ...(body.task_template_id ? { task_template_id: body.task_template_id } : {}),
      ...(body.quotation_package_template_id ? { quotation_package_template_id: body.quotation_package_template_id } : {}),
    }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const d = err as { detail?: string };
    throw new Error(d.detail || 'Failed to create quotation');
  }
  const row = (await response.json()) as { id: string; tender_code: string; quotation_code: string };
  return row;
}

export type MasterQuotationDuplicateResult = {
  id: string;
  tender_code: string;
  quotation_code: string;
  project_id?: string | null;
};

/** Clone master quotation (new code, working revision snapshot) on the same project tender. */
export async function duplicateMasterQuotation(masterId: string): Promise<MasterQuotationDuplicateResult> {
  const response = await apiFetch(
    `/api/v1/commercial/master-quotations/${encodeURIComponent(masterId)}/duplicate`,
    { method: 'POST' },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to duplicate quotation');
  }
  return response.json() as Promise<MasterQuotationDuplicateResult>;
}

export async function duplicateCommercialProject(id: string): Promise<CommercialProjectDetail> {
  const response = await apiFetch(`/api/v1/commercial/projects/${encodeURIComponent(id)}/duplicate`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to duplicate project');
  }
  return response.json();
}

export async function applyMasterQuotationPackageTemplate(
  masterId: string,
  quotation_package_template_id: string,
): Promise<void> {
  const response = await apiFetch(
    `/api/v1/commercial/master-quotations/${encodeURIComponent(masterId)}/apply-quotation-package-template`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quotation_package_template_id }),
    },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const d = err as { detail?: string };
    throw new Error(d.detail || 'Failed to apply quotation template');
  }
}

export async function listProjectTaskTemplates(): Promise<CommercialProjectTaskTemplateRow[]> {
  const response = await apiFetch('/api/v1/commercial/projects/task-templates/select');
  if (!response.ok) throw new Error('Failed to fetch task templates');
  return response.json();
}

export async function createCommercialProject(body: {
  lead_id?: string | null;
  title: string;
  brief?: string | null;
  notes?: string | null;
  address_line_1?: string | null;
  address_line_2?: string | null;
  postcode?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  task_template_id?: string | null;
  status?: string;
  project_stage_id?: string;
  owner_user_id?: string;
  project_owner_user_ids?: string[];
  developer_customer_id: string;
}): Promise<CommercialProjectDetail> {
  const response = await apiFetch('/api/v1/commercial/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to create project');
  }
  return response.json();
}

export async function updateCommercialProject(
  id: string,
  body: {
    lead_id?: string;
    title?: string | null;
    notes?: string | null;
    brief?: string | null;
    address_line_1?: string | null;
    address_line_2?: string | null;
    postcode?: string | null;
    city?: string | null;
    state?: string | null;
    country?: string | null;
    start_date?: string | null;
    end_date?: string | null;
    task_template_id?: string | null;
    task_board?: Record<string, unknown> | null;
    status?: string;
    project_stage_id?: string;
    owner_user_id?: string;
    project_owner_user_ids?: string[];
    developer_customer_id?: string;
    project_members?: Array<{ name: string; tags: string[] }>;
    project_customer_contacts?: Array<{
      id?: string | null;
      name: string;
      phone?: string | null;
      email?: string | null;
    }>;
  },
): Promise<CommercialProjectDetail> {
  const response = await apiFetch(`/api/v1/commercial/projects/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error('Failed to update project');
  return response.json();
}

export async function shareProjectOwnership(id: string): Promise<CommercialProjectDetail> {
  const response = await apiFetch(`/api/v1/commercial/projects/${id}/share-ownership`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to share project ownership');
  }
  return response.json();
}

export async function disownProject(id: string): Promise<CommercialProjectDetail> {
  const response = await apiFetch(`/api/v1/commercial/projects/${id}/disown`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to remove project ownership');
  }
  return response.json();
}

export type TaskScheduleImpactRow = {
  task_id: string;
  title: string;
  old_start_date?: string | null;
  old_end_date?: string | null;
  new_start_date?: string | null;
  new_end_date?: string | null;
};

export type TaskBoardSchedulePreviewResponse = {
  task_board: Record<string, unknown>;
  impacts: TaskScheduleImpactRow[];
};

export async function previewProjectTaskBoardSchedule(
  projectId: string,
  body: {
    task_board: Record<string, unknown>;
    baseline_start_date?: string | null;
    changed_task_id?: string | null;
  },
): Promise<TaskBoardSchedulePreviewResponse> {
  const response = await apiFetch(`/api/v1/commercial/projects/${encodeURIComponent(projectId)}/task-board/schedule/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to preview schedule');
  }
  return response.json();
}

export async function applyProjectTaskBoardSchedule(
  projectId: string,
  body: {
    task_board: Record<string, unknown>;
    baseline_start_date?: string | null;
    changed_task_id?: string | null;
  },
): Promise<TaskBoardSchedulePreviewResponse> {
  const response = await apiFetch(`/api/v1/commercial/projects/${encodeURIComponent(projectId)}/task-board/schedule/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to apply schedule');
  }
  return response.json();
}

export async function previewMasterQuotationTaskBoardSchedule(
  masterId: string,
  body: {
    task_board: Record<string, unknown>;
    baseline_start_date?: string | null;
    changed_task_id?: string | null;
  },
): Promise<TaskBoardSchedulePreviewResponse> {
  const response = await apiFetch(`/api/v1/commercial/master-quotations/${encodeURIComponent(masterId)}/task-board/schedule/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to preview schedule');
  }
  return response.json();
}

export async function applyMasterQuotationTaskBoardSchedule(
  masterId: string,
  body: {
    task_board: Record<string, unknown>;
    baseline_start_date?: string | null;
    changed_task_id?: string | null;
  },
): Promise<TaskBoardSchedulePreviewResponse> {
  const response = await apiFetch(`/api/v1/commercial/master-quotations/${encodeURIComponent(masterId)}/task-board/schedule/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to apply schedule');
  }
  return response.json();
}

export async function deleteCommercialProject(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/commercial/projects/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to delete project');
  }
}

/** Leads in terminal stages that allow project creation (workflow allows_conversion); backend validates on create. */
export async function listLeadsForProjectCreation(): Promise<CommercialLeadOption[]> {
  const q = new URLSearchParams({
    page: '1',
    limit: '100',
    terminal_conversion_eligible_only: 'true',
  });
  const response = await apiFetch(`/api/v1/commercial/leads?${q.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch leads');
  const json = (await response.json()) as {
    data: Array<{
      id: string;
      lead_code: string;
      title: string;
      stage_code: string | null;
    }>;
  };
  return json.data.map((r) => ({
    id: r.id,
    lead_code: r.lead_code,
    title: r.title,
    stage_code: r.stage_code,
  }));
}
