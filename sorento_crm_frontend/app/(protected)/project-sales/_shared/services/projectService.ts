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
  ProjectUpdateBody,
  TakeoverRequest,
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
