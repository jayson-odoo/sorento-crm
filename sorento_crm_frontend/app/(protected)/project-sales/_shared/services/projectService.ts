import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  ClashPreview,
  Project,
  ProjectCollaborator,
  ProjectListParams,
  ProjectParty,
  ProjectPartyBody,
  ProjectRegisterBody,
  ProjectStakeholder,
  ProjectStakeholderBody,
  ProjectTemplate,
  ProjectType,
  ProjectTypeBody,
  ProjectTask,
  ProjectTaskBody,
  ProjectTemplateBody,
  CustomerPortfolio,
  LeadConversionMetrics,
  LeadListParams,
  LeadQualifyBody,
  LeadReasonOption,
  ProjectLead,
  ProjectLeadBody,
  ProjectTemplateTask,
  ProjectTemplateTaskBody,
  ProjectUpdateBody,
  TakeoverRequest,
  TaskHistoryEntry,
  TaskPhase,
  TaskStatusChangeBody,
} from '../types/project.types';

const BASE = '/api/v1/project-sales';

interface ListEnvelope<T> {
  data: T[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}

/** Appends repeated params for array filters, which is what the API expects. */
function buildProjectParams(params: ProjectListParams): string {
  const sp = new URLSearchParams();
  if (params.query) sp.set('query', params.query);
  if (params.only_critical) sp.set('only_critical', 'true');
  if (params.page) sp.set('page', String(params.page));
  if (params.limit) sp.set('limit', String(params.limit));
  if (params.sort) sp.set('sort', params.sort);
  if (params.dir) sp.set('dir', params.dir);
  (
    ['status_id', 'outcome', 'owner_user_id', 'developer_party_id', 'type_id', 'brand_id'] as const
  ).forEach((key) => {
    (params[key] ?? []).forEach((value) => sp.append(key, value));
  });
  const query = sp.toString();
  return query ? `?${query}` : '';
}

export async function listProjects(
  params: ProjectListParams = {},
): Promise<ListEnvelope<Project>> {
  const response = await apiFetch(`${BASE}/projects/${buildProjectParams(params)}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load projects'));
  return response.json();
}

export async function getProject(projectId: string): Promise<Project> {
  const response = await apiFetch(`${BASE}/projects/${projectId}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load this project'));
  return response.json();
}

/**
 * Checks a title while the user is still typing it.
 *
 * Deliberately separate from the create call: warning at submit time, after the form
 * is filled, is what teaches people to work around the check.
 */
export async function previewClashes(body: {
  title: string;
  developer_party_id?: string | null;
}): Promise<ClashPreview> {
  const response = await apiFetch(`${BASE}/projects/clash-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Could not check for existing projects'));
  return response.json();
}

export async function registerProject(body: ProjectRegisterBody): Promise<Project> {
  const response = await apiFetch(`${BASE}/projects/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to register the project'));
  return response.json();
}

export async function updateProject(
  projectId: string,
  body: ProjectUpdateBody,
): Promise<Project> {
  const response = await apiFetch(`${BASE}/projects/${projectId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save the project'));
  return response.json();
}

export async function changeProjectStatus(
  projectId: string,
  toStatusId: string,
): Promise<Project> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to_status_id: toStatusId }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to move the project'));
  return response.json();
}

export async function deleteProject(projectId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/projects/${projectId}`, { method: 'DELETE' });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to delete the project'));
}

// ------------------------------------------------------------- stakeholders

export async function listStakeholders(projectId: string): Promise<ProjectStakeholder[]> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/stakeholders`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load stakeholders'));
  const body: ListEnvelope<ProjectStakeholder> = await response.json();
  return body.data;
}

export async function addStakeholder(
  projectId: string,
  body: ProjectStakeholderBody,
): Promise<ProjectStakeholder> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/stakeholders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to add the stakeholder'));
  return response.json();
}

export async function updateStakeholder(
  projectId: string,
  stakeholderId: string,
  body: Partial<ProjectStakeholderBody>,
): Promise<ProjectStakeholder> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/stakeholders/${stakeholderId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save the stakeholder'));
  return response.json();
}

export async function removeStakeholder(
  projectId: string,
  stakeholderId: string,
): Promise<void> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/stakeholders/${stakeholderId}`,
    { method: 'DELETE' },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to remove the stakeholder'));
}

// ------------------------------------------------- collaborators / requests

export async function listCollaborators(projectId: string): Promise<ProjectCollaborator[]> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/collaborators`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load collaborators'));
  const body: ListEnvelope<ProjectCollaborator> = await response.json();
  return body.data;
}

export async function listTakeoverRequests(projectId: string): Promise<TakeoverRequest[]> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/takeover-requests`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load requests'));
  const body: ListEnvelope<TakeoverRequest> = await response.json();
  return body.data;
}

export async function createTakeoverRequest(
  projectId: string,
  body: { kind: 'join' | 'dispute'; reason: string },
): Promise<TakeoverRequest> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/takeover-requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to send the request'));
  return response.json();
}

export async function decideTakeoverRequest(
  projectId: string,
  requestId: string,
  body: { approve: boolean; decision_note?: string | null },
): Promise<TakeoverRequest> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/takeover-requests/${requestId}/decide`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to record the decision'));
  return response.json();
}

// ------------------------------------------------------------------ parties

export async function listParties(
  params: {
    party_type?: string;
    query?: string;
    include_inactive?: boolean;
    page?: number;
    limit?: number;
  } = {},
): Promise<ListEnvelope<ProjectParty>> {
  const sp = new URLSearchParams();
  if (params.party_type) sp.set('party_type', params.party_type);
  if (params.query) sp.set('query', params.query);
  if (params.include_inactive) sp.set('include_inactive', 'true');
  if (params.page) sp.set('page', String(params.page));
  if (params.limit) sp.set('limit', String(params.limit));
  const query = sp.toString();
  const response = await apiFetch(`${BASE}/parties/${query ? `?${query}` : ''}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load parties'));
  return response.json();
}

export async function createParty(body: ProjectPartyBody): Promise<ProjectParty> {
  const response = await apiFetch(`${BASE}/parties/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to create the party'));
  return response.json();
}

export async function updateParty(
  partyId: string,
  body: Partial<ProjectPartyBody>,
): Promise<ProjectParty> {
  const response = await apiFetch(`${BASE}/parties/${partyId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save the party'));
  return response.json();
}

export async function deleteParty(partyId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/parties/${partyId}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete the party'));
}

// ------------------------------------------------------- types / templates

export async function listProjectTypes(includeInactive = false): Promise<ProjectType[]> {
  const response = await apiFetch(
    `${BASE}/config/types${includeInactive ? '?include_inactive=true' : ''}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load project types'));
  const body: ListEnvelope<ProjectType> = await response.json();
  return body.data;
}

export async function listProjectTemplates(typeId?: string): Promise<ProjectTemplate[]> {
  const sp = new URLSearchParams();
  if (typeId) sp.set('type_id', typeId);
  const query = sp.toString();
  const response = await apiFetch(`${BASE}/config/templates${query ? `?${query}` : ''}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load templates'));
  const body: ListEnvelope<ProjectTemplate> = await response.json();
  return body.data;
}

export async function createProjectType(body: ProjectTypeBody): Promise<ProjectType> {
  const response = await apiFetch(`${BASE}/config/types`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to create the project type'));
  return response.json();
}

export async function updateProjectType(
  typeId: string,
  body: Partial<ProjectTypeBody>,
): Promise<ProjectType> {
  const response = await apiFetch(`${BASE}/config/types/${typeId}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save the project type'));
  return response.json();
}

export async function deleteProjectType(typeId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/config/types/${typeId}`, { method: 'DELETE' });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to delete the project type'));
}

export async function createProjectTemplate(
  body: ProjectTemplateBody,
): Promise<ProjectTemplate> {
  const response = await apiFetch(`${BASE}/config/templates`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to create the template'));
  return response.json();
}

export async function updateProjectTemplate(
  templateId: string,
  body: Partial<ProjectTemplateBody>,
): Promise<ProjectTemplate> {
  const response = await apiFetch(`${BASE}/config/templates/${templateId}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save the template'));
  return response.json();
}

export async function deleteProjectTemplate(templateId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/config/templates/${templateId}`, {
    method: 'DELETE',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to delete the template'));
}

// ------------------------------------------------------------------- tasks

export async function listProjectTasks(
  projectId: string,
  taskPhase?: TaskPhase,
): Promise<ProjectTask[]> {
  const sp = new URLSearchParams();
  if (taskPhase) sp.set('task_phase', taskPhase);
  const query = sp.toString();
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/tasks${query ? `?${query}` : ''}`,
  );
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load tasks'));
  const body: ListEnvelope<ProjectTask> = await response.json();
  return body.data;
}

export async function createProjectTask(
  projectId: string,
  body: ProjectTaskBody,
): Promise<ProjectTask> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to add the task'));
  return response.json();
}

export async function updateProjectTask(
  projectId: string,
  taskId: string,
  body: Partial<ProjectTaskBody>,
): Promise<ProjectTask> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/tasks/${taskId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save the task'));
  return response.json();
}

/**
 * The move and its required context go in ONE request.
 *
 * Escalate needs a person and Stuck needs a reason; the server rejects the move
 * without them, so splitting this into two calls would leave a window where the task
 * is escalated to nobody.
 */
export async function changeTaskStatus(
  projectId: string,
  taskId: string,
  body: TaskStatusChangeBody,
): Promise<ProjectTask> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/tasks/${taskId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to move the task'));
  return response.json();
}

export async function deleteProjectTask(projectId: string, taskId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/projects/${projectId}/tasks/${taskId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete the task'));
}

export async function getTaskHistory(
  projectId: string,
  taskId: string,
): Promise<TaskHistoryEntry[]> {
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/tasks/${taskId}/history`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the task history'));
  const body: ListEnvelope<TaskHistoryEntry> = await response.json();
  return body.data;
}

export async function listMyTasks(
  params: { include_unassigned_owned?: boolean; page?: number; limit?: number } = {},
): Promise<ListEnvelope<ProjectTask>> {
  const sp = new URLSearchParams();
  if (params.include_unassigned_owned) sp.set('include_unassigned_owned', 'true');
  if (params.page) sp.set('page', String(params.page));
  if (params.limit) sp.set('limit', String(params.limit));
  const query = sp.toString();
  const response = await apiFetch(`${BASE}/my-tasks${query ? `?${query}` : ''}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load your tasks'));
  return response.json();
}

// ------------------------------------------------ template checklist admin

export async function listTemplateTasks(
  templateId: string,
): Promise<ProjectTemplateTask[]> {
  const response = await apiFetch(`${BASE}/config/templates/${templateId}/tasks`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the checklist'));
  const body: ListEnvelope<ProjectTemplateTask> = await response.json();
  return body.data;
}

export async function createTemplateTask(
  templateId: string,
  body: ProjectTemplateTaskBody,
): Promise<ProjectTemplateTask> {
  const response = await apiFetch(`${BASE}/config/templates/${templateId}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to add the checklist item'));
  return response.json();
}

export async function updateTemplateTask(
  templateId: string,
  templateTaskId: string,
  body: Partial<ProjectTemplateTaskBody>,
): Promise<ProjectTemplateTask> {
  const response = await apiFetch(
    `${BASE}/config/templates/${templateId}/tasks/${templateTaskId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save the checklist item'));
  return response.json();
}

export async function deleteTemplateTask(
  templateId: string,
  templateTaskId: string,
): Promise<void> {
  const response = await apiFetch(
    `${BASE}/config/templates/${templateId}/tasks/${templateTaskId}`,
    { method: 'DELETE' },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to remove the checklist item'));
}

// ------------------------------------------------------------------- leads

const LEADS = `${BASE}/leads`;

export async function listLeads(
  params: LeadListParams = {},
): Promise<ListEnvelope<ProjectLead>> {
  const sp = new URLSearchParams();
  if (params.query) sp.set('query', params.query);
  (params.outcome ?? []).forEach((value) => sp.append('outcome', value));
  (params.status_id ?? []).forEach((value) => sp.append('status_id', value));
  (params.owner_user_id ?? []).forEach((value) => sp.append('owner_user_id', value));
  (params.customer_id ?? []).forEach((value) => sp.append('customer_id', value));
  (params.source ?? []).forEach((value) => sp.append('source', value));
  if (params.page) sp.set('page', String(params.page));
  if (params.limit) sp.set('limit', String(params.limit));
  if (params.sort) sp.set('sort', params.sort);
  if (params.dir) sp.set('dir', params.dir);
  const query = sp.toString();
  const response = await apiFetch(`${LEADS}${query ? `?${query}` : ''}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load leads'));
  return response.json();
}

export async function getLead(leadId: string): Promise<ProjectLead> {
  const response = await apiFetch(`${LEADS}/${leadId}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the lead'));
  return response.json();
}

export async function createLead(body: ProjectLeadBody): Promise<ProjectLead> {
  const response = await apiFetch(LEADS, { method: 'POST', body: JSON.stringify(body) });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to record the lead'));
  return response.json();
}

export async function updateLead(
  leadId: string,
  body: Partial<ProjectLeadBody>,
): Promise<ProjectLead> {
  const response = await apiFetch(`${LEADS}/${leadId}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save the lead'));
  return response.json();
}

export async function changeLeadStatus(
  leadId: string,
  toStatusId: string,
): Promise<ProjectLead> {
  const response = await apiFetch(`${LEADS}/${leadId}/status`, {
    method: 'POST',
    body: JSON.stringify({ to_status_id: toStatusId }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to move the lead'));
  return response.json();
}

/**
 * What qualifying WOULD hit, before the user commits to it. Same matcher and
 * thresholds as registration, so the preview cannot disagree with the decision.
 */
export async function previewQualify(
  leadId: string,
  params: { title?: string | null; developer_party_id?: string | null } = {},
): Promise<ClashPreview> {
  const sp = new URLSearchParams();
  if (params.title) sp.set('title', params.title);
  if (params.developer_party_id) sp.set('developer_party_id', params.developer_party_id);
  const query = sp.toString();
  const response = await apiFetch(
    `${LEADS}/${leadId}/qualify-preview${query ? `?${query}` : ''}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to check for clashes'));
  return response.json();
}

/** Returns the PROJECT, because that is what qualifying produces (AC-O4). */
export async function qualifyLead(
  leadId: string,
  body: LeadQualifyBody = {},
): Promise<Project> {
  const response = await apiFetch(`${LEADS}/${leadId}/qualify`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to qualify the lead'));
  return response.json();
}

export async function disqualifyLead(
  leadId: string,
  reason: string,
): Promise<ProjectLead> {
  const response = await apiFetch(`${LEADS}/${leadId}/disqualify`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to disqualify the lead'));
  return response.json();
}

export async function reopenLead(leadId: string): Promise<ProjectLead> {
  const response = await apiFetch(`${LEADS}/${leadId}/reopen`, { method: 'POST' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to reopen the lead'));
  return response.json();
}

export async function deleteLead(leadId: string): Promise<void> {
  const response = await apiFetch(`${LEADS}/${leadId}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete the lead'));
}

export async function listDisqualifyReasons(): Promise<LeadReasonOption[]> {
  const response = await apiFetch(`${LEADS}/disqualify-reasons`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load reasons'));
  return response.json();
}

export async function getLeadMetrics(): Promise<LeadConversionMetrics> {
  const response = await apiFetch(`${LEADS}/metrics`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load lead metrics'));
  return response.json();
}

export async function getCustomerPortfolio(customerId: string): Promise<CustomerPortfolio> {
  const response = await apiFetch(`${LEADS}/by-customer/${customerId}/portfolio`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load this account'));
  return response.json();
}
